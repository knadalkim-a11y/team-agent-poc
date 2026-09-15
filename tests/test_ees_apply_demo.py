"""Operator entry tests use a local synthetic HTTP API; no WebUI or credentials."""

import argparse
from contextlib import contextmanager, nullcontext, redirect_stderr, redirect_stdout
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from scripts import ees_apply_demo as demo


TOKEN = "synthetic-webui-token"
HEAD = "a" * 40


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.respond()

    def do_POST(self):
        self.respond()

    def respond(self):
        length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(length)
        self.server.seen.append((self.command, self.path, self.headers.get("Authorization"), data))
        if self.path == "/api/redirect":
            self.send_response(302)
            self.send_header("Location", "http://example.invalid/api/secret")
            self.end_headers()
            return
        status = 404 if self.path == "/api/missing" else 500 if self.path == "/api/fail" else 200
        if self.path.startswith(demo.assets.ASSET_API + "/"):
            status = getattr(self.server, "asset_status", 503)
        payload = ({"version": "0.11.3+ees.9"} if self.path == "/api/version"
                   else {"role": "admin"} if self.path == "/api/v1/auths/"
                   else {"id": "existing", "base_model_id": "base", "params": {"system": "user text"}, "write_access": True}
                   if self.path == "/api/v1/models/model?id=existing"
                   else {"private": TOKEN} if status >= 400
                   else {"received": json.loads(data) if data else None})
        raw = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class WebUIHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.server.seen = []
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self):
        self.server.seen.clear()
        self.server.asset_status = 503
        self.client = demo.WebUIClient(self.url, TOKEN, timeout=2)

    def test_json_utf8_and_bearer_request(self):
        value = {"params": {"system": "기존 지침\n추가 지침"}, "id": "existing"}
        self.assertEqual(self.client.request("POST", "/api/echo", value), {"received": value})
        self.assertEqual(self.server.seen[0][2], "Bearer " + TOKEN)

    def test_redirect_never_follows_or_exposes_credentials(self):
        with self.assertRaisesRegex(demo.DemoError, "redirect_blocked"):
            self.client.request("GET", "/api/redirect")
        self.assertEqual(len(self.server.seen), 1)

    def test_only_get_404_means_absent_and_raw_error_stays_private(self):
        self.assertIsNone(self.client.request("GET", "/api/missing"))
        for method, path in [("POST", "/api/missing"), ("GET", "/api/fail")]:
            with self.assertRaises(demo.DemoError) as raised:
                self.client.request(method, path, {} if method == "POST" else None)
            self.assertNotIn(TOKEN, str(raised.exception))

    def test_conditional_conflict_and_unavailable_are_safe_typed_errors(self):
        for status, code in ((409, "concurrent_edit"), (404, "conditional_write_unavailable"),
                             (405, "conditional_write_unavailable"), (503, "conditional_write_unavailable")):
            with self.subTest(status=status):
                self.server.asset_status = status
                with self.assertRaisesRegex(demo.DemoError, code) as raised:
                    self.client.request("POST", demo.assets.ASSET_API + "/apply", {"kind": "tool", "id": "test"})
                self.assertNotIn(TOKEN, str(raised.exception))
        self.assertTrue(all(path == demo.assets.ASSET_API + "/apply" for _, path, _, _ in self.server.seen))

    def test_response_size_and_url_boundaries(self):
        with patch.object(demo, "MAX_RESPONSE", 4):
            with self.assertRaisesRegex(demo.DemoError, "api_response_too_large"):
                self.client.request("GET", "/api/version")
        for path in ["https://example.invalid/api", "//example.invalid/api", "/api/../secret"]:
            with self.assertRaisesRegex(demo.DemoError, "api_path_invalid"):
                self.client.request("GET", path)
        for url in ["http://user:secret@example.invalid", "http://localhost?x=1", "file:///tmp/demo"]:
            with self.assertRaisesRegex(demo.DemoError, "webui_url_invalid"):
                demo.base_url(url)

    def test_apply_uses_version_then_admin_then_core_without_server_control(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {"host": "127.0.0.1", "port": self.server.server_port, "state_root": directory}
            args = argparse.Namespace(webui_url=None, ees_model_id="existing", ca_file=None, reset_token=False)
            progress = {}
            with (patch.object(demo.upgrade.manager, "locked", return_value=nullcontext()),
                  patch.object(demo.upgrade, "checkout"),
                  patch.object(demo, "load_token", return_value=(TOKEN, False)),
                  patch.object(demo.assets, "apply_assets", return_value={"changed": 8, "source_commit": HEAD}) as core,
                  patch.object(demo.upgrade.manager, "stop_registered") as stop,
                  patch.object(demo.upgrade.manager, "start_selected") as start):
                result = demo.apply(config, args, HEAD, progress)
            self.assertEqual(result["next"], "new_chat")
            self.assertEqual([v[1] for v in self.server.seen], ["/api/version", "/api/v1/auths/", "/api/v1/models/model?id=existing"])
            self.assertIsNone(self.server.seen[0][2])
            self.assertEqual(core.call_args.args[3:], ("existing", HEAD))
            saved = json.loads((Path(directory) / "demo-connection.json").read_text(encoding="utf-8"))
            self.assertNotIn(TOKEN, json.dumps(saved))
            stop.assert_not_called()
            start.assert_not_called()

    def test_first_application_failure_keeps_validated_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {"host": "127.0.0.1", "port": self.server.server_port, "state_root": directory}
            args = argparse.Namespace(webui_url=None, ees_model_id="existing", ca_file=None, reset_token=False)
            with (patch.object(demo.upgrade.manager, "locked", return_value=nullcontext()),
                  patch.object(demo.upgrade, "checkout"),
                  patch.object(demo, "load_token", return_value=(TOKEN, False)),
                  patch.object(demo.assets, "apply_assets", side_effect=demo.DemoError("api_request_failed"))):
                with self.assertRaises(demo.DemoError):
                    demo.apply(config, args, HEAD, {})
            saved = json.loads(Path(directory, "demo-connection.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["ees_model_id"], "existing")
            self.assertEqual(saved["url"], self.url)


class PromptFrontendContractTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node is required to execute the upstream frontend expression")
    def test_model_payload_changes_the_actual_frontend_suggestions(self):
        manifest = demo.assets.load_manifest(Path(__file__).resolve().parents[1])
        item = manifest["ees"]
        expected, retired = item["suggestions"], item["retired_suggestions"]
        current = {"id": "existing-ees", "name": "EES 통합 Assistant",
                   "base_model_id": "synthetic-base", "params": {"system": ""},
                   "meta": {"suggestion_prompts": retired, "suggestionPrompts": expected},
                   "access_grants": [], "is_active": True}
        previous = {"tool_ids": item["tool_ids"], "suggestions": expected}
        updated = demo.assets._merge_model(current, item, True, previous)
        # The return expression is copied verbatim from Open WebUI 0.11.3:
        # https://github.com/open-webui/open-webui/blob/2a960a59fe1dbbd35282f0556b3666d81102e781/src/lib/components/chat/Placeholder.svelte#L283-L286
        # Keep this consumer contract independent of the writer/state key. The
        # API accepts unknown metadata, so payload echo tests missed this bug.
        consumer = """
const input = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
function suggestions(meta) {
    const atSelectedModel = null;
    const models = [{info: {meta}}];
    const selectedModelIdx = 0;
    const $config = {default_prompt_suggestions: input.retired};
    return atSelectedModel?.info?.meta?.suggestion_prompts ??
        models[selectedModelIdx]?.info?.meta?.suggestion_prompts ??
        $config?.default_prompt_suggestions ??
        [];
}
process.stdout.write(JSON.stringify({
    before: suggestions(input.before),
    after: suggestions(input.after),
    camelOnly: suggestions({suggestionPrompts: input.expected})
}));
"""
        result = subprocess.run([shutil.which("node"), "-e", consumer],
                                input=json.dumps({"before": current["meta"], "after": updated["meta"],
                                                  "retired": retired, "expected": expected}),
                                capture_output=True, text=True, encoding="utf-8", check=True, timeout=10)
        visible = json.loads(result.stdout)
        self.assertEqual(visible["before"], retired)
        self.assertEqual(visible["camelOnly"], retired)
        self.assertEqual(visible["after"], expected)
        self.assertEqual(len(visible["after"]), 3)


class OperatorTests(unittest.TestCase):
    def test_token_storage_is_dpapi_and_scoped_to_webui_url(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {"state_root": directory}
            url = "http://127.0.0.1:8080"
            with patch.object(demo.upgrade.manager.states, "_protect", return_value=b"CIPHERTEXT") as protect:
                demo.save_token(config, url, TOKEN)
            plaintext = json.loads(protect.call_args.args[0])
            self.assertEqual(plaintext, {"url": url, "token": TOKEN})
            self.assertEqual(demo.token_path(config, url).read_bytes(), b"CIPHERTEXT")
            with patch.object(demo.upgrade.manager.states, "_unprotect", return_value=json.dumps(plaintext).encode()):
                self.assertEqual(demo.load_token(config, url), (TOKEN, False))
            self.assertNotEqual(demo.token_path(config, url), demo.token_path(config, url + "/other"))
            self.assertFalse((Path(directory) / "github-update.dpapi").exists())

    def test_model_list_pagination_and_unique_existing_ees(self):
        client = Mock()
        client.request.side_effect = [
            {"items": [{"id": "a", "name": "A", "base_model_id": "base"},
                       {"id": "b", "name": "B", "base_model_id": "base"}], "total": 3},
            {"items": [{"id": "kept", "name": "EES 통합 Assistant", "base_model_id": "base"}], "total": 3}]
        self.assertEqual(demo.select_ees(client), "kept")
        self.assertEqual(client.request.call_count, 2)

    def test_ambiguous_models_require_one_selection(self):
        client = Mock()
        client.request.return_value = {"items": [
            {"id": "a", "name": "EES 통합 Assistant", "base_model_id": "base"},
            {"id": "b", "name": "EES 통합 Assistant", "base_model_id": "base"}], "total": 2}
        with patch.object(demo.sys.stdin, "isatty", return_value=False):
            with self.assertRaisesRegex(demo.DemoError, "ees_model_selection_required"):
                demo.select_ees(client)

    def test_connection_override_does_not_reuse_other_servers_model(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {"state_root": directory, "host": "127.0.0.1", "port": 8080}
            Path(directory, "demo-connection.json").write_text(json.dumps({"url": "http://127.0.0.1:8080", "ees_model_id": "old"}), encoding="utf-8")
            _, value = demo.connection(config, argparse.Namespace(webui_url="https://example.invalid", ees_model_id=None, ca_file=None))
            self.assertIsNone(value["ees_model_id"])

    def test_version_or_admin_failure_cannot_write_assets(self):
        for responses, code in [([{"version": "9.0"}], "unsupported_webui_version"),
                                ([{"version": "0.11.3"}, {"role": "user"}], "webui_administrator_required")]:
            with tempfile.TemporaryDirectory() as directory:
                config = {"state_root": directory, "host": "127.0.0.1", "port": 8080}
                args = argparse.Namespace(webui_url=None, ees_model_id="existing", ca_file=None, reset_token=False)
                client = Mock()
                client.request.side_effect = responses
                with (patch.object(demo.upgrade.manager, "locked", return_value=nullcontext()),
                      patch.object(demo.upgrade, "checkout"),
                      patch.object(demo, "WebUIClient", return_value=client),
                      patch.object(demo, "load_token", return_value=(TOKEN, False)),
                      patch.object(demo.assets, "apply_assets") as core):
                    with self.assertRaisesRegex(demo.DemoError, code):
                        demo.apply(config, args, HEAD, {})
                core.assert_not_called()

    def test_guard_unavailable_reports_program_upgrade_and_zero_changes(self):
        output = io.StringIO()
        with (patch.object(demo.upgrade.manager.states, "load_config", return_value={}),
              patch.object(demo.upgrade, "checkout"), patch.object(demo.upgrade, "github_client"),
              patch.object(demo.upgrade, "bootstrap", return_value=(None, HEAD, None)),
              patch.object(demo, "apply", side_effect=demo.assets.DemoAssetsError("conditional_write_unavailable")),
              patch.object(demo.upgrade.manager, "save_operation", return_value=True), redirect_stdout(output)):
            self.assertEqual(1, demo.main(["--config", "synthetic.json"]))
        self.assertIn("code=conditional_write_unavailable", output.getvalue())
        self.assertIn("next=upgrade", output.getvalue())
        self.assertIn("changed=0", output.getvalue())

    def test_error_report_contains_only_short_labels(self):
        output = io.StringIO()
        with patch.object(demo.upgrade.manager, "save_operation", return_value=True), redirect_stdout(output):
            demo.report(Path("synthetic.json"), {"source_commit": HEAD, "changed": 2,
                        "stage": "apply_assets", "code": "api_request_failed", "next": "inspect_local_result"}, failed=True)
        self.assertEqual(len(output.getvalue().splitlines()), 1)
        self.assertIn("changed=2", output.getvalue())
        self.assertNotIn(TOKEN, output.getvalue())

    def test_unconfirmed_write_is_not_reported_as_zero_changes(self):
        output = io.StringIO()
        with patch.object(demo.upgrade.manager, "save_operation", return_value=True), redirect_stdout(output):
            demo.report(Path("synthetic.json"), {"source_commit": HEAD, "changed": 0,
                        "pending": True, "stage": "apply_assets", "code": "webui_connection_failed",
                        "next": "inspect_local_result"}, failed=True)
        self.assertIn("changed=-", output.getvalue())
        self.assertIn("pending=true", output.getvalue())


@unittest.skipUnless(shutil.which("git"), "Git is required for canonical checkout boundaries")
class TrialSourceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Synthetic Test")
        self.git("config", "user.email", "synthetic@example.invalid")
        self.git("remote", "add", "origin", demo.upgrade.REPOSITORY + ".git")
        (self.repo / "source.txt").write_text("reviewed source\n", encoding="utf-8")
        self.git("add", "source.txt")
        self.git("commit", "-m", "synthetic [skip ci]")
        self.head = self.git("rev-parse", "HEAD")
        self.git("update-ref", "refs/remotes/origin/main", self.head)
        self.root_patch = patch.object(demo.upgrade, "ROOT", self.repo)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def git(self, *arguments):
        return subprocess.run(["git", "-C", str(self.repo), *arguments], capture_output=True,
                              text=True, encoding="utf-8", check=True, timeout=10).stdout.strip()

    def assert_trial_stops(self, code, commit=None):
        with (patch.object(demo.upgrade.manager.states, "load_config", return_value={}),
              patch.object(demo.upgrade, "github_client") as github,
              patch.object(demo.upgrade, "bootstrap") as bootstrap,
              patch.object(demo, "WebUIClient") as webui,
              patch.object(demo, "report") as report, redirect_stdout(io.StringIO())):
            self.assertEqual(1, demo.main(["--config", "synthetic.json", "--trial-commit", commit or self.head]))
        self.assertEqual(report.call_args.args[1]["code"], code)
        self.assertEqual(report.call_args.args[1]["stage"], "trial_source")
        self.assertEqual(report.call_args.args[1]["source_verification"], "local_trial")
        github.assert_not_called()
        bootstrap.assert_not_called()
        webui.assert_not_called()

    def test_trial_clean_main_uses_common_locked_asset_path_without_ci_or_git_update(self):
        state_root = self.root / "state"
        state_root.mkdir()
        config = {"state_root": str(state_root), "host": "127.0.0.1", "port": 8080}
        client = Mock()
        client.request.side_effect = [{"version": "0.11.3+ees.9"}, {"role": "admin"},
                                      {"id": "existing", "base_model_id": "base", "params": {}, "write_access": True}]
        before = self.git("rev-parse", "HEAD")
        with (patch.object(demo.upgrade.manager.states, "load_config", return_value=config),
              patch.object(demo.upgrade.manager, "locked", return_value=nullcontext()) as locked,
              patch.object(demo.upgrade, "github_client") as github,
              patch.object(demo.upgrade, "bootstrap") as bootstrap,
              patch.object(demo.upgrade, "git", wraps=demo.upgrade.git) as git,
              patch.object(demo.upgrade.manager, "read_registry", return_value={"phase": "idle", "customization": {"active": {"source_commit": self.head}}}),
              patch.object(demo.upgrade.manager, "selected_program", return_value=state_root / "program") as selected,
              patch.object(demo, "WebUIClient", return_value=client),
              patch.object(demo, "load_token", return_value=(TOKEN, False)),
              patch.object(demo.assets, "apply_assets", return_value={"changed": 1, "source_commit": self.head}) as core,
              patch.object(demo, "report") as report, redirect_stdout(io.StringIO())):
            self.assertEqual(0, demo.main(["--config", "synthetic.json", "--trial-commit", self.head,
                                           "--ees-model-id", "existing"]))
        locked.assert_called_once_with(config, track_owner=True)
        selected.assert_called_once()
        core.assert_called_once()
        self.assertEqual(core.call_args.args[3:], ("existing", self.head))
        self.assertEqual(report.call_args.args[1]["source_verification"], "local_trial")
        self.assertEqual(report.call_args.args[1]["stage"], "complete")
        self.assertEqual(self.git("rev-parse", "HEAD"), before)
        self.assertEqual(sum(call.args == ("rev-parse", "origin/main") for call in git.call_args_list), 2)
        self.assertFalse(any(call.args[0] in {"fetch", "merge", "checkout", "reset"} for call in git.call_args_list))
        github.assert_not_called()
        bootstrap.assert_not_called()

    def test_trial_rejects_other_repository(self):
        self.git("remote", "set-url", "origin", "https://github.com/another/repo.git")
        self.assert_trial_stops("wrong_repository")

    def test_trial_rejects_non_main_checkout(self):
        self.git("checkout", "-b", "local-feature")
        self.assert_trial_stops("main_required")

    def test_trial_rejects_dirty_tracked_source(self):
        (self.repo / "source.txt").write_text("unreviewed edit\n", encoding="utf-8")
        self.assert_trial_stops("local_changes")

    def test_trial_rejects_wrong_pinned_commit(self):
        self.assert_trial_stops("checkout_changed", HEAD)

    def test_trial_rejects_locally_committed_main_not_matching_fetched_main(self):
        (self.repo / "source.txt").write_text("local commit\n", encoding="utf-8")
        self.git("commit", "-am", "local [skip ci]")
        self.assert_trial_stops("trial_main_mismatch", self.git("rev-parse", "HEAD"))

    def test_trial_rechecks_fetched_identity_inside_existing_operation_lock(self):
        self.git("commit", "--allow-empty", "-m", "second [skip ci]")
        target = self.git("rev-parse", "HEAD")
        self.git("update-ref", "refs/remotes/origin/main", target)

        @contextmanager
        def change_source_under_lock(*args, **kwargs):
            self.git("update-ref", "refs/remotes/origin/main", self.head)
            yield

        with patch.object(demo.upgrade.manager, "locked", side_effect=change_source_under_lock) as locked:
            self.assert_trial_stops("trial_main_mismatch", target)
        locked.assert_called_once_with({}, track_owner=True)

    def test_trial_argument_rejects_abbreviation_and_release_bootstrap_mixing(self):
        for options in (["--trial-commit", self.head[:12]], ["--trial-commit", self.head.upper()],
                        ["--trial-commit", ""], ["--trial-commit", " "],
                        ["--trial-commit", self.head, "--reset-update-token"],
                        ["--trial-commit", self.head, "--prepared-head", self.head, "--wrapper-before", self.head]):
            with self.subTest(options=options), patch.object(demo.upgrade.manager.states, "load_config") as load:
                with self.assertRaises(SystemExit) as raised, redirect_stderr(io.StringIO()):
                    demo.main(["--config", "synthetic.json", *options])
                self.assertEqual(raised.exception.code, 2)
                load.assert_not_called()

    def test_trial_refuses_old_or_missing_program_before_api_or_asset_writes(self):
        for registry in ({"phase": "idle", "customization": {"active": None}},
                         {"phase": "idle", "customization": {"active": {"source_commit": HEAD}}}):
            with (self.subTest(registry=registry),
                  patch.object(demo.upgrade.manager, "locked", return_value=nullcontext()),
                  patch.object(demo.upgrade.manager, "read_registry", return_value=registry),
                  patch.object(demo.upgrade.manager, "selected_program") as selected,
                  patch.object(demo, "WebUIClient") as webui):
                progress = {}
                with self.assertRaisesRegex(demo.DemoError, "trial_program_mismatch"):
                    demo.apply({}, argparse.Namespace(trial_commit=self.head), self.head, progress)
                self.assertEqual(progress["stage"], "trial_program")
            selected.assert_not_called()
            webui.assert_not_called()

    def test_trial_keeps_existing_program_validation_before_api_and_reports_repair_step(self):
        with (patch.object(demo.upgrade.manager.states, "load_config", return_value={}),
              patch.object(demo.upgrade.manager, "locked", return_value=nullcontext()),
              patch.object(demo.upgrade.manager, "read_registry", return_value={"phase": "idle", "customization": {"active": {"source_commit": self.head}}}),
              patch.object(demo.upgrade.manager, "selected_program", side_effect=demo.upgrade.manager.DeploymentError("incomplete program")),
              patch.object(demo, "WebUIClient") as webui,
              patch.object(demo, "report") as report, redirect_stdout(io.StringIO())):
            self.assertEqual(1, demo.main(["--config", "synthetic.json", "--trial-commit", self.head]))
        webui.assert_not_called()
        self.assertEqual(report.call_args.args[1]["stage"], "trial_program")
        self.assertEqual(report.call_args.args[1]["next"], "apply_trial_program")

    def test_trial_refuses_incomplete_operation_or_uncertain_launch_before_api(self):
        for status in ({"phase": "switching"}, {"phase": "recovery_required"},
                       {"phase": "idle", "pending": {"source_commit": self.head}},
                       {"phase": "idle", "launch_uncertain": True}):
            registry = {"customization": {"active": {"source_commit": self.head}}, **status}
            with (self.subTest(status=status),
                  patch.object(demo.upgrade.manager.states, "load_config", return_value={}),
                  patch.object(demo.upgrade.manager, "locked", return_value=nullcontext()),
                  patch.object(demo.upgrade.manager, "read_registry", return_value=registry),
                  patch.object(demo.upgrade.manager, "selected_program") as selected,
                  patch.object(demo, "WebUIClient") as webui,
                  patch.object(demo, "report") as report, redirect_stdout(io.StringIO())):
                self.assertEqual(1, demo.main(["--config", "synthetic.json", "--trial-commit", self.head]))
            selected.assert_not_called()
            webui.assert_not_called()
            self.assertEqual(report.call_args.args[1]["stage"], "trial_program")
            self.assertEqual(report.call_args.args[1]["next"], "apply_trial_program")

    def test_default_still_requires_ci_and_does_not_fall_back_to_trial(self):
        def ci_failure(config, args, client, progress, **kwargs):
            progress["stage"] = "ci_check"
            raise demo.upgrade.UpgradeError("ci_not_successful")

        with (patch.object(demo.upgrade.manager.states, "load_config", return_value={}),
              patch.object(demo.upgrade, "github_client") as github,
              patch.object(demo.upgrade, "bootstrap", side_effect=ci_failure) as bootstrap,
              patch.object(demo, "trial_checkout") as trial,
              patch.object(demo, "apply") as apply,
              patch.object(demo, "report") as report, redirect_stdout(io.StringIO())):
            self.assertEqual(1, demo.main(["--config", "synthetic.json"]))
        github.assert_called_once()
        bootstrap.assert_called_once()
        trial.assert_not_called()
        apply.assert_not_called()
        self.assertEqual(report.call_args.args[1]["next"], "check_ci")
        self.assertNotIn("source_verification", report.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
