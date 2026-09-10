"""Real local fake-child lifecycle tests; never import or install Open WebUI."""

import importlib.util
import errno
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import MagicMock, Mock, patch

from scripts import build_ees_webui as branding


MODULE = Path(__file__).resolve().parents[1] / 'scripts' / 'ees_deploy_process.py'
SPEC = importlib.util.spec_from_file_location('ees_deploy_process_test', MODULE)
manager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manager)

FAKE_SERVER = r'''
import json, os, signal, sys, time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
if os.environ.get('EES_TEST_EXIT'):
    print('synthetic-private-log-only', flush=True)
    sys.exit(7)
running = True
def graceful(signum, frame):
    global running
    if not os.environ.get('EES_TEST_IGNORE'):
        running = False
signal.signal(signal.SIGBREAK if sys.platform == 'win32' else signal.SIGINT, graceful)
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        with open('requests.txt', 'a') as handle:
            handle.write(self.path + '\n')
        if os.environ.get('EES_TEST_REDIRECT') and self.path == '/health':
            self.send_response(302)
            self.send_header('Location', '/redirect-target')
            self.end_headers()
            return
        body = json.dumps({'status': not bool(os.environ.get('EES_TEST_UNHEALTHY'))}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *_):
        pass
server = HTTPServer((sys.argv[1], int(sys.argv[2])), Handler)
server.timeout = .1
Path('started.txt').write_text('ready')
deadline = time.monotonic() + float(os.environ.get('EES_TEST_LIFETIME', '12'))
while running and time.monotonic() < deadline:
    server.handle_request()
server.server_close()
Path('graceful.txt').write_text('stopped')
'''


class DeployProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.console_allocated = False
        if sys.platform.startswith('linux') and int(Path('/proc/self/stat').read_text().split()[0]) != os.getpid():
            raise unittest.SkipTest('The mounted /proc uses a different PID namespace; real lifecycle runs in Windows/Linux CI.')
        if os.name == 'nt':
            import ctypes
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            count = (ctypes.c_ulong * 1)()
            if kernel.GetConsoleProcessList(count, 1) == 0:
                if not kernel.AllocConsole():
                    raise RuntimeError('Windows lifecycle tests require a real console.')
                cls.console_allocated = True

    @classmethod
    def tearDownClass(cls):
        if cls.console_allocated:
            import ctypes
            ctypes.WinDLL('kernel32').FreeConsole()

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            self.port = listener.getsockname()[1]
        self.patch = patch.object(manager, 'SERVER_CODE', FAKE_SERVER)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.identity = None
        self.addCleanup(self.cleanup_child)

    def cleanup_child(self):
        if self.identity is not None and manager.verify_identity(self.identity):
            try:
                manager.stop_server(self.identity, timeout=3)
            except manager.ProcessError:
                # The bounded fake child exits itself; tests never force-kill it.
                deadline = time.monotonic() + 13
                while manager.verify_identity(self.identity) and time.monotonic() < deadline:
                    time.sleep(.1)

    def start(self, **settings):
        env = {**os.environ, **settings}
        self.identity = manager.start_server(sys.executable, self.root, env,
                                             '127.0.0.1', self.port, self.root / 'logs')
        return self.identity

    def test_start_health_and_graceful_stop(self):
        self.assertTrue(manager.port_is_free('127.0.0.1', self.port))
        identity = self.start()
        manager.wait_healthy(identity, timeout=5)
        self.assertTrue(manager.verify_identity(identity))
        self.assertFalse(manager.port_is_free('127.0.0.1', self.port))
        manager.stop_server(identity, timeout=3)
        self.assertEqual((self.root / 'graceful.txt').read_text(), 'stopped')
        self.assertFalse(manager.verify_identity(identity))
        self.assertTrue(manager.port_is_free('127.0.0.1', self.port))
        manager.stop_server(identity)  # Already stopped is harmless.

    def test_another_process_can_stop_saved_identity(self):
        identity = self.start()
        manager.wait_healthy(identity, timeout=5)
        code = ('import importlib.util,json,sys; '
                's=importlib.util.spec_from_file_location("m",sys.argv[1]); '
                'm=importlib.util.module_from_spec(s);s.loader.exec_module(m); '
                'm.stop_server(json.loads(sys.argv[2]),timeout=3)')
        flags = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
        completed = subprocess.run([sys.executable, '-c', code, str(MODULE), json.dumps(identity)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=8, **flags)
        self.assertEqual(completed.returncode, 0, completed.stderr.decode(errors='replace'))
        self.assertEqual((self.root / 'graceful.txt').read_text(), 'stopped')

    def test_venv_redirector_or_symlink_preserves_environment_and_graceful_stop(self):
        environment = self.root / 'tiny-venv'
        command = [sys.executable, '-m', 'venv', '--without-pip']
        if os.name != 'nt':
            command.append('--symlinks')
        completed = subprocess.run(command + [str(environment)], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stderr.decode(errors='replace'))
        executable = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        if os.name != 'nt':
            self.assertTrue(executable.is_symlink())
        runtime_probe = (
            "import json,os,sys; from pathlib import Path; "
            "Path('python-runtime.json').write_text(json.dumps({"
            "'prefix':sys.prefix,'executable':sys.executable,'pid':os.getpid()}))\n"
        )
        with patch.object(manager, 'SERVER_CODE', runtime_probe + FAKE_SERVER):
            self.identity = manager.start_server(executable, self.root, dict(os.environ),
                                                 '127.0.0.1', self.port, self.root / 'logs')
        manager.wait_healthy(self.identity, timeout=5)
        runtime = json.loads((self.root / 'python-runtime.json').read_text())
        self.assertEqual(Path(runtime['prefix']).resolve(), environment.resolve())
        self.assertEqual(Path(runtime['executable']).absolute(), executable.absolute())
        if os.name == 'nt':
            # CPython's venv redirector owns the group and waits for this Python child.
            self.assertNotEqual(runtime['pid'], self.identity['pid'])
        manager.stop_server(self.identity, timeout=3)
        self.assertEqual((self.root / 'graceful.txt').read_text(), 'stopped')
        self.assertFalse(manager.verify_identity(self.identity))
        self.assertTrue(manager.port_is_free('127.0.0.1', self.port))

    def test_wrong_creation_time_or_executable_never_signals(self):
        identity = self.start()
        manager.wait_healthy(identity, timeout=5)
        for field in ('created_at', 'executable'):
            with self.subTest(field=field):
                bad = {**identity, field: identity[field] + '-wrong'}
                with self.assertRaisesRegex(manager.ProcessError, 'identity changed'):
                    manager.stop_server(bad)
                self.assertTrue(manager.verify_identity(identity))
                self.assertFalse((self.root / 'graceful.txt').exists())

    def test_startup_failure_does_not_echo_log_contents(self):
        with self.assertRaises(manager.ProcessError) as failure:
            identity = self.start(EES_TEST_EXIT='1')
            manager.wait_healthy(identity, timeout=3)
        self.assertNotIn('synthetic-private', str(failure.exception))
        self.assertEqual(failure.exception.reason, 'process_exited')
        self.assertEqual(failure.exception.exit_code, 7)
        logs = list((self.root / 'logs').glob('*.log'))
        self.assertEqual(len(logs), 1)
        self.assertEqual(failure.exception.log_id, logs[0].name)

    def test_occupied_port_does_not_start_or_stop_any_process(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', self.port))
            listener.listen()
            with patch.object(manager.subprocess, 'Popen') as spawn:
                with self.assertRaisesRegex(manager.ProcessError, 'port is unavailable'):
                    self.start()
                spawn.assert_not_called()

    def test_health_ignores_proxy_and_never_follows_redirects(self):
        identity = self.start(EES_TEST_REDIRECT='1')
        self.wait_started()
        with patch.dict(os.environ, {'HTTP_PROXY': 'http://127.0.0.1:1', 'NO_PROXY': ''}):
            with self.assertRaisesRegex(manager.ProcessError, 'health timed out'):
                manager.wait_healthy(identity, timeout=.8)
        paths = (self.root / 'requests.txt').read_text().splitlines()
        self.assertGreater(len(paths), 0)  # Direct request succeeded despite an unusable proxy.
        self.assertEqual(set(paths), {'/health'})

    def test_health_false_and_stop_timeout_do_not_force_kill(self):
        identity = self.start(EES_TEST_UNHEALTHY='1', EES_TEST_IGNORE='1', EES_TEST_LIFETIME='2.5')
        self.wait_started()
        with self.assertRaisesRegex(manager.ProcessError, 'health timed out'):
            manager.wait_healthy(identity, timeout=.5)
        with self.assertRaisesRegex(manager.ProcessError, 'stop timed out'):
            manager.stop_server(identity, timeout=.15)
        self.assertTrue(manager.verify_identity(identity))
        deadline = time.monotonic() + 3
        while manager.verify_identity(identity) and time.monotonic() < deadline:
            time.sleep(.1)
        self.assertFalse(manager.verify_identity(identity))

    def wait_started(self):
        deadline = time.monotonic() + 5
        while not (self.root / 'started.txt').exists() and time.monotonic() < deadline:
            time.sleep(.05)
        self.assertTrue((self.root / 'started.txt').exists())


class ProcessContracts(unittest.TestCase):
    def setUp(self):
        self.saved = {'pid': 123, 'executable': 'python', 'created_at': '456', 'group_id': 123,
                      'host': '127.0.0.1', 'port': 8080, 'log_file': 'local-only.log'}

    def test_bind_failure_preserves_only_numeric_codes_without_reprobe_or_launch(self):
        private = 'synthetic-private-key C:/private/server.log 192.0.2.123'
        for code, windows_code in [(errno.EADDRINUSE, 10048), (errno.EADDRNOTAVAIL, 10049),
                                   (errno.EACCES, 10013)]:
            with self.subTest(code=code):
                original = OSError(code, private, 'synthetic-private-file')
                original.winerror = windows_code
                resource = MagicMock()
                listener = resource.__enter__.return_value
                listener.bind.side_effect = original
                with patch.object(manager.socket, 'socket', return_value=resource) as probe, \
                        patch.object(manager.subprocess, 'Popen') as spawn:
                    with self.assertRaises(manager.ProcessError) as failure:
                        manager.start_server(sys.executable, '.', {'KEY': private}, '192.0.2.123', 8080, '.')
                error = failure.exception
                self.assertEqual((error.errno, error.winerror, error.operation), (code, windows_code, 'port_bind'))
                self.assertEqual(str(error), 'The listen port is unavailable; no existing process was stopped.')
                self.assertNotIn('synthetic-private', repr(error))
                self.assertTrue(error.__suppress_context__)
                probe.assert_called_once()
                listener.bind.assert_called_once_with(('192.0.2.123', 8080))
                spawn.assert_not_called()

    def test_port_probe_boolean_api_remains_available(self):
        resource = MagicMock()
        listener = resource.__enter__.return_value
        listener.bind.side_effect = OSError(errno.EADDRNOTAVAIL, 'synthetic-private')
        with patch.object(manager.socket, 'socket', return_value=resource) as probe:
            self.assertIs(manager.port_is_free('127.0.0.1', 8080), False)
            listener.bind.side_effect = None
            self.assertIs(manager.port_is_free('127.0.0.1', 8080), True)
            self.assertIs(manager.port_is_free('127.0.0.1', 8080, raise_on_error=True), True)
        self.assertEqual((probe.call_count, listener.bind.call_count), (3, 3))

    def test_socket_setup_failure_is_distinct_from_bind_failure(self):
        for failed_step in ('creation', 'setsockopt'):
            with self.subTest(failed_step=failed_step):
                resource = MagicMock()
                listener = resource.__enter__.return_value
                original = OSError(errno.EMFILE, 'synthetic-private')
                if failed_step == 'setsockopt':
                    listener.setsockopt.side_effect = original
                with patch.object(manager.os, 'name', 'posix'), \
                        patch.object(manager.socket, 'socket', return_value=resource,
                                     side_effect=original if failed_step == 'creation' else None) as probe:
                    with self.assertRaises(manager.ProcessError) as failure:
                        manager.port_is_free('127.0.0.1', 8080, raise_on_error=True)
                self.assertEqual((failure.exception.errno, failure.exception.winerror,
                                  failure.exception.operation), (errno.EMFILE, None, 'port_probe'))
                probe.assert_called_once()
                listener.bind.assert_not_called()

    def test_process_error_rejects_nonnumeric_codes_and_unknown_operation(self):
        for value in (None, True, 'synthetic-private', 13.0, ['synthetic-private']):
            with self.subTest(value=value):
                original = OSError('synthetic-private-error')
                original.errno = original.winerror = value
                error = manager.ProcessError('Safe message.', cause=original, operation='synthetic-private')
                self.assertEqual((error.errno, error.winerror, error.operation), (None, None, None))
                self.assertEqual(str(error), 'Safe message.')

    def test_failure_metadata_accepts_only_fixed_reasons_safe_ids_and_finite_numbers(self):
        log_id = 'server-' + 'a' * 32 + '.log'
        error = manager.ProcessError('Safe message.', reason='process_exited', elapsed_seconds=1.25,
                                     timeout_seconds=60, exit_code=-2, log_id=log_id)
        self.assertEqual((error.reason, error.elapsed_seconds, error.timeout_seconds,
                          error.exit_code, error.log_id), ('process_exited', 1.25, 60, -2, log_id))
        for value in (None, True, 'synthetic-private', ['synthetic-private'],
                      float('inf'), float('-inf'), float('nan')):
            with self.subTest(value=value):
                error = manager.ProcessError('Safe message.', reason=value, elapsed_seconds=value,
                                             timeout_seconds=value, exit_code=value, log_id=value)
                self.assertEqual((error.reason, error.elapsed_seconds, error.timeout_seconds,
                                  error.exit_code, error.log_id), (None, None, None, None, None))
                self.assertNotIn('synthetic-private', json.dumps(vars(error)))
        for value in (-1, -0.5):
            error = manager.ProcessError('Safe message.', elapsed_seconds=value, timeout_seconds=value)
            self.assertEqual((error.elapsed_seconds, error.timeout_seconds), (None, None))
        for value in ('C:/synthetic-private/' + log_id, '../' + log_id, log_id + '\n',
                      'server-secret.log', 'server-' + 'A' * 32 + '.log'):
            self.assertIsNone(manager.ProcessError('Safe message.', log_id=value).log_id)

    def test_launch_failure_does_not_echo_error_or_log_path(self):
        original = OSError(errno.EACCES, 'synthetic-private-error', 'synthetic-private-file')
        with tempfile.TemporaryDirectory(prefix='synthetic-private-') as directory, \
                patch.object(manager, 'port_is_free', return_value=True), \
                patch.object(manager.subprocess, 'Popen', side_effect=original) as spawn:
            with self.assertRaises(manager.ProcessError) as failure:
                manager.start_server(sys.executable, directory, {}, '127.0.0.1', 8080, directory)
            self.assertEqual(failure.exception.errno, errno.EACCES)
            self.assertEqual(failure.exception.reason, 'launch_failed')
            self.assertGreaterEqual(failure.exception.elapsed_seconds, 0)
            self.assertEqual(failure.exception.log_id, next(Path(directory).glob('*.log')).name)
            self.assertNotIn('synthetic-private', str(failure.exception))
            self.assertNotIn(directory, str(failure.exception))
            spawn.assert_called_once()

    def test_health_failure_does_not_echo_saved_log_path(self):
        identity = {**self.saved, 'log_file': 'C:/synthetic-private/server.log'}
        with patch.object(manager, 'verify_identity', return_value=False):
            with self.assertRaisesRegex(manager.ProcessError, 'identity changed') as failure:
                manager.wait_healthy(identity, timeout=1)
            self.assertNotIn('synthetic-private', str(failure.exception))
            self.assertIsNone(failure.exception.log_id)
        with self.assertRaisesRegex(manager.ProcessError, 'health timed out') as failure:
            manager.wait_healthy(identity, timeout=0)
        self.assertNotIn('synthetic-private', str(failure.exception))

    def test_health_exit_retains_exit_evidence_after_identity_removes_owned_child(self):
        child = Mock(pid=self.saved['pid'], returncode=None)
        def exited():
            child.returncode = 7
            return 7
        child.poll.side_effect = exited
        log_id = 'server-' + 'b' * 32 + '.log'
        identity = {**self.saved, 'log_file': '/synthetic-private/' + log_id}
        with patch.dict(manager._CHILDREN, {child.pid: child}, clear=True), \
                patch.object(manager.time, 'monotonic', side_effect=[10, 10.1, 10.2]), \
                patch.object(manager, '_healthy') as health, patch.object(manager.time, 'sleep') as sleep:
            with self.assertRaises(manager.ProcessError) as failure:
                manager.wait_healthy(identity, timeout=60)
            self.assertNotIn(child.pid, manager._CHILDREN)
        error = failure.exception
        self.assertEqual((error.reason, error.exit_code, error.timeout_seconds, error.log_id),
                         ('process_exited', 7, 60, log_id))
        self.assertAlmostEqual(error.elapsed_seconds, .2)
        child.poll.assert_called_once()
        health.assert_not_called()
        sleep.assert_not_called()
        self.assertNotIn('synthetic-private', json.dumps(vars(error)))

    def test_unhealthy_process_reports_timeout_with_measured_duration(self):
        with patch.object(manager, 'verify_identity', return_value=True) as verify, \
                patch.object(manager, '_healthy', return_value=False) as health, \
                patch.object(manager.time, 'monotonic', side_effect=[20, 20, 20.1, 20.2, 21, 21.25]), \
                patch.object(manager.time, 'sleep') as sleep:
            with self.assertRaises(manager.ProcessError) as failure:
                manager.wait_healthy(self.saved, timeout=1)
        self.assertEqual((failure.exception.reason, failure.exception.elapsed_seconds,
                          failure.exception.timeout_seconds, failure.exception.exit_code),
                         ('health_timeout', 1.25, 1, None))
        verify.assert_called_once_with(self.saved)
        health.assert_called_once()
        sleep.assert_called_once()

    def test_missing_or_changed_identity_is_not_evidence_of_process_exit(self):
        for actual in (None, {**self.saved, 'created_at': 'different'}):
            with self.subTest(actual=actual), patch.dict(manager._CHILDREN, {}, clear=True), \
                    patch.object(manager, '_identity', return_value=actual), \
                    patch.object(manager, '_healthy') as health:
                with self.assertRaises(manager.ProcessError) as failure:
                    manager.wait_healthy(self.saved, timeout=60)
                self.assertEqual(failure.exception.reason, 'identity_changed')
                self.assertIsNone(failure.exception.exit_code)
                self.assertGreaterEqual(failure.exception.elapsed_seconds, 0)
                health.assert_not_called()

    def test_identity_inspection_failure_is_distinct_and_does_not_echo_error(self):
        original = OSError(errno.EACCES, 'synthetic-private-inspection')
        with patch.object(manager, '_identity', side_effect=original), \
                patch.object(manager, '_healthy') as health:
            with self.assertRaises(manager.ProcessError) as failure:
                manager.wait_healthy(self.saved, timeout=60)
        self.assertEqual((failure.exception.reason, failure.exception.errno,
                          failure.exception.exit_code), ('identity_unavailable', errno.EACCES, None))
        self.assertNotIn('synthetic-private', str(failure.exception))
        self.assertNotIn('synthetic-private', json.dumps(vars(failure.exception)))
        self.assertTrue(failure.exception.__suppress_context__)
        health.assert_not_called()

    def test_final_health_identity_failure_is_not_reported_as_timeout_or_success(self):
        for result, reason in ((False, 'identity_changed'),
                               (manager.ProcessError('synthetic-private'), 'identity_unavailable')):
            with self.subTest(reason=reason), patch.dict(manager._CHILDREN, {}, clear=True), \
                    patch.object(manager, 'verify_identity', side_effect=[True, result]) as verify, \
                    patch.object(manager, '_healthy', return_value=True) as health, \
                    patch.object(manager.time, 'sleep') as sleep:
                with self.assertRaises(manager.ProcessError) as failure:
                    manager.wait_healthy(self.saved, timeout=60)
                self.assertEqual(failure.exception.reason, reason)
                self.assertNotIn('synthetic-private', str(failure.exception))
                self.assertEqual(verify.call_count, 2)
                health.assert_called_once()
                sleep.assert_not_called()

    def test_unknown_port_owner_is_never_spawned_or_stopped(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            with patch.object(manager.subprocess, 'Popen') as spawn:
                with self.assertRaises(manager.ProcessError):
                    manager.start_server(sys.executable, '.', {}, '127.0.0.1', listener.getsockname()[1], '.')
                spawn.assert_not_called()

    def test_reused_pid_refuses_all_signals(self):
        for field in ('executable', 'created_at'):
            with self.subTest(field=field), patch.object(manager, '_identity', return_value={**self.saved, field: 'different'}), \
                    patch.object(manager.subprocess, 'Popen') as helper, patch.object(manager.os, 'killpg', create=True) as send:
                with self.assertRaisesRegex(manager.ProcessError, 'identity changed'):
                    manager.stop_server(self.saved)
                helper.assert_not_called()
                send.assert_not_called()

    def test_stopped_identity_does_not_signal(self):
        with patch.object(manager, '_identity', return_value=None), patch.object(manager.subprocess, 'Popen') as helper, \
                patch.object(manager.os, 'killpg', create=True) as send:
            manager.stop_server(self.saved)
            helper.assert_not_called()
            send.assert_not_called()

    def test_one_graceful_signal_then_timeout_without_force(self):
        helper = Mock()
        helper.wait.return_value = 0
        with patch.object(manager, '_identity', return_value=self.saved), \
                patch.object(manager.os, 'getpgid', return_value=123, create=True), \
                patch.object(manager.os, 'killpg', create=True) as send, \
                patch.object(manager.subprocess, 'Popen', return_value=helper) as spawn:
            with self.assertRaisesRegex(manager.ProcessError, 'not force-killed'):
                manager.stop_server(self.saved, timeout=.01)
            self.assertEqual(spawn.call_count + send.call_count, 1)
            helper.terminate.assert_not_called()
            helper.kill.assert_not_called()

    def test_explicit_environment_and_local_logs_are_used(self):
        child = Mock(pid=123)
        env = {'SYNTHETIC_PRIVATE': 'never-print-this'}
        with tempfile.TemporaryDirectory() as directory, patch.object(manager, 'port_is_free', return_value=True), \
                patch.object(manager, '_identity', return_value=self.saved), \
                patch.object(manager.subprocess, 'Popen', return_value=child) as spawn:
            result = manager.start_server(sys.executable, directory, env, '127.0.0.1', 8080, Path(directory) / 'logs')
            self.assertIs(spawn.call_args.kwargs['env'], env)
            self.assertEqual(spawn.call_args.kwargs['stderr'], subprocess.STDOUT)
            self.assertEqual(spawn.call_args.kwargs['stdin'], subprocess.DEVNULL)
            self.assertNotIn('never-print-this', json.dumps(result))
            self.assertTrue(Path(result['log_file']).is_file())
            manager._CHILDREN.pop(123, None)

    def test_launched_child_with_unverifiable_identity_blocks_automatic_recovery(self):
        for outcome in (None, manager.ProcessError('synthetic-private-inspection-error')):
            with self.subTest(outcome=type(outcome).__name__), tempfile.TemporaryDirectory() as directory:
                child = Mock(pid=123)
                child.poll.return_value = None
                effect = {'side_effect': outcome} if isinstance(outcome, Exception) else {'return_value': None}
                with patch.object(manager, 'port_is_free', return_value=True), \
                        patch.object(manager, '_identity', **effect), \
                        patch.object(manager.subprocess, 'Popen', return_value=child):
                    with self.assertRaises(manager.LaunchUncertain) as failure:
                        manager.start_server(sys.executable, directory, {}, '127.0.0.1', 8080, directory)
                    self.assertNotIn('synthetic-private', str(failure.exception))
                    self.assertEqual(failure.exception.reason, 'launch_unverified')
                    self.assertEqual(failure.exception.log_id, next(Path(directory).glob('*.log')).name)
                    self.assertGreaterEqual(failure.exception.elapsed_seconds, 0)
                    child.terminate.assert_not_called()
                    child.kill.assert_not_called()
                manager._CHILDREN.pop(123, None)

    def test_child_confirmed_exited_is_an_ordinary_startup_failure(self):
        child = Mock(pid=123)
        child.poll.return_value = 7
        with tempfile.TemporaryDirectory() as directory, patch.object(manager, 'port_is_free', return_value=True), \
                patch.object(manager, '_identity', return_value=None), \
                patch.object(manager.subprocess, 'Popen', return_value=child):
            with self.assertRaises(manager.ProcessError) as failure:
                manager.start_server(sys.executable, directory, {}, '127.0.0.1', 8080, directory)
            self.assertNotIsInstance(failure.exception, manager.LaunchUncertain)
            self.assertEqual(failure.exception.reason, 'process_exited')
            self.assertEqual(failure.exception.exit_code, 7)
            self.assertEqual(failure.exception.log_id, next(Path(directory).glob('*.log')).name)
            manager._CHILDREN.pop(123, None)

    def test_invalid_listen_address_never_uses_dns(self):
        with patch.object(manager.socket, 'getaddrinfo') as dns:
            for host, port in [('example.invalid', 80), ('127.0.0.1', True), ('127.0.0.1', 0)]:
                with self.assertRaises(manager.ProcessError):
                    manager.port_is_free(host, port)
            dns.assert_not_called()

    def test_actual_health_requests_ignore_proxy_reject_redirect_and_false(self):
        received = []
        class Handler(BaseHTTPRequestHandler):
            mode = 'normal'
            def do_GET(self):
                received.append(self.path)
                if self.mode == 'redirect':
                    self.send_response(302)
                    self.send_header('Location', '/other')
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(json.dumps({'status': self.mode == 'normal'}).encode())
            def log_message(self, *_):
                pass
        with HTTPServer(('127.0.0.1', 0), Handler) as server:
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                with patch.dict(os.environ, {'HTTP_PROXY': 'http://127.0.0.1:1', 'NO_PROXY': ''}):
                    self.assertTrue(manager._healthy('127.0.0.1', server.server_port, 1))
                    Handler.mode = 'redirect'
                    self.assertFalse(manager._healthy('127.0.0.1', server.server_port, 1))
                    Handler.mode = 'false'
                    self.assertFalse(manager._healthy('127.0.0.1', server.server_port, 1))
                self.assertEqual(received, ['/health', '/health', '/health'])
            finally:
                server.shutdown()
                worker.join(timeout=2)


class CustomizedLauncherTests(unittest.TestCase):
    """Execute the real selected-program child code with a synthetic app."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.cwd, self.data, self.program = (self.root / name for name in ('working', 'data', 'program'))
        for directory in (self.cwd, self.data, self.program):
            directory.mkdir()
        self.package = self.program / 'open_webui'
        self.package.mkdir()
        self.version = branding.VERSION
        self.frontend_name = branding.PROGRAM_FRONTENDS[self.version]
        self.info = self.program / f'open_webui-{self.version}.dist-info'
        self.info.mkdir()
        self.metadata = self.info / 'METADATA'
        self.metadata.write_text(f'Metadata-Version: 2.1\nName: open-webui\nVersion: {self.version}\n', encoding='utf-8')
        frontend = self.package / 'frontend'
        (frontend / self.frontend_name).mkdir(parents=True)
        (frontend / 'index.html').write_text('synthetic-selected-frontend', encoding='utf-8')
        (frontend / self.frontend_name / 'version.json').write_text(json.dumps({'version': self.version}), encoding='utf-8')
        (self.data / 'webui.db').write_bytes(b'synthetic-existing-data')
        (self.cwd / '.webui_secret_key').write_bytes(b'synthetic-existing-key')
        (self.package / '__init__.py').write_text('''
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import sys
import cryptography
Path('imported.txt').write_text('selected', encoding='utf-8')
def serve(*, host, port):
    Path('observed.json').write_text(json.dumps({
        'code': __file__, 'metadata_root': str(metadata.distribution('open-webui').locate_file('')),
        'version': metadata.version('open-webui'), 'dependency': cryptography.__file__,
        'static': (Path(__file__).parent / 'frontend' / 'index.html').read_text(encoding='utf-8'),
        'prefix': sys.prefix, 'executable': sys.executable, 'cwd': str(Path.cwd()),
        'data': os.environ['DATA_DIR'], 'path_type': type(sys.path[0]).__name__,
        'host': host, 'port': port}), encoding='utf-8')
''', encoding='utf-8')
        self.env = {**os.environ, 'DATA_DIR': str(self.data)}
        for name in ('WEBUI_SECRET_KEY', 'UVICORN_WORKERS', 'WEB_CONCURRENCY', 'UVICORN_RELOAD', 'WEBUI_RELOAD'):
            self.env.pop(name, None)

    def command(self, program_path=None, *, original=False, version=None):
        saved = {'pid': 123, 'executable': 'python', 'created_at': '456'}
        child = Mock(pid=123)
        with patch.object(manager, 'port_is_free', return_value=True), \
                patch.object(manager, '_identity', return_value=saved), \
                patch.object(manager.subprocess, 'Popen', return_value=child) as spawn, \
                patch.object(sys, 'path', [str(MODULE.parent), *sys.path]):
            options = {} if original else {'program_path': str(self.program) if program_path is None else program_path}
            if version is not None:
                options['program_version'] = version
            try:
                manager.start_server(sys.executable, self.cwd, self.env, '127.0.0.1', 8080,
                                     self.root / 'logs', **options)
            finally:
                manager._CHILDREN.pop(123, None)
        return spawn.call_args.args[0]

    def run_child(self):
        return subprocess.run(self.command(), cwd=self.cwd, env=self.env, capture_output=True,
                              text=True, timeout=15)

    def assert_rejected_without_app_import(self):
        result = self.run_child()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('no fallback was started', result.stderr)
        self.assertNotIn(str(self.root), result.stderr)
        self.assertNotIn('synthetic-existing-key', result.stderr)
        self.assertFalse((self.cwd / 'imported.txt').exists())

    def test_actual_child_selects_code_metadata_static_and_existing_dependency(self):
        import cryptography
        result = self.run_child()
        self.assertEqual(result.returncode, 0, result.stderr)
        observation = json.loads((self.cwd / 'observed.json').read_text(encoding='utf-8'))
        self.assertEqual(Path(observation['code']), self.package / '__init__.py')
        self.assertEqual(Path(observation['metadata_root']), self.program)
        self.assertEqual(observation['version'], self.version)
        self.assertEqual(Path(observation['dependency']), Path(cryptography.__file__))
        self.assertEqual(observation['static'], 'synthetic-selected-frontend')
        self.assertEqual(observation['prefix'], sys.prefix)
        self.assertEqual(Path(observation['executable']).absolute(), Path(sys.executable).absolute())
        self.assertEqual(Path(observation['cwd']), self.cwd)
        self.assertEqual(Path(observation['data']), self.data)
        self.assertEqual((observation['path_type'], observation['host'], observation['port']),
                         ('str', '127.0.0.1', 8080))
        self.assertFalse(list(self.program.rglob('__pycache__')))
        self.assertEqual((self.data / 'webui.db').read_bytes(), b'synthetic-existing-data')
        self.assertEqual((self.cwd / '.webui_secret_key').read_bytes(), b'synthetic-existing-key')

    def test_original_command_is_unchanged_and_customized_command_is_isolated(self):
        self.assertEqual(self.command(original=True),
                         [str(Path(sys.executable).absolute()), '-c', manager.SERVER_CODE, '127.0.0.1', '8080'])
        selected = self.command()
        self.assertEqual(selected[1:4], ['-I', '-B', '-c'])
        self.assertEqual(selected[4], manager.CUSTOMIZED_SERVER_CODE)
        self.assertEqual(selected[7:], [str(self.program), self.version, self.info.name, self.frontend_name])

    def test_legacy_selected_version_launches_after_wrapper_update(self):
        for legacy, namespace in (('0.11.3+ees.1', '_ees1'), ('0.11.3+ees.2', '_ees2'), ('0.11.3+ees.3', '_ees3')):
            with self.subTest(version=legacy):
                self.setUp()
                legacy_info = self.program / f'open_webui-{legacy}.dist-info'
                self.info.rename(legacy_info)
                (legacy_info / 'METADATA').write_text(f'Name: open-webui\nVersion: {legacy}\n', encoding='utf-8')
                frontend = self.package / 'frontend'
                (frontend / self.frontend_name).rename(frontend / namespace)
                (frontend / namespace / 'version.json').write_text(json.dumps({'version': legacy}), encoding='utf-8')
                result = subprocess.run(self.command(version=legacy), cwd=self.cwd, env=self.env,
                                        capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads((self.cwd / 'observed.json').read_text(encoding='utf-8'))['version'], legacy)

    def test_unsupported_and_mixed_release_arguments_refuse_app_import(self):
        for version in ('0.11.3+ees.5', [], '0.11.3'):
            with self.subTest(version=version), self.assertRaises(manager.ProcessError):
                self.command(version=version)
        for index, value in ((8, '0.11.3+ees.5'), (9, 'open_webui-0.11.3+ees.1.dist-info'), (10, '_ees1')):
            command = self.command()
            command[index] = value
            with self.subTest(index=index):
                result = subprocess.run(command, cwd=self.cwd, env=self.env, capture_output=True, text=True, timeout=15)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('no fallback was started', result.stderr)
                self.assertFalse((self.cwd / 'imported.txt').exists())

    def test_nonabsolute_or_nonstring_program_path_refuses_launch(self):
        for value in ('relative', str(self.root / 'missing'), self.program):
            with self.subTest(value=type(value).__name__), self.assertRaises(manager.ProcessError):
                self.command(value)

    def test_missing_code_metadata_or_static_never_falls_back(self):
        for target in (self.package / '__init__.py', self.metadata, self.package / 'frontend' / 'index.html',
                       self.package / 'frontend' / self.frontend_name / 'version.json'):
            with self.subTest(target=target.name):
                original = target.read_bytes()
                target.unlink()
                try:
                    self.assert_rejected_without_app_import()
                finally:
                    target.write_bytes(original)

    def test_missing_selection_never_imports_an_available_original(self):
        original_root = self.root / 'original-installation'
        original_package = original_root / 'open_webui'
        original_package.mkdir(parents=True)
        (original_package / '__init__.py').write_text(
            "from pathlib import Path\nPath('original-imported.txt').write_text('unexpected')\n", encoding='utf-8')
        original_info = original_root / 'open_webui-0.11.3.dist-info'
        original_info.mkdir()
        (original_info / 'METADATA').write_text(
            'Metadata-Version: 2.1\nName: open-webui\nVersion: 0.11.3\n', encoding='utf-8')
        for target in (self.package / '__init__.py', self.metadata):
            with self.subTest(target=target.name):
                content = target.read_bytes()
                target.unlink()
                try:
                    command = self.command()
                    # Model an already installed official package without installing one.
                    # The complete production entry point follows this search-path fixture.
                    command[4] = ('import sys\nsys.path.append(' + repr(str(original_root)) + ')\n'
                                  + command[4])
                    result = subprocess.run(command, cwd=self.cwd, env=self.env, capture_output=True,
                                            text=True, timeout=15)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('no fallback was started', result.stderr)
                    self.assertFalse((self.cwd / 'original-imported.txt').exists())
                    self.assertFalse((self.cwd / 'imported.txt').exists())
                finally:
                    target.write_bytes(content)

    def test_mismatched_metadata_or_static_version_refuses_import(self):
        for target in (self.metadata, self.package / 'frontend' / self.frontend_name / 'version.json'):
            with self.subTest(target=target.name):
                original = target.read_bytes()
                target.write_bytes(original.replace(self.version.encode(), b'0.11.3'))
                try:
                    self.assert_rejected_without_app_import()
                finally:
                    target.write_bytes(original)

    def test_existing_data_and_existing_key_are_required_before_import(self):
        for name, value in (('DATA_DIR', None), ('DATA_DIR', 'relative'),
                            ('DATA_DIR', str(self.root / 'missing')), ('WEBUI_SECRET_KEY', ' '),
                            ('UVICORN_WORKERS', '2'), ('WEB_CONCURRENCY', '2'),
                            ('UVICORN_RELOAD', 'true'), ('WEBUI_RELOAD', '1')):
            with self.subTest(name=name, value=value):
                previous = self.env.pop(name, None)
                if value is not None:
                    self.env[name] = value
                try:
                    self.assert_rejected_without_app_import()
                finally:
                    self.env.pop(name, None)
                    if previous is not None:
                        self.env[name] = previous
        (self.cwd / '.webui_secret_key').unlink()
        self.assert_rejected_without_app_import()
        self.env['WEBUI_SECRET_KEY'] = 'synthetic-environment-key'
        result = self.run_child()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.cwd / '.webui_secret_key').exists())

    def test_unexpected_dotenv_stops_before_import_and_preserves_file(self):
        for directory in (self.cwd, self.package, self.program, self.program.parent):
            with self.subTest(directory=directory.name):
                dotenv = directory / '.env'
                dotenv.write_bytes(b'WEBUI_SECRET_KEY=synthetic-private')
                try:
                    self.assert_rejected_without_app_import()
                    self.assertEqual(dotenv.read_bytes(), b'WEBUI_SECRET_KEY=synthetic-private')
                finally:
                    dotenv.unlink()


if __name__ == '__main__':
    unittest.main()
