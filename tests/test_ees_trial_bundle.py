"""Trial packaging boundaries: pinned network bytes and exact Git checkout."""

import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from scripts import ees_trial_bundle as bundles
from scripts import ees_deploy_stop_recovery as recovery


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
        temporary = tempfile.TemporaryDirectory(dir=os.environ.get("RUNNER_TEMP"))
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
        failure = {"failure": {"action": "upgrade", "failed": True, "result": {
            "stage": "process_stop", "changed": False, "wrapper_commit": self.commit,
            "source_verification": "local_trial", "process": {"error_type": "process"},
            "bundle": str(bundle)}}}
        self.assertEqual(recovery.validate_failure(self.config, failure, self.commit), bundle)

    def test_full_repository_prepares_with_long_paths_disabled(self):
        required = os.environ.get("EES_TEST_REQUIRE_WIN32_PATHS_DISABLED") == "1"
        policy = None
        if os.name == "nt":
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"SYSTEM\CurrentControlSet\Control\FileSystem") as key:
                try:
                    policy = winreg.QueryValueEx(key, "LongPathsEnabled")[0]
                except FileNotFoundError:
                    policy = 0
        if required:
            self.assertEqual(os.name, "nt")
            self.assertEqual(policy, 0)
        repository = Path(__file__).resolve().parents[1]
        archive = subprocess.run(["git", "-C", str(repository), "archive", "HEAD"],
                                 check=True, capture_output=True, timeout=60).stdout
        with tarfile.open(fileobj=io.BytesIO(archive)) as source_archive:
            source_archive.extractall(self.source, filter="data")
        self.git("add", "-f", "--all")
        self.git("commit", "-m", "Full tracked repository fixture")
        self.commit = self.git("rev-parse", "HEAD")
        self.git("update-ref", "refs/remotes/origin/main", self.commit)
        self.git("config", "core.longpaths", "true")
        names = self.git("ls-tree", "-r", "-z", "--name-only", "HEAD").split("\0")
        units = lambda path: len(str(path).encode("utf-16-le")) // 2
        longest = max(filter(None, names), key=units)
        self.assertGreater(len(names), 1000)
        size = 290 - units(self.root / "trial-build-12345678" / "source" / longest) - 1
        self.assertGreater(size, 0)
        self.state = self.root / ("s" * size)
        self.state.mkdir()
        self.config["state_root"] = str(self.state)
        old_source = self.state / "trial-build-12345678" / "source"
        old_source.parent.mkdir()
        self.assertEqual(units(old_source / longest), 290)
        try:
            self.git("-c", "core.autocrlf=false", "worktree", "add", "--detach", str(old_source), self.commit)
            old_exists = (old_source / longest).exists()
            if required:
                self.assertFalse(old_exists, "The old 290-unit path must reproduce the Python failure")
        finally:
            # Git handles the deliberately long paths even when Python cannot.
            entries = self.git("worktree", "list", "--porcelain", "-z").split("\0")
            if any(row.startswith("worktree ") and Path(row[9:]) == old_source for row in entries):
                self.git("worktree", "remove", "--force", str(old_source))
            old_source.parent.rmdir()
        with patch.object(bundles, "_build", side_effect=self.build):
            bundle = self.prepare()
        self.assertLess(max(units(self.built_source / name) for name in filter(None, names)), 260)
        self.assertEqual(self.built_source.parent, self.source.parent)
        self.assertFalse(self.built_source.exists())
        self.assertEqual(bundle.parent.parent, self.state)
        self.assertEqual(list(bundle.parent.iterdir()), [bundle])
        print("EES path regression policy=%s old_max=290 old_exists=%s new_max=%s source_removed=True" %
              (policy, old_exists, max(units(self.built_source / name) for name in filter(None, names))))

    def test_path_budget_rejects_before_download_or_temporary_files(self):
        with patch.object(bundles, "WINDOWS_PATHS", True), \
                patch.object(bundles, "_git", wraps=bundles._git) as git_call, \
                patch.object(bundles, "_check_source_paths", side_effect=bundles.TrialBundleError("trial_source_path_too_long")):
            with self.assertRaisesRegex(bundles.TrialBundleError, "trial_source_path_too_long"):
                self.prepare()
        self.upstream.assert_not_called()
        self.assertEqual(list(self.state.iterdir()), [])
        self.assertFalse(list(self.root.glob("ees-*")))
        self.assertFalse(any(call.args[:2] == ("worktree", "add") for call in git_call.call_args_list))

    def test_windows_utf16_file_and_directory_limits(self):
        with patch.object(bundles, "WINDOWS_PATHS", True):
            for directory, filename, valid in ((10, 248, True), (10, 249, False),
                                                (247, 1, True), (248, 1, True), (249, 1, False)):
                # A leading slash and separator count too, independently of the host OS.
                source = Path("/" + "s" * (directory - 1))
                with patch.object(bundles, "_git", return_value="f" * filename):
                    if valid:
                        bundles._check_source_paths(source, self.commit)
                    else:
                        with self.assertRaisesRegex(bundles.TrialBundleError, "trial_source_path_too_long"):
                            bundles._check_source_paths(source, self.commit)
            with patch.object(bundles, "_git", return_value="\U0001f600" * 128):
                with self.assertRaisesRegex(bundles.TrialBundleError, "trial_source_path_too_long"):
                    bundles._check_source_paths(Path("/ss"), self.commit)

    def test_partial_add_cleanup_preserves_unrelated_worktree(self):
        other = self.root / "unrelated"
        self.git("worktree", "add", "--detach", str(other), self.commit)
        self.addCleanup(lambda: self.git("worktree", "remove", "--force", str(other)))
        original = bundles._git
        def partial(*arguments, **kwargs):
            result = original(*arguments, **kwargs)
            if arguments[:2] == ("worktree", "add"):
                raise bundles.TrialBundleError("trial_source_failed")
            return result
        with patch.object(bundles, "_git", side_effect=partial):
            with self.assertRaisesRegex(bundles.TrialBundleError, "trial_source_failed"):
                self.prepare()
        self.assertFalse(list(self.root.glob("ees-*")))
        self.assertEqual(list(self.state.iterdir()), [])
        self.assertEqual((other / "source.txt").read_bytes(), b"reviewed\nsource\n")

    def test_cleanup_failure_does_not_replace_original_failure(self):
        original = bundles._remove_source
        retained = []
        def failed_cleanup(source):
            retained.append(source)
            raise PermissionError("synthetic locked path")
        try:
            with patch.object(bundles, "_build", side_effect=bundles.TrialBundleError("trial_build_failed")), \
                    patch.object(bundles, "_remove_source", side_effect=failed_cleanup):
                with self.assertRaisesRegex(bundles.TrialBundleError, "trial_build_failed"):
                    self.prepare()
            self.assertTrue(self.progress["cleanup_failed"])
        finally:
            for source in retained:
                original(source)

    def test_linked_source_parent_is_rejected_before_download(self):
        link = self.root / "parent-link"
        try:
            link.symlink_to(self.root, target_is_directory=True)
        except OSError:
            self.skipTest("Creating symlinks requires OS permission")
        with patch.object(bundles, "ROOT", link / "repo"):
            with self.assertRaises(bundles.states.StateError):
                self.prepare()
        self.upstream.assert_not_called()
        self.assertFalse(list(self.root.glob("ees-*")))

    def test_source_creation_failure_cleans_only_output(self):
        original = bundles.tempfile.mkdtemp
        sentinel = self.root / "ees-unrelated"
        sentinel.mkdir()
        (sentinel / "keep").write_bytes(b"user content")
        def create(*args, **kwargs):
            if kwargs.get("prefix") == "ees-":
                raise PermissionError("synthetic source creation failure")
            return original(*args, **kwargs)
        with patch.object(bundles.tempfile, "mkdtemp", side_effect=create):
            with self.assertRaises(PermissionError):
                self.prepare()
        self.assertEqual(list(self.state.iterdir()), [])
        self.assertEqual((sentinel / "keep").read_bytes(), b"user content")

    def test_cleanup_refuses_replaced_source_link_and_preserves_target(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "keep").write_bytes(b"user content")
        source = self.root / "ees-replaced"
        try:
            source.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Creating symlinks requires OS permission")
        with self.assertRaises(bundles.states.StateError):
            bundles._remove_source(source)
        self.assertEqual((outside / "keep").read_bytes(), b"user content")
        self.assertTrue(source.is_symlink())

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
