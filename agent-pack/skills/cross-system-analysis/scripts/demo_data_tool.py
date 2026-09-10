"""
title: EES Demo Data
description: Synthetic EMS/APC/FDC observations and bounded comparisons. No production connection.
version: 0.1.2
required_open_webui_version: 0.11.3
ees_demo_pack: ees-demo-v1
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from statistics import mean
from uuid import uuid4

from pydantic import BaseModel, Field


_DOMAINS = {"ees_demo_ems": "EMS", "ees_demo_apc": "APC", "ees_demo_fdc": "FDC"}
_DATASETS = ("sample_a", "sample_b")
_RECIPES = {
    "R-01": {"APC": (0.8, 1.2), "FDC": (8.0, 12.0)},
    "R-02": {"APC": (1.8, 2.2), "FDC": (18.0, 22.0)},
}
_UNITS = {"APC": "mm (시연 보정량)", "FDC": "시연 신호 단위"}
PANEL_SCRIPT = ""  # ApplyDemo embeds the reviewed, fixed cooperation panel script.
PANEL_SEND_TIMEOUT = 0.25


async def _panel(emitter, state, phase, result=None, error=None):
    """Publish only comparison arguments/results, never caller metadata."""
    state["seq"] += 1
    if not PANEL_SCRIPT or not emitter or not state["chat_id"] or not state["message_id"]:
        return
    try:
        snapshot = {**state, "phase": phase, "error": error}
        if result is not None:
            snapshot["result"] = result
        code = "const eesPanelUpdate=" + json.dumps(snapshot, ensure_ascii=True) + ";\n" + PANEL_SCRIPT
        await asyncio.wait_for(emitter({"type": "execute", "data": {"code": code}}),
                               timeout=PANEL_SEND_TIMEOUT)
    except Exception:
        # A cancelled parent must stay cancelled; UI errors are optional.
        pass


def _error(code, message):
    return {"ok": False, "demo": True, "error": {"code": code, "message": message}}


def _time(value):
    return value.isoformat(timespec="seconds")


def _fixtures(dataset):
    """Deterministic observations; outcome expectations live in tests, not replies."""
    if dataset == "sample_a":
        specifications = [
            ("EQ-01", "R-01", "planned_start", 3, 3, ""),
            ("EQ-01", "R-01", "planned_start", 4, 4, ""),
            ("EQ-01", "R-01", "maintenance", 3, 3, ""),
            ("EQ-01", "R-01", "maintenance", 4, 4, ""),
            ("EQ-01", "R-02", "planned_start", 4, 4, ""),
            ("EQ-01", "R-02", "planned_start", 5, 5, ""),
            ("EQ-01", "R-02", "maintenance", 16, 18, ""),
            ("EQ-01", "R-02", "maintenance", 18, 20, ""),
            ("EQ-02", "R-02", "planned_start", 4, 4, ""),
            ("EQ-02", "R-02", "maintenance", 5, 5, ""),
            ("EQ-02", "R-01", "planned_start", 3, 3, ""),
            ("EQ-02", "R-01", "maintenance", 4, 4, ""),
            ("EQ-01", "R-02", "maintenance", 31, 31, ""),
            ("EQ-02", "R-01", "maintenance", 3, 3, "missing"),
            ("EQ-02", "R-02", "planned_start", 18, 18, "interrupted"),
        ]
    else:
        specifications = []
        for restart_type, recipes in (
            ("planned_start", ["R-01"] * 6 + ["R-02"] * 2),
            ("maintenance", ["R-01"] * 2 + ["R-02"] * 6),
        ):
            for recipe in recipes:
                first = 3 if recipe == "R-01" else 16
                specifications.append(("EQ-01", recipe, restart_type, first, first, ""))
        for recipe in _RECIPES:
            for restart_type in ("planned_start", "maintenance"):
                first = 3 if recipe == "R-01" else 16
                specifications.append(("EQ-02", recipe, restart_type, first, first, ""))
    events = []
    start = datetime(2026, 8, 1, 8, tzinfo=timezone.utc)
    for index, (equipment, recipe, restart_type, apc_first, fdc_first, gap) in enumerate(specifications, 1):
        resumed = start + timedelta(hours=index - 1)
        event_id = f"{dataset}-{index:02d}"
        event = {
            "event_id": event_id, "site_id": "DEMO-SITE", "equipment_id": equipment,
            "recipe_id": recipe, "resumed_at": _time(resumed),
            "restart_type": restart_type, "records": {},
        }
        maintenance = restart_type == "maintenance"
        event["records"]["EMS"] = {
            "record_id": f"EMS-{event_id}",
            "work_started_at": _time(resumed - timedelta(minutes=35)) if maintenance else None,
            "work_completed_at": _time(resumed - timedelta(minutes=5)) if maintenance else None,
            "work_description": "가이드롤러 교체" if maintenance and equipment == "EQ-01" else (
                "노즐 청소" if maintenance else "계획된 생산 시작"),
            "work_status": "완료" if maintenance else "해당 없음",
        }
        for domain, first in (("APC", apc_first), ("FDC", fdc_first)):
            lower, upper = _RECIPES[recipe][domain]
            baseline = (lower + upper) / 2
            records = []
            for minute in range(1, 31):
                if gap == "missing" and domain == "FDC" and minute == 10:
                    continue
                if gap == "interrupted" and minute > 12:
                    continue
                offset = 0.04 if domain == "APC" else 0.2
                value = baseline + (-offset if minute % 2 else offset)
                if minute < first:
                    value = upper + (0.15 if domain == "APC" else 0.8)
                records.append({
                    "record_id": f"{domain}-{event_id}-{minute:02d}",
                    "observed_at": _time(resumed + timedelta(minutes=minute)),
                    "value": round(value, 3),
                })
            event["records"][domain] = records
        # A small unrelated setting change is ordinary evidence, never an outcome label.
        event["setting_revision"] = "rev-2" if equipment == "EQ-02" else "rev-1"
        events.append(event)
    return events


def _identity(event):
    return {key: event[key] for key in (
        "event_id", "site_id", "equipment_id", "recipe_id", "resumed_at"
    )}


def _domain_view(event, domain, detailed=False):
    result = _identity(event)
    if domain == "EMS":
        result.update(event["records"][domain])
        result["restart_type"] = event["restart_type"]
        result["work_minutes"] = (
            (datetime.fromisoformat(result["work_completed_at"]) -
             datetime.fromisoformat(result["work_started_at"])).total_seconds() / 60
            if result["work_started_at"] else None
        )
        return result
    records = event["records"][domain]
    lower, upper = _RECIPES[event["recipe_id"]][domain]
    values = [row["value"] for row in records]
    result.update({
        "unit": _UNITS[domain], "allowed_range": [lower, upper],
        "expected_samples": 30, "observed_samples": len(records),
        "outside_range_samples": sum(not lower <= value <= upper for value in values),
        "mean": round(mean(values), 4), "min": min(values), "max": max(values),
        "source_records": [records[0]["record_id"], records[-1]["record_id"]],
        "source_record_scope": "first_and_last_only",
    })
    if domain == "APC":
        result["setting_revision"] = event["setting_revision"]
    if detailed:
        result["records"] = records
    return result


def _joint_observation(event):
    """Require a complete 30 minute paired observation and five aligned samples."""
    resumed = datetime.fromisoformat(event["resumed_at"])
    expected = [_time(resumed + timedelta(minutes=minute)) for minute in range(1, 31)]
    maps = {domain: {row["observed_at"]: row for row in event["records"][domain]}
            for domain in ("APC", "FDC")}
    result = {**_identity(event), "restart_type": event["restart_type"],
              "state": "unassessable", "confirmed_after_minutes": None,
              "confirmation_at": None, "evidence_record_ids": [event["records"]["EMS"]["record_id"]]}
    missing = {domain: sum(stamp not in maps[domain] for stamp in expected) for domain in maps}
    result["missing_samples"] = missing
    if any(missing.values()):
        result["reason"] = "incomplete_observation"
        return result
    streak = []
    for minute, stamp in enumerate(expected, 1):
        paired = [maps[domain][stamp] for domain in ("APC", "FDC")]
        in_range = all(_RECIPES[event["recipe_id"]][domain][0] <= row["value"] <=
                       _RECIPES[event["recipe_id"]][domain][1]
                       for domain, row in zip(("APC", "FDC"), paired))
        streak = streak + paired if in_range else []
        if len(streak) == 10:
            result.update({"state": "confirmed", "confirmed_after_minutes": minute,
                           "confirmation_at": stamp,
                           "evidence_record_ids": result["evidence_record_ids"] +
                               [row["record_id"] for row in streak]})
            return result
    result["state"] = "not_confirmed_within_window"
    return result


def _summary(rows):
    confirmed = [row["confirmed_after_minutes"] for row in rows if row["state"] == "confirmed"]
    assessable = sum(row["state"] != "unassessable" for row in rows)
    return {
        "total_events": len(rows), "assessable_events": assessable,
        "confirmed_events": len(confirmed),
        "not_confirmed_events": sum(row["state"] == "not_confirmed_within_window" for row in rows),
        "unassessable_events": len(rows) - assessable,
        "mean_confirmed_minutes": round(mean(confirmed), 3) if confirmed else None,
        "mean_denominator": len(confirmed),
        "event_ids": [row["event_id"] for row in rows],
    }


class Tools:
    class Valves(BaseModel):
        ees_model_id: str = Field(default="", description="기존 EES Workspace 모델 ID. ApplyDemo가 설정합니다.")

    def __init__(self):
        self.valves = self.Valves()

    def _role(self, metadata):
        if not isinstance(metadata, dict):
            return None
        model_id = metadata.get("model_id")
        if not isinstance(model_id, str):
            return None
        if model_id in _DOMAINS:
            return _DOMAINS[model_id]
        if self.valves.ees_model_id and model_id == self.valves.ees_model_id:
            return "EES"
        return None

    @staticmethod
    def _select(dataset, equipment_id, recipe_id, event_ids):
        if dataset not in _DATASETS:
            return _error("invalid_dataset", "자료는 sample_a 또는 sample_b를 선택해 주세요.")
        if equipment_id and equipment_id not in ("EQ-01", "EQ-02"):
            return _error("invalid_equipment", "시연 설비는 EQ-01 또는 EQ-02입니다.")
        if recipe_id and recipe_id not in _RECIPES:
            return _error("invalid_recipe", "시연 레시피는 R-01 또는 R-02입니다.")
        events = _fixtures(dataset)
        known = {event["event_id"] for event in events}
        if any(event_id not in known for event_id in event_ids):
            return _error("invalid_event", "해당 자료의 실제 event_id를 사용해 주세요.")
        return [event for event in events if
                (not equipment_id or event["equipment_id"] == equipment_id) and
                (not recipe_id or event["recipe_id"] == recipe_id) and
                (not event_ids or event["event_id"] in event_ids)]

    async def read_demo_data(self, dataset: str = "sample_a", equipment_id: str = "",
                             recipe_id: str = "", event_id: str = "", __metadata__=None) -> dict:
        """Read this specialist's synthetic records. Default: summaries; event_id: full samples.

        :param dataset: Synthetic dataset ID: sample_a or sample_b.
        :param equipment_id: Optional equipment ID, EQ-01 or EQ-02.
        :param recipe_id: Optional recipe ID, R-01 or R-02.
        :param event_id: Optional event ID from a previous result for detailed records.
        """
        domain = self._role(__metadata__)
        if domain not in _DOMAINS.values():
            return _error("domain_not_allowed", "전문 Assistant에서 담당 자료를 확인해 주세요.")
        count = __metadata__.get("ees_demo_data_calls", 0)
        if type(count) is not int or count < 0 or count >= 3:
            return _error("query_limit", "이번 전문 분석의 자료 확인 한도에 도달했습니다. 확보한 근거로 답변해 주세요.")
        __metadata__["ees_demo_data_calls"] = count + 1
        if any(not isinstance(value, str) or len(value) > 80
               for value in (dataset, equipment_id, recipe_id, event_id)):
            return _error("invalid_filters", "조회 조건은 80자 이내의 문자열로 입력해 주세요.")
        events = self._select(dataset, equipment_id, recipe_id, [event_id] if event_id else [])
        if isinstance(events, dict):
            return events
        records = [_domain_view(event, domain, bool(event_id)) for event in events]
        result = {
            "ok": True, "demo": True, "dataset": dataset, "domain": domain,
            "time_basis": "UTC; 생산 재개 후 1~30분, 1분 간격",
            "join_keys": ["site_id", "equipment_id", "event_id", "recipe_id", "resumed_at"],
            "message": "합성 시연 자료이며 실제 사내 조회가 아닙니다.",
            "records": records,
            "record_count": len(events), "remaining_queries": 2 - count,
        }
        if domain == "EMS":
            work_groups = {}
            for row in records:
                if row["restart_type"] == "maintenance":
                    work_groups.setdefault((row["equipment_id"], row["work_description"]), []).append(row)
            result["work_groups"] = [
                {"equipment_id": key[0], "work_description": key[1], "work_count": len(rows),
                 "total_work_minutes": sum(row["work_minutes"] for row in rows),
                 "record_ids": [row["record_id"] for row in rows]}
                for key, rows in work_groups.items()
            ]
        return result

    async def compare_demo_data(self, dataset: str = "sample_a", group_by: str = "overall",
                                equipment_id: str = "", recipe_id: str = "", event_ids: str = "",
                                __metadata__=None, __event_emitter__=None) -> dict:
        """Compute paired observations for EES using synthetic records; no causal conclusion.

        :param dataset: Synthetic dataset ID: sample_a or sample_b.
        :param group_by: Comparison grouping: overall, equipment_id, recipe_id, equipment_recipe.
        :param equipment_id: Optional equipment ID, EQ-01 or EQ-02.
        :param recipe_id: Optional recipe ID, R-01 or R-02.
        :param event_ids: Optional comma-separated event IDs returned by specialist analyses.
        """
        if self._role(__metadata__) != "EES":
            return _error("comparison_not_allowed", "종합 비교는 EES에서 수행합니다. 담당 자료 근거를 반환해 주세요.")
        if any(not isinstance(value, str) or len(value) > maximum for value, maximum in
               ((dataset, 80), (group_by, 80), (equipment_id, 80), (recipe_id, 80), (event_ids, 1000))):
            return _error("invalid_filters", "비교 조건 형식을 확인해 주세요.")
        call_id = str(uuid4())
        state = {"version": 1, "kind": "comparison", "call_id": call_id, "batch_id": call_id,
                 "seq": 0, "arguments": {"dataset": dataset, "group_by": group_by,
                     "equipment_id": equipment_id, "recipe_id": recipe_id, "event_ids": event_ids}}
        for key in ("chat_id", "message_id"):
            value = __metadata__.get(key)
            state[key] = value if isinstance(value, str) and len(value) <= 200 else ""
        result = None
        try:
            await _panel(__event_emitter__, state, "requested")
            await _panel(__event_emitter__, state, "querying")
            result = self._compare(dataset, group_by, equipment_id, recipe_id, event_ids)
            await _panel(__event_emitter__, state, "completed" if result["ok"] else "failed",
                         result, (result.get("error") or {}).get("code"))
        except asyncio.CancelledError:
            # If calculation already finished, preserve its real outcome even
            # when cancellation arrives during the optional final UI emission.
            phase = ("completed" if result["ok"] else "failed") if result is not None else "cancelled"
            await _panel(__event_emitter__, state, phase, result,
                         (result.get("error") or {}).get("code") if result is not None else "cancelled")
            raise
        except Exception:
            result = _error("comparison_failed", "교차 계산을 완료하지 못했습니다. 확보된 전문 근거를 사용해 주세요.")
            await _panel(__event_emitter__, state, "failed", result, "comparison_failed")
        return result

    @staticmethod
    def _compare(dataset, group_by, equipment_id, recipe_id, event_ids):
        groupings = {"overall": (), "equipment_id": ("equipment_id",), "recipe_id": ("recipe_id",),
                     "equipment_recipe": ("equipment_id", "recipe_id")}
        if group_by not in groupings:
            return _error("invalid_grouping", "overall, equipment_id, recipe_id, equipment_recipe 중 선택해 주세요.")
        selected = [part.strip() for part in event_ids.split(",") if part.strip()]
        events = Tools._select(dataset, equipment_id, recipe_id, selected)
        if isinstance(events, dict):
            return events
        rows = [_joint_observation(event) for event in events]
        groups = {}
        for row in rows:
            key = tuple(row[field] for field in groupings[group_by])
            groups.setdefault(key, []).append(row)
        comparisons = []
        for key, grouped in groups.items():
            values = {restart_type: _summary([row for row in grouped if row["restart_type"] == restart_type])
                      for restart_type in ("planned_start", "maintenance")}
            left, right = [values[k]["mean_confirmed_minutes"] for k in ("planned_start", "maintenance")]
            comparisons.append({
                "conditions": dict(zip(groupings[group_by], key)), "groups": values,
                "maintenance_minus_planned_minutes": round(right - left, 3)
                    if left is not None and right is not None else None,
            })
        return {
            "ok": True, "demo": True, "dataset": dataset, "group_by": group_by,
            "calculation": {
                "observation_minutes": 30, "sample_interval_minutes": 1,
                "conditions": "같은 시각의 APC와 FDC가 모두 각 레시피 허용 범위 이내",
                "consecutive_samples": 5, "end": "5번째 표본 시각 - 생산 재개 시각",
                "missing_policy": "30분 중 어느 한쪽 표본이 누락되면 판정 불가; 0분으로 치환하지 않음",
                "mean_policy": "5개 연속 표본이 확인된 이벤트만 평균. 미확인·판정 불가 수와 분모는 별도",
            },
            "summary": _summary(rows), "comparisons": comparisons, "events": rows,
            "message": "합성 관측치의 계산 결과입니다. 원인이나 운영 KPI의 타당성을 확정하지 않습니다.",
        }
