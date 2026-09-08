"""Real local fake-child lifecycle tests; never import or install Open WebUI."""

import importlib.util
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
from unittest.mock import Mock, patch


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
        self.assertEqual(len(list((self.root / 'logs').glob('*.log'))), 1)

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


if __name__ == '__main__':
    unittest.main()
