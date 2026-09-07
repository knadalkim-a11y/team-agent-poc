"""Synthetic SQLite fixtures; never reads real WebUI data or contacts a server."""

import base64
import contextlib
import hashlib
import importlib.util
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet


SPEC = importlib.util.spec_from_file_location(
    "canary_check", Path(__file__).resolve().parents[1] / "scripts/check_confluence_canary.py"
)
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


class CanaryCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "data").mkdir()
        self.db = self.root / "data/webui.db"
        self.secret = "synthetic-local-key-with-newline\n"
        (self.root / ".webui_secret_key").write_text(self.secret, encoding="utf-8")
        self.fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(self.secret.encode()).digest()))
        with sqlite3.connect(self.db) as db:
            db.execute('CREATE TABLE "user" (settings TEXT)')
            db.execute('CREATE TABLE "tool" (id TEXT PRIMARY KEY, name TEXT)')

    def store(self, stored, tool_id="synthetic-tool"):
        with sqlite3.connect(self.db) as db:
            db.execute('INSERT INTO "user" VALUES (?)',
                       (json.dumps({"tools": {"valves": {tool_id: stored}}}),))

    def encrypted(self, canary=checker.CANARY):
        return self.fernet.encrypt(json.dumps({"PAT": canary}).encode()).decode()

    def jira_tool(self, tool_id="synthetic-jira", name="EES Jira Read"):
        with sqlite3.connect(self.db) as db:
            db.execute('INSERT INTO "tool" VALUES (?, ?)', (tool_id, name))

    def github_tool(self, tool_id="synthetic-github", name="EES GitHub Read"):
        with sqlite3.connect(self.db) as db:
            db.execute('INSERT INTO "tool" VALUES (?, ?)', (tool_id, name))

    def test_encrypted_value_matches_existing_key_and_db_is_unchanged(self):
        self.store(self.encrypted())
        before = self.db.read_bytes()
        result = checker.check(self.root)
        self.assertTrue(result["DatabaseCheckPassed"])
        self.assertEqual(result["EncryptedCanaryMatches"], 1)
        self.assertFalse(result["LogsChecked"])
        self.assertFalse(result["RestartPersistenceChecked"])
        self.assertEqual(before, self.db.read_bytes())
        self.assertNotIn("TargetToolMatches", result)
        self.assertNotIn("TargetEncryptedCanaryMatches", result)

    def test_plaintext_dict_cannot_pass(self):
        self.store({"PAT": checker.CANARY})
        result = checker.check(self.root)
        self.assertFalse(result["DatabaseCheckPassed"])
        self.assertEqual(result["PlaintextCanaryMatches"], 1)
        self.assertTrue(result["PlaintextInDatabaseFiles"])

    def test_wrong_key_and_absent_canary_do_not_pass(self):
        self.assertFalse(checker.check(self.root)["DatabaseCheckPassed"])
        self.store(self.encrypted())
        (self.root / ".webui_secret_key").write_text("another-synthetic-key", encoding="utf-8")
        self.assertFalse(checker.check(self.root)["DatabaseCheckPassed"])

    def test_duplicate_and_mixed_plaintext_records_do_not_pass(self):
        self.store(self.encrypted())
        self.store(self.encrypted())
        self.assertFalse(checker.check(self.root)["DatabaseCheckPassed"])
        self.store({"PAT": checker.CANARY})
        self.assertFalse(checker.check(self.root)["DatabaseCheckPassed"])

    def test_committed_wal_is_read(self):
        keeper = sqlite3.connect(self.db)
        self.addCleanup(keeper.close)
        keeper.execute("PRAGMA journal_mode=WAL")
        keeper.execute("PRAGMA wal_autocheckpoint=0")
        keeper.execute('INSERT INTO "user" VALUES (?)',
                       (json.dumps({"tools": {"valves": {"synthetic-tool": self.encrypted()}}}),))
        keeper.commit()
        result = checker.check(self.root)
        self.assertTrue(result["DatabaseCheckPassed"])
        self.assertGreaterEqual(result["DatabaseFilesChecked"], 2)

    def test_plaintext_residue_in_journal_prevents_pass(self):
        self.store(self.encrypted())
        Path(str(self.db) + "-journal").write_bytes(b"\0" * 512 + checker.CANARY.encode())
        self.assertFalse(checker.check(self.root)["DatabaseCheckPassed"])

    def test_scan_detects_chunk_boundary_and_utf16(self):
        candidate = self.root / "synthetic.bin"
        for encoding in ("utf-8", "utf-16-le", "utf-16-be"):
            candidate.write_bytes(b"x" * 65530 + checker.CANARY.encode(encoding))
            self.assertTrue(checker.contains_canary(candidate, checker.CANARY))

    def test_missing_db_is_not_created(self):
        self.db.unlink()
        with self.assertRaises(ValueError):
            checker.check(self.root)
        self.assertFalse(self.db.exists())

    def test_44_character_fernet_key(self):
        key = Fernet.generate_key()
        (self.root / ".webui_secret_key").write_text(key.decode(), encoding="utf-8")
        self.store(Fernet(key).encrypt(json.dumps({"PAT": checker.CANARY}).encode()).decode())
        self.assertTrue(checker.check(self.root)["DatabaseCheckPassed"])

    def test_error_does_not_disclose_values_or_traceback(self):
        output = io.StringIO()
        with patch.dict("os.environ", {"LOCALAPPDATA": str(self.root)}), \
             patch.object(checker, "version", return_value="0.11.3"), \
             patch.object(checker, "check", side_effect=ValueError("synthetic-secret-do-not-print")), \
             contextlib.redirect_stdout(output):
            self.assertEqual(checker.main([]), 2)
        self.assertEqual(json.loads(output.getvalue()),
                         {"CheckCompleted": False, "Error": "LOCAL_CHECK_FAILED"})

    def test_jira_requires_fresh_marker_under_exact_target_and_preserves_db(self):
        self.jira_tool()
        self.store(self.encrypted())  # Existing Confluence marker is independent.
        self.store(self.encrypted(checker.JIRA_CANARY), "synthetic-jira")
        before = self.db.read_bytes()
        result = checker.check(self.root, jira=True)
        self.assertTrue(result["DatabaseCheckPassed"])
        self.assertEqual(result["EncryptedCanaryMatches"], 1)
        self.assertEqual(result["TargetToolMatches"], 1)
        self.assertEqual(result["TargetEncryptedCanaryMatches"], 1)
        self.assertFalse(result["LogsChecked"])
        self.assertFalse(result["RestartPersistenceChecked"])
        self.assertEqual(before, self.db.read_bytes())
        self.assertTrue(checker.check(self.root)["DatabaseCheckPassed"])

    def test_jira_marker_in_another_tool_cannot_pass(self):
        self.jira_tool()
        self.store(self.encrypted(checker.JIRA_CANARY))
        result = checker.check(self.root, jira=True)
        self.assertEqual(result["EncryptedCanaryMatches"], 1)
        self.assertEqual(result["TargetEncryptedCanaryMatches"], 0)
        self.assertFalse(result["DatabaseCheckPassed"])

    def test_jira_old_marker_in_target_cannot_pass(self):
        self.jira_tool()
        self.store(self.encrypted(), "synthetic-jira")
        self.assertFalse(checker.check(self.root, jira=True)["DatabaseCheckPassed"])

    def test_jira_missing_or_case_mismatched_label_cannot_pass(self):
        self.store(self.encrypted(checker.JIRA_CANARY), "synthetic-jira")
        result = checker.check(self.root, jira=True)
        self.assertEqual(result["TargetToolMatches"], 0)
        self.assertFalse(result["DatabaseCheckPassed"])
        self.jira_tool(name="ees jira read")
        result = checker.check(self.root, jira=True)
        self.assertEqual(result["TargetToolMatches"], 0)
        self.assertFalse(result["DatabaseCheckPassed"])

    def test_jira_duplicate_labels_cannot_pass(self):
        self.jira_tool()
        self.jira_tool(tool_id="synthetic-jira-copy")
        self.store(self.encrypted(checker.JIRA_CANARY), "synthetic-jira")
        result = checker.check(self.root, jira=True)
        self.assertEqual(result["TargetToolMatches"], 2)
        self.assertFalse(result["DatabaseCheckPassed"])

    def test_jira_duplicate_marker_for_same_or_different_tool_cannot_pass(self):
        self.jira_tool()
        for other_tool in ("synthetic-jira", "synthetic-other"):
            with self.subTest(other_tool=other_tool):
                with sqlite3.connect(self.db) as db:
                    db.execute('DELETE FROM "user"')
                self.store(self.encrypted(checker.JIRA_CANARY), "synthetic-jira")
                self.store(self.encrypted(checker.JIRA_CANARY), other_tool)
                result = checker.check(self.root, jira=True)
                self.assertEqual(result["EncryptedCanaryMatches"], 2)
                self.assertFalse(result["DatabaseCheckPassed"])

    def test_jira_plaintext_and_file_residue_cannot_pass(self):
        self.jira_tool()
        self.store({"PAT": checker.JIRA_CANARY}, "synthetic-jira")
        result = checker.check(self.root, jira=True)
        self.assertEqual(result["PlaintextCanaryMatches"], 1)
        self.assertTrue(result["PlaintextInDatabaseFiles"])
        self.assertFalse(result["DatabaseCheckPassed"])
        with sqlite3.connect(self.db) as db:
            db.execute('DELETE FROM "user"')
            db.commit()
            db.execute("VACUUM")
        self.store(self.encrypted(checker.JIRA_CANARY), "synthetic-jira")
        self.assertTrue(checker.check(self.root, jira=True)["DatabaseCheckPassed"])
        Path(str(self.db) + "-journal").write_bytes(b"\0" * 512 + checker.JIRA_CANARY.encode())
        self.assertFalse(checker.check(self.root, jira=True)["DatabaseCheckPassed"])

    def test_jira_committed_wal_target_and_plaintext_are_read(self):
        keeper = sqlite3.connect(self.db)
        self.addCleanup(keeper.close)
        keeper.execute("PRAGMA journal_mode=WAL")
        keeper.execute("PRAGMA wal_autocheckpoint=0")
        keeper.execute('INSERT INTO "tool" VALUES (?, ?)', ("synthetic-jira", "EES Jira Read"))
        keeper.execute('INSERT INTO "user" VALUES (?)', (json.dumps({
            "tools": {"valves": {"synthetic-jira": self.encrypted(checker.JIRA_CANARY)}}
        }),))
        keeper.commit()
        self.assertTrue(checker.check(self.root, jira=True)["DatabaseCheckPassed"])
        keeper.execute('INSERT INTO "user" VALUES (?)',
                       (json.dumps({"note": checker.JIRA_CANARY}),))
        keeper.commit()
        self.assertFalse(checker.contains_canary(self.db, checker.JIRA_CANARY))
        self.assertTrue(checker.contains_canary(Path(str(self.db) + "-wal"), checker.JIRA_CANARY))
        result = checker.check(self.root, jira=True)
        self.assertEqual(result["PlaintextCanaryMatches"], 0)
        self.assertTrue(result["PlaintextInDatabaseFiles"])
        self.assertFalse(result["DatabaseCheckPassed"])

    def test_jira_cli_checks_version_before_reading_and_outputs_only_result(self):
        output = io.StringIO()
        with patch.object(checker, "version", return_value="0.11.2"), \
             patch.object(checker, "check") as check, contextlib.redirect_stdout(output):
            self.assertEqual(checker.main(["--jira"]), 2)
        check.assert_not_called()
        self.assertEqual(json.loads(output.getvalue()),
                         {"CheckCompleted": False, "Error": "UNSUPPORTED_WEBUI_VERSION"})

    def test_jira_cli_uses_fixed_mode_and_suppresses_error_details(self):
        output = io.StringIO()
        with patch.dict("os.environ", {"LOCALAPPDATA": str(self.root)}), \
             patch.object(checker, "version", return_value="0.11.3"), \
             patch.object(checker, "check", side_effect=ValueError("secret-id-url")) as check, \
             contextlib.redirect_stdout(output):
            self.assertEqual(checker.main(["--jira"]), 2)
        check.assert_called_once_with(self.root / "EES-Agent-POC" / "open-webui", jira=True)
        self.assertEqual(json.loads(output.getvalue()),
                         {"CheckCompleted": False, "Error": "LOCAL_CHECK_FAILED"})

    def test_cli_rejects_arbitrary_input_without_echoing_it(self):
        output = io.StringIO()
        with patch.object(checker, "check") as check, contextlib.redirect_stdout(output):
            self.assertEqual(checker.main(["--jira", "synthetic-secret"]), 2)
        check.assert_not_called()
        self.assertEqual(json.loads(output.getvalue()),
                         {"CheckCompleted": False, "Error": "UNSUPPORTED_ARGUMENTS"})

    def test_github_requires_fresh_marker_under_exact_target_and_preserves_db(self):
        self.github_tool()
        self.jira_tool()
        self.store(self.encrypted())
        self.store(self.encrypted(checker.JIRA_CANARY), "synthetic-jira")
        self.store(self.encrypted(checker.GITHUB_CANARY), "synthetic-github")
        before = self.db.read_bytes()
        result = checker.check(self.root, github=True)
        self.assertEqual(result, {
            "CheckCompleted": True,
            "EncryptedCanaryMatches": 1,
            "PlaintextCanaryMatches": 0,
            "PlaintextInDatabaseFiles": False,
            "DatabaseFilesChecked": 1,
            "DatabaseCheckPassed": True,
            "LogsChecked": False,
            "RestartPersistenceChecked": False,
            "TargetToolMatches": 1,
            "TargetEncryptedCanaryMatches": 1,
        })
        self.assertTrue(checker.check(self.root)["DatabaseCheckPassed"])
        self.assertTrue(checker.check(self.root, jira=True)["DatabaseCheckPassed"])
        self.assertEqual(before, self.db.read_bytes())

    def test_github_marker_in_another_tool_cannot_pass(self):
        self.github_tool()
        self.store(self.encrypted(checker.GITHUB_CANARY), "synthetic-jira")
        result = checker.check(self.root, github=True)
        self.assertEqual(result["EncryptedCanaryMatches"], 1)
        self.assertEqual(result["TargetEncryptedCanaryMatches"], 0)
        self.assertFalse(result["DatabaseCheckPassed"])

    def test_github_existing_markers_in_target_cannot_pass(self):
        self.github_tool()
        for marker in (checker.CANARY, checker.JIRA_CANARY):
            with self.subTest(marker=marker):
                self.store(self.encrypted(marker), "synthetic-github")
                result = checker.check(self.root, github=True)
                self.assertEqual(result["EncryptedCanaryMatches"], 0)
                self.assertEqual(result["TargetEncryptedCanaryMatches"], 0)
                self.assertFalse(result["DatabaseCheckPassed"])

    def test_github_missing_or_case_mismatched_label_cannot_pass(self):
        self.store(self.encrypted(checker.GITHUB_CANARY), "synthetic-github")
        result = checker.check(self.root, github=True)
        self.assertEqual(result["TargetToolMatches"], 0)
        self.assertFalse(result["DatabaseCheckPassed"])
        self.github_tool(name="EES Github Read")
        result = checker.check(self.root, github=True)
        self.assertEqual(result["TargetToolMatches"], 0)
        self.assertFalse(result["DatabaseCheckPassed"])

    def test_github_duplicate_labels_cannot_pass(self):
        self.github_tool()
        self.github_tool(tool_id="synthetic-github-copy")
        self.store(self.encrypted(checker.GITHUB_CANARY), "synthetic-github")
        result = checker.check(self.root, github=True)
        self.assertEqual(result["TargetToolMatches"], 2)
        self.assertEqual(result["TargetEncryptedCanaryMatches"], 0)
        self.assertFalse(result["DatabaseCheckPassed"])

    def test_github_duplicate_marker_for_same_or_different_tool_cannot_pass(self):
        self.github_tool()
        for other_tool in ("synthetic-github", "synthetic-other"):
            with self.subTest(other_tool=other_tool):
                with sqlite3.connect(self.db) as db:
                    db.execute('DELETE FROM "user"')
                self.store(self.encrypted(checker.GITHUB_CANARY), "synthetic-github")
                self.store(self.encrypted(checker.GITHUB_CANARY), other_tool)
                result = checker.check(self.root, github=True)
                self.assertEqual(result["EncryptedCanaryMatches"], 2)
                self.assertFalse(result["DatabaseCheckPassed"])

    def test_github_plaintext_in_db_and_journal_cannot_pass(self):
        self.github_tool()
        self.store({"PAT": checker.GITHUB_CANARY}, "synthetic-github")
        result = checker.check(self.root, github=True)
        self.assertEqual(result["PlaintextCanaryMatches"], 1)
        self.assertTrue(result["PlaintextInDatabaseFiles"])
        self.assertFalse(result["DatabaseCheckPassed"])
        with sqlite3.connect(self.db) as db:
            db.execute('DELETE FROM "user"')
            db.commit()
            db.execute("VACUUM")
        self.store(self.encrypted(checker.GITHUB_CANARY), "synthetic-github")
        self.assertTrue(checker.check(self.root, github=True)["DatabaseCheckPassed"])
        Path(str(self.db) + "-journal").write_bytes(b"\0" * 512 + checker.GITHUB_CANARY.encode())
        result = checker.check(self.root, github=True)
        self.assertEqual(result["EncryptedCanaryMatches"], 1)
        self.assertEqual(result["PlaintextCanaryMatches"], 0)
        self.assertTrue(result["PlaintextInDatabaseFiles"])
        self.assertFalse(result["DatabaseCheckPassed"])

    def test_github_committed_wal_target_and_plaintext_are_read(self):
        keeper = sqlite3.connect(self.db)
        self.addCleanup(keeper.close)
        keeper.execute("PRAGMA journal_mode=WAL")
        keeper.execute("PRAGMA wal_autocheckpoint=0")
        keeper.execute('INSERT INTO "tool" VALUES (?, ?)', ("synthetic-github", "EES GitHub Read"))
        keeper.execute('INSERT INTO "user" VALUES (?)', (json.dumps({
            "tools": {"valves": {"synthetic-github": self.encrypted(checker.GITHUB_CANARY)}}
        }),))
        keeper.commit()
        result = checker.check(self.root, github=True)
        self.assertTrue(result["DatabaseCheckPassed"])
        self.assertGreaterEqual(result["DatabaseFilesChecked"], 2)
        keeper.execute('INSERT INTO "user" VALUES (?)',
                       (json.dumps({"note": checker.GITHUB_CANARY}),))
        keeper.commit()
        self.assertFalse(checker.contains_canary(self.db, checker.GITHUB_CANARY))
        self.assertTrue(checker.contains_canary(Path(str(self.db) + "-wal"), checker.GITHUB_CANARY))
        result = checker.check(self.root, github=True)
        self.assertEqual(result["PlaintextCanaryMatches"], 0)
        self.assertTrue(result["PlaintextInDatabaseFiles"])
        self.assertFalse(result["DatabaseCheckPassed"])

    def test_github_cli_checks_version_before_reading(self):
        output = io.StringIO()
        with patch.object(checker, "version", return_value="0.11.2"), \
             patch.object(checker, "check") as check, contextlib.redirect_stdout(output):
            self.assertEqual(checker.main(["--github"]), 2)
        check.assert_not_called()
        self.assertEqual(json.loads(output.getvalue()),
                         {"CheckCompleted": False, "Error": "UNSUPPORTED_WEBUI_VERSION"})

    def test_github_cli_uses_fixed_mode_and_prints_only_counts_and_booleans(self):
        self.github_tool()
        self.store(self.encrypted(checker.GITHUB_CANARY), "synthetic-github")
        expected = checker.check(self.root, github=True)
        output = io.StringIO()
        with patch.dict("os.environ", {"LOCALAPPDATA": str(self.root)}), \
             patch.object(checker, "version", return_value="0.11.3"), \
             patch.object(checker, "check", return_value=expected) as check, \
             contextlib.redirect_stdout(output):
            self.assertEqual(checker.main(["--github"]), 0)
        check.assert_called_once_with(self.root / "EES-Agent-POC" / "open-webui", github=True)
        self.assertEqual(json.loads(output.getvalue()), expected)
        self.assertTrue(all(type(value) in (int, bool) for value in expected.values()))

    def test_github_cli_suppresses_error_details(self):
        output = io.StringIO()
        with patch.dict("os.environ", {"LOCALAPPDATA": str(self.root)}), \
             patch.object(checker, "version", return_value="0.11.3"), \
             patch.object(checker, "check", side_effect=ValueError("secret-id-url")), \
             contextlib.redirect_stdout(output):
            self.assertEqual(checker.main(["--github"]), 2)
        self.assertEqual(json.loads(output.getvalue()),
                         {"CheckCompleted": False, "Error": "LOCAL_CHECK_FAILED"})

    def test_conflicting_check_modes_rejected_before_file_access(self):
        with patch.object(checker, "Path") as path, self.assertRaises(ValueError):
            checker.check(self.root, jira=True, github=True)
        path.assert_not_called()

    def test_cli_conflicts_and_arbitrary_input_rejected_before_version_or_file_access(self):
        for args in (["--jira", "--github"], ["--github", "--jira"],
                     ["--github", "--github"], ["--github", "synthetic-secret"],
                     ["--github=synthetic-secret"], ["--tool", "EES GitHub Read"]):
            with self.subTest(args=args):
                output = io.StringIO()
                with patch.object(checker, "version") as version, \
                     patch.object(checker, "Path") as path, \
                     patch.object(checker, "check") as check, contextlib.redirect_stdout(output):
                    self.assertEqual(checker.main(args), 2)
                version.assert_not_called()
                path.assert_not_called()
                check.assert_not_called()
                self.assertEqual(json.loads(output.getvalue()),
                                 {"CheckCompleted": False, "Error": "UNSUPPORTED_ARGUMENTS"})


if __name__ == "__main__":
    unittest.main()
