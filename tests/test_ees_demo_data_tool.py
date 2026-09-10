"""Synthetic data boundaries and numerical evidence; no WebUI or LLM is invoked."""

import asyncio
import importlib.util
import json
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch


PATH = Path(__file__).resolve().parents[1] / "agent-pack/skills/cross-system-analysis/scripts/demo_data_tool.py"
SPEC = importlib.util.spec_from_file_location("ees_demo_data_tests", PATH)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class DemoDataTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tool = module.Tools()
        self.tool.valves.ees_model_id = "existing-ees"

    async def read(self, domain="ems", **kwargs):
        return await self.tool.read_demo_data(__metadata__={"model_id": f"ees_demo_{domain}"}, **kwargs)

    async def compare(self, **kwargs):
        return await self.tool.compare_demo_data(__metadata__={"model_id": "existing-ees"}, **kwargs)

    @staticmethod
    def panel_updates(events):
        updates = []
        for event in events:
            if event["type"] == "execute":
                code = event["data"]["code"]
                prefix = "const eesPanelUpdate="
                if not code.startswith(prefix):
                    raise AssertionError("Unexpected executable prefix")
                value, end = json.JSONDecoder().raw_decode(code[len(prefix):])
                if code[len(prefix) + end:] != ";\n" + module.PANEL_SCRIPT:
                    raise AssertionError("The executable suffix must be the fixed script")
                updates.append(value)
        return updates

    async def test_panel_shows_exact_comparison_conditions_results_and_independent_calls(self):
        events = []
        async def emit(event):
            events.append(event)
        metadata = {"model_id": "existing-ees", "chat_id": "parent-chat", "message_id": "parent-message",
                    "user": {"pat": "DO-NOT-RETURN"}, "provider": "DO-NOT-RETURN"}
        with patch.object(module, "PANEL_SCRIPT", "/* fixed panel */"):
            results = await asyncio.gather(*(
                self.tool.compare_demo_data(dataset=dataset, group_by="recipe_id",
                    __metadata__=metadata, __event_emitter__=emit) for dataset in ("sample_a", "sample_b")))
            updates = self.panel_updates(events)
        grouped = {}
        for update in updates:
            grouped.setdefault(update["call_id"], []).append(update)
            self.assertEqual((update["chat_id"], update["message_id"]), ("parent-chat", "parent-message"))
            self.assertEqual((update["kind"], update["version"]), ("comparison", 1))
            self.assertEqual(update["batch_id"], update["call_id"])
        self.assertEqual(len(grouped), 2)
        for rows, result in zip(grouped.values(), results):
            self.assertEqual([u["seq"] for u in rows], [1, 2, 3])
            self.assertEqual([u["phase"] for u in rows], ["requested", "querying", "completed"])
            self.assertNotIn("result", rows[0])
            self.assertEqual(rows[-1]["result"], result)
            self.assertEqual(rows[-1]["arguments"], {"dataset": result["dataset"], "group_by": "recipe_id",
                "equipment_id": "", "recipe_id": "", "event_ids": ""})
        self.assertNotIn("DO-NOT-RETURN", json.dumps(updates))

    async def test_panel_marks_validation_or_calculation_failure_without_leaking_exception(self):
        events = []
        async def emit(event):
            events.append(event)
        kwargs = {"__metadata__": {"model_id": "existing-ees", "chat_id": "chat", "message_id": "message"},
                  "__event_emitter__": emit}
        with patch.object(module, "PANEL_SCRIPT", "/* fixed panel */"):
            failed = await self.tool.compare_demo_data(group_by='invalid";\nfilter', **kwargs)
            rows = self.panel_updates(events)
            self.assertEqual(rows[-1]["phase"], "failed")
            self.assertEqual(rows[-1]["error"], "invalid_grouping")
            self.assertEqual(rows[-1]["result"], failed)
            self.assertEqual(rows[-1]["arguments"]["group_by"], 'invalid";\nfilter')
            events.clear()
            with patch.object(module, "_joint_observation", side_effect=RuntimeError("DO-NOT-RETURN")):
                result = await self.tool.compare_demo_data(**kwargs)
            self.assertEqual(result["error"]["code"], "comparison_failed")
            self.assertEqual(self.panel_updates(events)[-1]["phase"], "failed")
            self.assertNotIn("DO-NOT-RETURN", json.dumps(events))

    async def test_panel_unavailable_or_unauthorized_does_not_change_calculation(self):
        async def unavailable(event):
            await asyncio.Event().wait()
        metadata = {"model_id": "existing-ees", "chat_id": "chat", "message_id": "message"}
        with patch.object(module, "PANEL_SCRIPT", "/* fixed panel */"), patch.object(module, "PANEL_SEND_TIMEOUT", 0.002):
            result = await asyncio.wait_for(self.tool.compare_demo_data(
                __metadata__=metadata, __event_emitter__=unavailable), timeout=1)
            self.assertEqual(result, await self.compare())
            events = []
            async def emit(event):
                events.append(event)
            for metadata in ({"model_id": "ees_demo_ems", "chat_id": "chat", "message_id": "message"},
                             {"model_id": "existing-ees"}):
                await self.tool.compare_demo_data(__metadata__=metadata, __event_emitter__=emit)
            self.assertEqual(events, [])

    async def test_panel_cancellation_propagates_and_never_claims_an_unstarted_calculation(self):
        events = []
        entered = asyncio.Event()
        async def emit(event):
            events.append(event)
            if self.panel_updates([event])[0]["phase"] == "querying":
                entered.set()
                await asyncio.Event().wait()
        with patch.object(module, "PANEL_SCRIPT", "/* fixed panel */"):
            job = asyncio.create_task(self.tool.compare_demo_data(
                __metadata__={"model_id": "existing-ees", "chat_id": "chat", "message_id": "message"},
                __event_emitter__=emit))
            await entered.wait()
            job.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await job
            updates = self.panel_updates(events)
        self.assertEqual([u["phase"] for u in updates], ["requested", "querying", "cancelled"])
        self.assertNotIn("result", updates[-1])

    async def test_domain_is_server_metadata_and_never_model_argument(self):
        for metadata in (None, {}, {"model_id": "unknown"}, {"model_id": ["ees_demo_ems"]},
                         {"model": "ees_demo_ems"}, {"model_id": "existing-ees"}):
            with self.subTest(metadata=metadata):
                self.assertFalse((await self.tool.read_demo_data(__metadata__=metadata))["ok"])
        ems = await self.read()
        apc = await self.read("apc")
        fdc = await self.read("fdc")
        self.assertEqual([data["domain"] for data in (ems, apc, fdc)], ["EMS", "APC", "FDC"])
        self.assertIn("work_description", ems["records"][0])
        self.assertNotIn("mean", ems["records"][0])
        self.assertNotIn("work_description", apc["records"][0])
        self.assertNotIn("restart_type", fdc["records"][0])
        self.assertEqual(apc["records"][0]["unit"], "mm (시연 보정량)")
        self.assertNotEqual(apc["records"][0]["allowed_range"], fdc["records"][0]["allowed_range"])

    async def test_only_configured_parent_can_compare_and_unset_fails_closed(self):
        for model_id in ("ees_demo_ems", "ees_demo_apc", "ees_demo_fdc", "unrelated"):
            result = await self.tool.compare_demo_data(__metadata__={"model_id": model_id})
            self.assertEqual(result["error"]["code"], "comparison_not_allowed")
        self.assertTrue((await self.compare())["ok"])
        self.tool.valves.ees_model_id = ""
        self.assertFalse((await self.compare())["ok"])

    async def test_three_reads_per_child_request_and_fresh_request_is_independent(self):
        metadata = {"model_id": "ees_demo_ems"}
        for remaining in (2, 1, 0):
            result = await self.tool.read_demo_data(__metadata__=metadata)
            self.assertTrue(result["ok"])
            self.assertEqual(result["remaining_queries"], remaining)
        self.assertEqual((await self.tool.read_demo_data(__metadata__=metadata))["error"]["code"], "query_limit")
        self.assertTrue((await self.read())["ok"])
        for counter in (True, -1, "0", None):
            result = await self.tool.read_demo_data(__metadata__={"model_id": "ees_demo_ems", "ees_demo_data_calls": counter})
            self.assertEqual(result["error"]["code"], "query_limit")

    async def test_small_summary_then_exact_event_detail_has_consistent_evidence(self):
        summary = await self.read("apc", equipment_id="EQ-01", recipe_id="R-02")
        event = summary["records"][0]
        self.assertNotIn("records", event)
        detailed = (await self.read("apc", event_id=event["event_id"]))["records"][0]
        self.assertEqual(len(detailed["records"]), 30)
        self.assertEqual(event["mean"], detailed["mean"])
        self.assertEqual(event["source_records"], [detailed["records"][0]["record_id"], detailed["records"][-1]["record_id"]])
        self.assertIsNotNone(datetime.fromisoformat(detailed["records"][0]["observed_at"]).tzinfo)

    async def test_invalid_selectors_do_not_silently_read_other_data(self):
        for args in ({"dataset": "sample_b_override"}, {"equipment_id": "EQ-99"}, {"recipe_id": "R-03"},
                     {"event_id": "sample_b-01"}, {"dataset": []}, {"event_id": "x" * 81}):
            with self.subTest(args=args):
                self.assertFalse((await self.read(**args))["ok"])
        for args in ({"group_by": "sql"}, {"event_ids": "sample_b-01"}, {"event_ids": []},
                     {"group_by": None}, {"dataset": "unknown"}):
            with self.subTest(args=args):
                self.assertFalse((await self.compare(**args))["ok"])
        result = await self.read(event_id="sample_a-01", equipment_id="EQ-02")
        self.assertTrue(result["ok"])
        self.assertEqual(result["record_count"], 0)

    async def test_joint_confirmation_uses_fifth_aligned_sample_and_record_evidence(self):
        result = await self.compare(event_ids="sample_a-07")
        event = result["events"][0]
        # APC enters its range at minute 16; FDC at 18. Joint window is 18..22.
        self.assertEqual(event["confirmed_after_minutes"], 22)
        self.assertEqual((datetime.fromisoformat(event["confirmation_at"]) -
                          datetime.fromisoformat(event["resumed_at"])).total_seconds(), 22 * 60)
        self.assertEqual(len(event["evidence_record_ids"]), 11)
        self.assertIn("APC-sample_a-07-18", event["evidence_record_ids"])
        self.assertIn("FDC-sample_a-07-22", event["evidence_record_ids"])
        self.assertIsNone(result["comparisons"][0]["maintenance_minus_planned_minutes"])

    def test_in_range_requires_both_domains_at_same_times_not_separate_streaks(self):
        event = module._fixtures("sample_a")[0]
        for domain, rows in event["records"].items():
            if domain == "EMS":
                continue
            for minute, row in enumerate(rows, 1):
                row["value"] = 1.0 if domain == "APC" else 10.0
                if (domain == "APC" and minute > 5) or (domain == "FDC" and minute < 6):
                    row["value"] = 99
        self.assertEqual(module._joint_observation(event)["state"], "not_confirmed_within_window")

    def test_boundary_values_count_and_four_samples_do_not_finish(self):
        event = module._fixtures("sample_a")[0]
        for domain in ("APC", "FDC"):
            lower, upper = module._RECIPES[event["recipe_id"]][domain]
            for minute, row in enumerate(event["records"][domain], 1):
                row["value"] = upper + 10 if minute < 27 else lower if minute % 2 else upper
        self.assertEqual(module._joint_observation(event)["state"], "not_confirmed_within_window")
        for domain in ("APC", "FDC"):
            event["records"][domain][25]["value"] = module._RECIPES[event["recipe_id"]][domain][0]
        self.assertEqual(module._joint_observation(event)["confirmed_after_minutes"], 30)

    async def test_unconfirmed_and_incomplete_denominators_are_not_zero_minutes(self):
        result = await self.compare()
        summary = result["summary"]
        self.assertEqual((summary["total_events"], summary["assessable_events"], summary["confirmed_events"],
                          summary["not_confirmed_events"], summary["unassessable_events"]), (15, 13, 12, 1, 2))
        self.assertEqual(summary["mean_denominator"], 12)
        self.assertAlmostEqual(summary["mean_confirmed_minutes"], 125 / 12, places=3)
        by_id = {row["event_id"]: row for row in result["events"]}
        self.assertEqual(by_id["sample_a-13"]["state"], "not_confirmed_within_window")
        self.assertEqual(by_id["sample_a-14"]["missing_samples"], {"APC": 0, "FDC": 1})
        self.assertEqual(by_id["sample_a-15"]["missing_samples"], {"APC": 18, "FDC": 18})
        for number in (13, 14, 15):
            self.assertIsNone(by_id[f"sample_a-{number}"]["confirmed_after_minutes"])
        excluded = await self.compare(event_ids="sample_a-13,sample_a-14,sample_a-15")
        self.assertIsNone(excluded["summary"]["mean_confirmed_minutes"])
        self.assertEqual(excluded["summary"]["mean_denominator"], 0)

    async def test_case_a_has_conditional_difference_with_normal_controls(self):
        result = await self.compare(group_by="equipment_recipe")
        groups = {(v["conditions"]["equipment_id"], v["conditions"]["recipe_id"]): v for v in result["comparisons"]}
        self.assertEqual(groups[("EQ-01", "R-02")]["maintenance_minus_planned_minutes"], 14.5)
        self.assertEqual(groups[("EQ-01", "R-01")]["maintenance_minus_planned_minutes"], 0)
        self.assertEqual(groups[("EQ-02", "R-02")]["maintenance_minus_planned_minutes"], 1)
        self.assertEqual(groups[("EQ-01", "R-02")]["groups"]["maintenance"]["not_confirmed_events"], 1)

    async def test_case_b_pooled_difference_disappears_with_recipe_comparison(self):
        pooled = await self.compare(dataset="sample_b")
        self.assertEqual(pooled["comparisons"][0]["maintenance_minus_planned_minutes"], 5.2)
        stratified = await self.compare(dataset="sample_b", group_by="recipe_id")
        self.assertTrue(all(row["maintenance_minus_planned_minutes"] == 0 for row in stratified["comparisons"]))
        group = next(row for row in stratified["comparisons"] if row["conditions"]["recipe_id"] == "R-01")
        self.assertEqual(group["groups"]["planned_start"]["total_events"], 7)
        self.assertEqual(group["groups"]["maintenance"]["total_events"], 3)

    async def test_ems_alone_has_computed_repeat_work_evidence(self):
        result = await self.read()
        group = next(row for row in result["work_groups"] if row["equipment_id"] == "EQ-01")
        self.assertEqual(group["work_count"], 5)
        self.assertEqual(group["total_work_minutes"], 150)
        self.assertEqual(len(group["record_ids"]), group["work_count"])

    async def test_return_mutation_does_not_change_later_evidence(self):
        first = await self.read("fdc", event_id="sample_a-01")
        first["records"][0]["records"][0]["value"] = -9999
        fresh = await self.read("fdc", event_id="sample_a-01")
        self.assertNotEqual(fresh["records"][0]["records"][0]["value"], -9999)


if __name__ == "__main__":
    unittest.main()
