import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ship'))
import upgrade_once as upgrade


def status(current=True, running=True):
    return {'current_commit': upgrade.SHA if current else 'previous', 'managed_process_running': running,
            'program_valid': True, 'program_incomplete': False}


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'git'
        self.config = self.root / 'config.json'
        self.config.write_text(json.dumps({'env_names': []}))
        self.cache = self.root / 'cache'
        self.base = 'https://docs.example.invalid/rest/api'
        self.addCleanup(patch.stopall)

    def install(self, choose):
        with contextlib.redirect_stdout(io.StringIO()):
            upgrade.install(self.repo, self.config, self.cache, self.base, choose)

    def actions(self, statuses, *, start_failed=False):
        calls = []
        def invoke(repo, path, action, *args, env=None, read=False):
            self.assertEqual((repo, path), (self.repo, self.config))
            calls.append((action, args, env, read))
            if action == 'Status':
                return next(statuses)
            if action == 'Start':
                return {'already_running': True} if start_failed else {'started': True}
        patch.object(upgrade, 'manager', side_effect=invoke).start()
        return calls

    def test_new_version_download_and_install_order_and_credential_scope(self):
        calls = self.actions(iter([status(False), status(False), status()]))
        events = []
        values = {'TEST_CONFLUENCE': 'dummy'}
        patch.object(upgrade, 'check_source', side_effect=lambda *a: events.append('update')).start()
        artifact = self.root / upgrade.FILENAME
        def download(*args):
            events.append('download')
            self.assertNotIn('TEST_CONFLUENCE', os.environ)
            return artifact
        patch.object(upgrade, 'download', side_effect=download).start()
        def connect(base, settings):
            self.assertEqual(base, self.base)
            self.assertEqual(settings['env_names'], [])
            events.append('preflight')
            return values
        patch.object(upgrade, 'get_connection', side_effect=connect).start()
        self.install(True)
        self.assertEqual(events, ['update', 'download', 'preflight'])
        self.assertEqual([x[0] for x in calls], ['Status', 'Status', 'Upgrade', 'Status'])
        self.assertEqual(calls[2][1], ('-Bundle', artifact, '-Commit', upgrade.SHA, '-ArtifactSha256', upgrade.DIGEST, '-HealthTimeout', '120'))
        self.assertIs(calls[2][2], values)
        self.assertTrue(all(c[2] is None for c in [calls[0], calls[1], calls[3]]))

    def test_current_noop_and_existing_stopped_start(self):
        for running, expected in [(True, ['Status', 'Status', 'Status']), (False, ['Status', 'Status', 'Start', 'Status'])]:
            with self.subTest(running=running):
                calls = self.actions(iter([status(running=running), status(running=running), status()]))
                with patch.object(upgrade, 'check_source') as download:
                    self.install(False)
                    download.assert_not_called()
                self.assertEqual([x[0] for x in calls], expected)

    def test_current_connection_preflight_then_stop_start(self):
        calls = self.actions(iter([status(), status(), status()]))
        def connect(*args):
            self.assertEqual([x[0] for x in calls], ['Status'])
            return {'AUTH': 'dummy'}
        patch.object(upgrade, 'get_connection', side_effect=connect).start()
        self.install(True)
        self.assertEqual([x[0] for x in calls], ['Status', 'Status', 'Stop', 'Start', 'Status'])
        self.assertEqual(calls[3][2], {'AUTH': 'dummy'})
        self.assertIsNone(calls[2][2])

    def test_failed_reconnect_restores_previous_managed_service(self):
        calls = self.actions(iter([status(), status(), status(running=False)]))
        with patch.object(upgrade, 'get_connection', return_value={'NEW_AUTH': 'fake'}), patch.object(upgrade,'start', side_effect=[upgrade.DeploymentError('initial failure'), None]) as start:
            with self.assertRaisesRegex(upgrade.DeploymentError, '기존 관리 설정'):
                self.install(True)
            self.assertEqual([x[0] for x in calls], ['Status', 'Status', 'Stop', 'Status'])
            self.assertIsNone(start.call_args.args[-1])
            self.assertEqual(start.call_count, 2)

    def test_preflight_failure_or_racing_start_never_claims_connection(self):
        calls = self.actions(iter([status()]))
        with patch.object(upgrade, 'get_connection', side_effect=upgrade.DeploymentError('test')):
            with self.assertRaises(upgrade.DeploymentError):
                self.install(True)
        self.assertEqual([x[0] for x in calls], ['Status'])
        self.actions(iter([status(running=False), status(running=False)]), start_failed=True)
        with self.assertRaises(upgrade.DeploymentError):
            self.install(False)

    def test_choices_preserve_existing_and_no_prompt_in_batch(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(sys.stdin, 'isatty', return_value=True), patch('builtins.input', return_value=''):
            self.assertTrue(upgrade.connection_choice(self.base, None, {}, False))
            self.assertFalse(upgrade.connection_choice(self.base, None, {}, True))
            self.assertFalse(upgrade.connection_choice(self.base, None, {'env_names': [upgrade.REGISTRY]}, False))
            with patch.dict(os.environ, {upgrade.REGISTRY: json.dumps({upgrade.SERVICE: {}})}):
                self.assertFalse(upgrade.connection_choice(self.base, None, {}, False))
        with patch.object(sys.stdin, 'isatty', return_value=False), patch('builtins.input', side_effect=AssertionError):
            self.assertFalse(upgrade.connection_choice(self.base, None, {}, False))
        with self.assertRaises(upgrade.DeploymentError):
            upgrade.connection_choice(None, True, {}, False)

    def test_wrong_head_refused_before_update(self):
        with patch.object(upgrade, 'git', side_effect=[upgrade.SOURCE, 'main', '', 'other refs/heads/main']), patch.object(upgrade, 'manager') as manager:
            with self.assertRaises(upgrade.DeploymentError):
                upgrade.check_source(self.repo, self.config)
            manager.assert_not_called()
        with patch.object(upgrade,'git', side_effect=[upgrade.SOURCE, 'main', '', upgrade.SHA+'\trefs/heads/main', upgrade.SHA, 'moved']), patch.object(upgrade,'manager') as manager:
            with self.assertRaises(upgrade.DeploymentError):
                upgrade.check_source(self.repo, self.config)
            manager.assert_called_once_with(self.repo, self.config, 'Update')

    def test_install_incomplete_is_never_replaced(self):
        self.actions(iter([{**status(False), 'program_incomplete': True}]))
        with patch.object(upgrade, 'check_source') as git:
            with self.assertRaises(upgrade.DeploymentError):
                self.install(False)
            git.assert_not_called()

    def test_real_release_digest_and_cache_not_modified(self):
        art = self.cache / upgrade.FILENAME
        self.cache.mkdir()
        art.write_bytes(b'correct')
        with patch.object(upgrade, 'SIZE', art.stat().st_size), patch.object(upgrade, 'DIGEST', hashlib.sha256(b'correct').hexdigest()):
            self.assertEqual(upgrade.download(self.repo, self.config, self.cache), art)
            art.write_bytes(b'incorre')
            self.assertFalse(upgrade.verified(art))

    def test_retry_partial_download_and_restore_limit(self):
        content = b'reviewed bytes'
        class DownloadError(Exception):
            def __init__(self, code): self.code = code
        protocol = types.SimpleNamespace(MAX_DOWNLOAD_SECONDS=600, DownloadError=DownloadError)
        attempts = []
        def download(id, path, digest, size):
            self.assertEqual(id, upgrade.ARTIFACT_ID)
            self.assertEqual(protocol.MAX_DOWNLOAD_SECONDS, 3600)
            self.assertFalse(path.exists())
            path.write_bytes(content if attempts else b'partial')
            attempts.append(path)
            if len(attempts) == 1:
                raise DownloadError('download_timeout')
        controller = Mock(downloads=protocol)
        controller.github_client.return_value._download.side_effect = download
        with patch.object(upgrade, 'SIZE', len(content)), patch.object(upgrade, 'DIGEST', hashlib.sha256(content).hexdigest()), patch.dict(sys.modules,{'ees_upgrade': controller}), patch.object(upgrade.time,'sleep'):
            answer = upgrade.download(self.repo, self.config, self.cache)
            self.assertEqual(answer.read_bytes(), content)
            self.assertEqual(protocol.MAX_DOWNLOAD_SECONDS, 600)
            self.assertEqual(len(attempts), 2)
            self.assertFalse(attempts[0].exists())

    def test_completed_job_requires_healthy_current_commit(self):
        self.actions(iter([status(), status(), status(False)]))
        with self.assertRaises(upgrade.DeploymentError):
            self.install(False)

    def test_manager_calls_native_windows_process_without_credentials_in_args(self):
        (self.repo / 'scripts').mkdir(parents=True)
        (self.repo / 'scripts' / 'manage-ees.ps1').touch()
        env = {'TEST_SECRET': 'dummy-secret'}
        with patch.dict(os.environ, {'SystemRoot': 'C:/Windows'}), patch.object(subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, b'{"started":true}')) as run:
            self.assertEqual(upgrade.manager(self.repo, self.config, 'Start', env=env, read=True), {'started': True})
            args = run.call_args.args[0]
            self.assertIn('Start', args)
            self.assertNotIn('dummy-secret', str(args))
            self.assertIs(run.call_args.kwargs['env'], env)
        self.assertEqual(upgrade.parse_output('{"x": 1}'.encode('utf-16')), {'x':1})


if __name__ == '__main__':
    unittest.main()
