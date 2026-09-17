"""Trial packaging boundaries: pinned network bytes and exact Git checkout."""

import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from scripts import ees_trial_bundle as bundles


WHEEL = b"synthetic pinned upstream wheel"
WHEEL_SHA = hashlib.sha256(WHEEL).hexdigest()
FILE_URL = "https://files.pythonhosted.org/packages/aa/bb/" + bundles.branding.SOURCE_FILENAME


def response(content, status=200):
    result = io.BytesIO(content)
    result.status = status
    return result


def metadata(**changes):
    row = {"filename": bundles.branding.SOURCE_FILENAME, "packagetype": "bdist_wheel", "yanked": False,
           "digests": {"sha256": WHEEL_SHA}, "size": len(WHEEL), "url": FILE_URL}
    row.update(changes)
    return json.dumps({"urls": [row]}).encode("utf-8")


class UpstreamTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = {"state_root": str(self.root)}
        self.progress = {}
        override = patch.object(bundles.branding, "SOURCE_SHA256", WHEEL_SHA)
        override.start()
        self.addCleanup(override.stop)
        self.opener = Mock()
        override = patch.object(bundles, "_opener", return_value=self.opener)
        self.open_mock = override.start()
        self.addCleanup(override.stop)

    def target(self):
        return self.root / "upstream" / bundles.branding.SOURCE_FILENAME

    def upstream(self):
        return bundles._upstream(self.config, "http://synthetic-proxy:8080", self.progress)

    def test_verified_download_is_cached_and_reused_without_network(self):
        self.opener.open.side_effect = [response(metadata()), response(WHEEL)]
        self.assertEqual(self.upstream().read_bytes(), WHEEL)
        self.assertFalse(self.progress["upstream_cached"])
        requests = [call.args[0] for call in self.opener.open.call_args_list]
        self.assertEqual([request.full_url for request in requests], [bundles.METADATA_URL, FILE_URL])
        self.assertTrue(all(not request.has_header("Authorization") for request in requests))
        self.assertTrue(all(call.kwargs["timeout"] == 30 for call in self.opener.open.call_args_list))
        self.open_mock.reset_mock()
        self.assertEqual(self.upstream().read_bytes(), WHEEL)
        self.assertTrue(self.progress["upstream_cached"])
        self.open_mock.assert_not_called()
        self.assertEqual(list(self.target().parent.iterdir()), [self.target()])

    def test_tampered_existing_cache_is_not_overwritten_or_downloaded(self):
        self.target().parent.mkdir()
        self.target().write_bytes(b"changed cache")
        with self.assertRaisesRegex(bundles.TrialBundleError, "upstream_cache_mismatch"):
            self.upstream()
        self.assertEqual(self.target().read_bytes(), b"changed cache")
        self.open_mock.assert_not_called()

    def test_untrusted_metadata_rejects_before_wheel_download(self):
        cases = ({"digests": {"sha256": "a" * 64}}, {"url": FILE_URL.replace("files.pythonhosted.org", "evil.test")},
                 {"size": True}, {"size": bundles.MAX_WHEEL_BYTES + 1}, {"yanked": True})
        for changes in cases:
            with self.subTest(changes=changes):
                self.opener.open.reset_mock()
                self.opener.open.side_effect = [response(metadata(**changes))]
                with self.assertRaises(bundles.TrialBundleError):
                    self.upstream()
                self.assertEqual(self.opener.open.call_count, 1)
                self.assertFalse(self.target().exists())

    def test_wheel_size_and_digest_failures_leave_no_partial_cache(self):
        for content in (b"incorrect wheel bytes", WHEEL + b"excess", WHEEL[:-1]):
            with self.subTest(content=content):
                self.opener.open.side_effect = [response(metadata()), response(content)]
                with self.assertRaises(bundles.TrialBundleError):
                    self.upstream()
                self.assertEqual(list(self.target().parent.iterdir()), [])

    def test_redirect_is_blocked_without_another_request_or_secret_text(self):
        self.opener.open.side_effect = HTTPError(bundles.METADATA_URL, 302, "secret-proxy-credential",
                                               {"Location": "https://evil.test"}, io.BytesIO())
        with self.assertRaisesRegex(bundles.TrialBundleError, "^upstream_redirect_blocked$"):
            self.upstream()
        self.assertEqual(self.opener.open.call_count, 1)
        self.assertIsNone(bundles._NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.test"))

    def test_file_urls_reject_authority_encoding_and_non_default_transport(self):
        bad = [FILE_URL.replace("https:", "http:"), FILE_URL.replace(".org/", ".org:444/"),
               FILE_URL.replace("files.", "user:password@files."), FILE_URL + "#fragment", FILE_URL + "?query=1",
               FILE_URL.replace("files.", "@files."), FILE_URL.replace(".org/", ".org:/"),
               FILE_URL.replace("/aa/", "/%61a/"), FILE_URL + "\n", FILE_URL.replace("/packages/", "/other/"), None]
        for url in bad:
            with self.subTest(url=url), self.assertRaisesRegex(bundles.TrialBundleError, "upstream_host_blocked"):
                bundles._wheel_url(url)
        self.assertEqual(bundles._wheel_url(FILE_URL.replace(".org/", ".org:443/")), FILE_URL.replace(".org/", ".org:443/"))

    def test_oversized_or_invalid_json_is_not_used(self):
        for raw in (b"x" * (bundles.MAX_JSON_BYTES + 1), b"[]", b"not json"):
            with self.subTest(size=len(raw)):
                self.opener.open.side_effect = [response(raw)]
                with self.assertRaises(bundles.TrialBundleError):
                    self.upstream()
                self.assertFalse(self.target().exists())

    def test_cleanup_is_scoped_and_does_not_reclassify_completed_update(self):
        directory = self.root / "trial-build-example"
        directory.mkdir()
        bundle = directory / ("EES-demo-" + "a" * 12 + ".zip")
        bundle.write_bytes(b"bundle")
        with patch.object(bundles.shutil, "rmtree", side_effect=PermissionError("locked")):
            self.assertFalse(bundles.cleanup(self.config, bundle))
        self.assertTrue(bundle.exists())
        self.assertFalse(bundles.cleanup({"state_root": str(directory)}, bundle))
        self.assertTrue(bundle.exists())
        self.assertTrue(bundles.cleanup(self.config, bundle))
        self.assertFalse(directory.exists())
        self.assertFalse(bundles.cleanup(self.config, bundle))

    def test_cleanup_rejects_linked_directory_without_touching_outside(self):
        outside = self.root / "preserved"
        outside.mkdir()
        bundle = outside / ("EES-demo-" + "a" * 12 + ".zip")
        bundle.write_bytes(b"preserve")
        link = self.root / "trial-build-linked"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Creating symlinks requires OS permission")
        self.assertFalse(bundles.cleanup(self.config, link / bundle.name))
        self.assertEqual(bundle.read_bytes(), b"preserve")


@unittest.skipUnless(shutil.which("git"), "Git is required")
class SourceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "repo"
        self.source.mkdir()
        self.state = self.root / "state"
        self.state.mkdir()
        self.config = {"state_root": str(self.state), "source_python": sys.executable}
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Synthetic Test")
        self.git("config", "user.email", "synthetic@example.invalid")
        (self.source / "source.txt").write_bytes(b"reviewed\nsource\n")
        self.git("add", ".")
        self.git("commit", "-m", "Synthetic source [skip ci]")
        self.commit = self.git("rev-parse", "HEAD")
        self.git("remote", "add", "origin", bundles.REPOSITORY)
        self.git("update-ref", "refs/remotes/origin/main", self.commit)
        override = patch.object(bundles, "ROOT", self.source)
        override.start()
        self.addCleanup(override.stop)
        override = patch.object(bundles, "_upstream", return_value=self.root / "official.whl")
        self.upstream = override.start()
        self.addCleanup(override.stop)
        self.progress = {}
        self.built_source = None

    def git(self, *arguments):
        return subprocess.run(["git", "-C", str(self.source), *arguments], check=True, capture_output=True,
                              text=True, encoding="utf-8", timeout=30).stdout.strip()

    def build(self, python, source, wheel, output):
        self.assertEqual(python, sys.executable)
        self.assertEqual((source / "source.txt").read_bytes(), b"reviewed\nsource\n")
        self.built_source = source
        (output / "branding").mkdir()
        (output / "branding" / "synthetic.whl").write_bytes(WHEEL)
        (output / ("EES-demo-" + self.commit[:12] + ".zip")).write_bytes(b"synthetic bundle")

    def prepare(self):
        return bundles.prepare(self.config, self.commit, None, self.progress)

    def test_lf_worktree_matches_git_bytes_preserving_original_crlf_checkout(self):
        self.git("config", "core.autocrlf", "true")
        (self.source / "source.txt").unlink()
        self.git("checkout", "--", "source.txt")
        self.assertEqual((self.source / "source.txt").read_bytes(), b"reviewed\r\nsource\r\n")
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=no"), "")
        with patch.object(bundles, "_build", side_effect=self.build):
            bundle = self.prepare()
        self.assertEqual((self.source / "source.txt").read_bytes(), b"reviewed\r\nsource\r\n")
        self.assertEqual(list(bundle.parent.iterdir()), [bundle])
        self.assertFalse(self.built_source.exists())
        self.assertEqual(bundle.parent.parent, self.state)
        self.assertNotIn(str(self.built_source), self.git("worktree", "list", "--porcelain"))

    def test_build_failure_cleans_created_worktree_and_temporary_output(self):
        with patch.object(bundles, "_build", side_effect=bundles.TrialBundleError("trial_build_failed")):
            with self.assertRaisesRegex(bundles.TrialBundleError, "trial_build_failed"):
                self.prepare()
        self.assertEqual(list(self.state.iterdir()), [])
        self.assertEqual(self.git("worktree", "list", "--porcelain").count("worktree "), 1)

    def test_checkout_change_stops_before_upstream_preparation(self):
        (self.source / "source.txt").write_bytes(b"user edit\n")
        with self.assertRaisesRegex(bundles.TrialBundleError, "trial_source_changed"):
            self.prepare()
        self.upstream.assert_not_called()
        self.assertEqual((self.source / "source.txt").read_bytes(), b"user edit\n")

    def test_source_mutation_during_builder_is_rejected_and_cleaned(self):
        def changed(*args):
            self.build(*args)
            (args[1] / "source.txt").write_bytes(b"unexpected source\n")
        with patch.object(bundles, "_build", side_effect=changed):
            with self.assertRaisesRegex(bundles.TrialBundleError, "trial_source_changed"):
                self.prepare()
        self.assertEqual(list(self.state.iterdir()), [])

    def test_wrong_branch_and_moved_origin_are_rejected(self):
        self.git("branch", "-m", "topic")
        with self.assertRaisesRegex(bundles.TrialBundleError, "trial_source_changed"):
            self.prepare()
        self.git("branch", "-m", "main")
        self.git("update-ref", "-d", "refs/remotes/origin/main")
        with self.assertRaises(bundles.TrialBundleError):
            self.prepare()
        self.upstream.assert_not_called()


if __name__ == "__main__":
    unittest.main()
