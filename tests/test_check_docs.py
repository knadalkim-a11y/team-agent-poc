"""Offline contract tests for the read-only Markdown hygiene checker."""

from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_docs.py"
SPEC = importlib.util.spec_from_file_location("check_docs_under_test", SCRIPT_PATH)
CHECK_DOCS = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CHECK_DOCS
SPEC.loader.exec_module(CHECK_DOCS)


class CheckDocsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="check-docs-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        network_guard = patch("socket.socket.connect", side_effect=AssertionError("Network access is forbidden"))
        network_guard.start()
        self.addCleanup(network_guard.stop)
        self.write("README.md", "# Test repository\n")

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def check(self):
        report = CHECK_DOCS.check_repository(self.root)
        self.assertIsInstance(report["files_checked"], int)
        self.assertIsInstance(report["links_checked"], int)
        for severity in ("errors", "warnings"):
            self.assertIsInstance(report[severity], list)
            for diagnostic in report[severity]:
                self.assertTrue(diagnostic.get("code"), diagnostic)
                self.assertIn("file", diagnostic)
        return report

    def assert_clean(self):
        report = self.check()
        self.assertEqual(report["errors"], [], report)
        return report

    def warning_files(self, report):
        return {str(item["file"]).replace("\\", "/") for item in report["warnings"]}

    def test_empty_repository_has_no_link_errors(self):
        report = self.assert_clean()
        self.assertEqual(report["files_checked"], 1)
        self.assertEqual(report["links_checked"], 0)

    def test_relative_link_and_parent_directory_link(self):
        self.write("README.md", "[Guide](docs/guide.md)\n")
        self.write("docs/guide.md", "[Repository](../README.md)\n")
        report = self.assert_clean()
        self.assertEqual(report["links_checked"], 2)
        self.assertEqual(report["warnings"], [])

    def test_missing_link_target_is_error(self):
        self.write("README.md", "[Missing](docs/missing.md)\n")
        report = self.check()
        self.assertTrue(report["errors"])
        self.assertIn("missing.md", json.dumps(report["errors"]))

    def test_known_heading_fragment(self):
        self.write("README.md", "[Section](docs/guide.md#first-section)\n")
        self.write("docs/guide.md", "# First section\n")
        self.assert_clean()

    def test_missing_heading_fragment_is_error(self):
        self.write("README.md", "[Section](docs/guide.md#not-a-section)\n")
        self.write("docs/guide.md", "# Actual section\n")
        self.assertTrue(self.check()["errors"])

    def test_local_heading_fragment(self):
        self.write("README.md", "# Overview\n[Above](#overview)\n")
        self.assert_clean()

    def test_korean_heading_fragment(self):
        self.write("README.md", "[설치](docs/guide.md#설치-안내)\n")
        self.write("docs/guide.md", "## 설치 안내\n")
        self.assert_clean()

    def test_explicit_html_anchor(self):
        self.write("README.md", "[Evidence](evals/result.md#stable-result)\n")
        self.write("evals/result.md", '<a id="stable-result"></a>\n# Result\n')
        self.assert_clean()

    def test_duplicate_heading_suffix(self):
        self.write("README.md", "[Second](docs/guide.md#repeat-1)\n")
        self.write("docs/guide.md", "# Repeat\n\n# Repeat\n")
        self.assert_clean()

    def test_inline_code_is_not_a_link(self):
        self.write("README.md", "Example: `[Missing](not-created.md)`\n")
        report = self.assert_clean()
        self.assertEqual(report["links_checked"], 0)

    def test_fenced_code_is_not_a_link(self):
        self.write("README.md", "```markdown\n[Missing](absent.md)\n```\n")
        report = self.assert_clean()
        self.assertEqual(report["links_checked"], 0)

    def test_tilde_fence_is_not_a_link(self):
        self.write("README.md", "~~~md\n[Missing](absent.md)\n~~~\n")
        report = self.assert_clean()
        self.assertEqual(report["links_checked"], 0)

    def test_comment_is_not_a_link(self):
        self.write("README.md", "<!--\n[Missing](absent.md)\n-->\n")
        report = self.assert_clean()
        self.assertEqual(report["links_checked"], 0)

    def test_full_reference_link(self):
        self.write("README.md", "[Read guide][guide]\n\n[guide]: docs/guide.md\n")
        self.write("docs/guide.md", "# Guide\n")
        report = self.assert_clean()
        self.assertEqual(report["links_checked"], 1)
        self.assertEqual(report["warnings"], [])

    def test_undefined_full_reference_is_error(self):
        self.write("README.md", "[Read guide][not-defined]\n")
        self.assertTrue(self.check()["errors"])

    def test_percent_encoded_space_in_target(self):
        self.write("README.md", "[Guide](docs/setup%20guide.md)\n")
        self.write("docs/setup guide.md", "# Setup\n")
        self.assert_clean()

    def test_escaped_space_in_target(self):
        self.write("README.md", "[Guide](docs/setup\\ guide.md)\n")
        self.write("docs/setup guide.md", "# Setup\n")
        self.assert_clean()

    def test_image_path_is_checked(self):
        self.write("README.md", "![Diagram](assets/diagram.svg)\n")
        self.write("assets/diagram.svg", '<svg xmlns="http://www.w3.org/2000/svg"/>')
        self.assert_clean()
        self.write("README.md", "![Diagram](assets/missing.svg)\n")
        self.assertTrue(self.check()["errors"])

    def test_image_with_empty_alt_still_checks_target(self):
        self.write("README.md", "![](missing.png)\n")
        report = self.check()
        self.assertTrue(report["errors"])
        self.assertIn("missing.png", json.dumps(report["errors"]))

    def test_data_id_attribute_is_not_an_html_anchor(self):
        self.write("README.md", "[Example](docs/guide.md#fake)\n")
        self.write("docs/guide.md", '<span data-id="fake">Text</span>\n')
        self.assertTrue(self.check()["errors"])

    def test_external_urls_not_requested_or_flagged(self):
        self.write(
            "README.md",
            "[Web](https://example.invalid/missing#missing)\n"
            "[Web](http://example.invalid/missing)\n"
            "[Mail](mailto:team@example.invalid)\n",
        )
        self.assert_clean()

    def test_outside_root_target_rejected_even_when_exists(self):
        with tempfile.TemporaryDirectory(prefix="check-docs-outside-") as outside:
            target = Path(outside) / "outside.md"
            target.write_text("# Outside\n", encoding="utf-8")
            relative = Path("..") / Path(outside).name / target.name
            self.write("README.md", f"[Outside]({relative.as_posix()})\n")
            self.assertTrue(self.check()["errors"])

    def test_unlinked_guide_is_review_warning_only(self):
        self.write("docs/old-guide.md", "# Old guide\n")
        report = self.assert_clean()
        self.assertTrue(any(name.endswith("docs/old-guide.md") for name in self.warning_files(report)))

    def test_unlinked_eval_is_review_warning_not_error(self):
        self.write("evals/old-evidence.md", "# Historical evidence\n")
        report = self.assert_clean()
        self.assertTrue(any(name.endswith("evals/old-evidence.md") for name in self.warning_files(report)))

    def test_disconnected_document_cycle_is_flagged(self):
        self.write("docs/a.md", "[B](b.md)\n")
        self.write("docs/b.md", "[A](a.md)\n")
        report = self.assert_clean()
        warnings = self.warning_files(report)
        self.assertTrue(any(name.endswith("docs/a.md") for name in warnings))
        self.assertTrue(any(name.endswith("docs/b.md") for name in warnings))

    def test_reachable_document_chain_is_not_flagged(self):
        self.write("README.md", "[A](docs/a.md)\n")
        self.write("docs/a.md", "[B](b.md)\n")
        self.write("docs/b.md", "# B\n")
        self.assertEqual(self.assert_clean()["warnings"], [])

    def test_agents_is_additional_entrypoint(self):
        self.write("AGENTS.md", "[Status](docs/STATUS.md)\n")
        self.write("docs/STATUS.md", "# Current status\n")
        self.assertEqual(self.assert_clean()["warnings"], [])

    def test_folder_link_does_not_mark_all_children_reachable(self):
        self.write("README.md", "[Guides](docs/)\n")
        self.write("docs/unlinked.md", "# Unlinked\n")
        report = self.assert_clean()
        self.assertTrue(any(name.endswith("docs/unlinked.md") for name in self.warning_files(report)))

    def test_skills_and_runtime_assets_are_not_unused_candidates(self):
        self.write("agent-pack/skills/example/SKILL.md", "# Skill\n")
        self.write("agent-pack/skills/example/references/reference.md", "# Runtime reference\n")
        self.write("agent-pack/policies/common-policy.md", "# Policy\n")
        report = self.assert_clean()
        self.assertEqual(report["warnings"], [])

    def test_ignored_directories_not_scanned(self):
        for directory in (".git", ".venv", "node_modules", "data", "runtime", "logs", "__pycache__"):
            self.write(f"{directory}/bad.md", "[Broken](missing.md)\n")
        report = self.assert_clean()
        self.assertEqual(report["files_checked"], 1)

    def test_symlinked_document_and_directory_are_not_followed(self):
        with tempfile.TemporaryDirectory(prefix="check-docs-outside-") as outside:
            external = Path(outside)
            (external / "bad.md").write_text("[Broken](missing.md)\n", encoding="utf-8")
            try:
                (self.root / "linked.md").symlink_to(external / "bad.md")
                (self.root / "linked-dir").symlink_to(external, target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"Symlink creation unavailable: {type(exc).__name__}")
            report = self.assert_clean()
            self.assertEqual(report["files_checked"], 1)

    def test_link_to_outside_symlink_rejected(self):
        with tempfile.TemporaryDirectory(prefix="check-docs-outside-") as outside:
            target = Path(outside) / "outside.md"
            target.write_text("# Outside\n", encoding="utf-8")
            try:
                (self.root / "link.md").symlink_to(target)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"Symlink creation unavailable: {type(exc).__name__}")
            self.write("README.md", "[Outside](link.md)\n")
            self.assertTrue(self.check()["errors"])

    def test_resolved_directory_outside_root_is_skipped_synthetic_boundary(self):
        """Synthetic resolve boundary only; this is not a real Windows junction test."""
        redirected = self.root / "junction-like"
        self.write("junction-like/bad.md", "[Must not scan](missing.md)\n")
        real_resolve = Path.resolve
        with tempfile.TemporaryDirectory(prefix="check-docs-resolved-outside-") as outside:
            external = Path(outside)

            def resolve_with_redirect(path, *args, **kwargs):
                if path == redirected:
                    return external
                return real_resolve(path, *args, **kwargs)

            with patch.object(Path, "resolve", new=resolve_with_redirect):
                report = self.assert_clean()
            self.assertEqual(report["files_checked"], 1)
            self.assertTrue(any(name.endswith("junction-like") for name in self.warning_files(report)))

    def test_invalid_root_is_reported(self):
        report = CHECK_DOCS.check_repository(self.root / "not-created")
        self.assertTrue(report["errors"])

    def test_invalid_utf8_document_is_read_error(self):
        path = self.root / "docs" / "unreadable.md"
        path.parent.mkdir()
        path.write_bytes(b"\xff\xfe\xff")
        self.assertTrue(self.check()["errors"])

    def test_checker_preserves_all_file_bytes_and_mtimes(self):
        self.write("README.md", "[Guide](docs/guide.md)\n[Missing](missing.md)\n")
        self.write("docs/guide.md", "# Guide\n")
        self.write("docs/unlinked.md", "# Unlinked\n")
        self.write("data/private.txt", "Do not scan or change.\n")

        def snapshot():
            return {
                path.relative_to(self.root).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
                for path in self.root.rglob("*")
                if path.is_file()
            }

        before = snapshot()
        self.check()
        self.assertEqual(snapshot(), before)

    def test_cli_json_warnings_do_not_fail(self):
        self.write("docs/unlinked.md", "# Review candidate\n")
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = CHECK_DOCS.main(["--root", str(self.root), "--json"])
        self.assertEqual(result, 0)
        report = json.loads(stdout.getvalue())
        self.assertTrue(report["warnings"])
        self.assertEqual(report["errors"], [])

    def test_cli_json_errors_fail(self):
        self.write("README.md", "[Missing](missing.md)\n")
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = CHECK_DOCS.main(["--root", str(self.root), "--json"])
        self.assertEqual(result, 1)
        self.assertTrue(json.loads(stdout.getvalue())["errors"])

    def test_cli_text_link_error_with_line_number(self):
        self.write("README.md", "# Repository\n\n[Missing](missing.md)\n")
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = CHECK_DOCS.main(["--root", str(self.root)])
        self.assertEqual(result, 1)
        self.assertIn("README.md", stdout.getvalue())
        self.assertTrue(stdout.getvalue().strip())

    def test_cli_text_warning_without_line_number(self):
        self.write("docs/unlinked.md", "# Review candidate\n")
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = CHECK_DOCS.main(["--root", str(self.root)])
        self.assertEqual(result, 0)
        self.assertIn("docs/unlinked.md", stdout.getvalue().replace("\\", "/"))

    def test_html_id_in_code_or_comment_is_not_an_anchor(self):
        examples = {
            "fenced": '```html\n<a id="example-id"></a>\n```\n',
            "inline": 'Example: `<a id="example-id"></a>`\n',
            "comment": '<!-- <a id="example-id"></a> -->\n',
        }
        for name, content in examples.items():
            with self.subTest(name=name):
                self.write("README.md", "[Example](docs/guide.md#example-id)\n")
                self.write("docs/guide.md", content)
                self.assertTrue(self.check()["errors"], name)

    def test_cli_missing_root_is_inspection_error_not_usage_error(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = CHECK_DOCS.main(["--root", str(self.root / "absent"), "--json"])
        self.assertEqual(result, 1)
        self.assertTrue(json.loads(stdout.getvalue())["errors"])

    def test_document_over_one_mebibyte_is_bounded_read_error(self):
        self.write("docs/oversized.md", "x" * (1024 * 1024 + 1))
        report = self.check()
        self.assertTrue(report["errors"])
        self.assertTrue(any(str(item["file"]).endswith("oversized.md") for item in report["errors"]))


if __name__ == "__main__":
    unittest.main()
