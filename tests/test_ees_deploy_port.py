"""Bounded port checks only: synthetic Winsock errors and real local sockets.

No Open WebUI, real application data, or external service is used. The Linux
lifecycle test signals only its own bounded fake child through the real manager.
Synthetic Windows branches do not establish real Winsock/TIME_WAIT behavior.
"""

import errno
import importlib.util
import socket
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

MODULE = Path(__file__).resolve().parents[1] / 'scripts' / 'ees_deploy_process.py'
SPEC = importlib.util.spec_from_file_location('ees_deploy_port_test', MODULE)
process = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(process)


def windows_error(code=10048, *, winerror=True):
    error = OSError(code, 'synthetic-private-address-and-path')
    if winerror:
        error.winerror = code
    return error


class PortRetryTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.sleeps = []
        self.sockets = []
        self.effects = []
        self.exit_error = None
        self.os = SimpleNamespace(name='nt')
        self.clock = SimpleNamespace(monotonic=lambda: self.now, sleep=self.sleep)
        self.factory = Mock(side_effect=self.make_socket)
        for target, name, value in (
            (process, 'os', self.os), (process, 'time', self.clock),
            (process.socket, 'socket', self.factory),
        ):
            item = patch.object(target, name, value)
            item.start()
            self.addCleanup(item.stop)

    def sleep(self, duration):
        self.assertTrue(all(item.closed for item in self.sockets))
        self.assertGreater(duration, 0)
        self.sleeps.append(duration)
        self.now += duration

    def make_socket(self, *args):
        item = Mock()
        item.closed = False
        item.family_args = args
        item.setsockopt = Mock()
        item.bind = Mock(side_effect=self.bind)
        context = Mock()
        context.__enter__ = Mock(return_value=item)

        def close(*_):
            item.closed = True
            if self.exit_error:
                raise self.exit_error
            return False

        context.__exit__ = Mock(side_effect=close)
        self.sockets.append(item)
        return context

    def bind(self, target):
        self.assertIn(target, [('127.0.0.1', 8080), ('::1', 8080)])
        effect = self.effects.pop(0) if self.effects else None
        if isinstance(effect, BaseException):
            raise effect

    def test_transient_windows_busy_recovers_without_reuse(self):
        self.effects = [windows_error(), windows_error(), None]
        self.assertTrue(process.port_is_free('127.0.0.1', 8080, raise_on_error=True))
        self.assertEqual(len(self.sockets), 3)
        self.assertEqual(self.sleeps, [.25, .25])
        for item in self.sockets:
            item.setsockopt.assert_not_called()
            self.assertTrue(item.closed)

    def test_immediate_success_does_not_wait(self):
        self.assertTrue(process.port_is_free('127.0.0.1', 8080, raise_on_error=True))
        self.assertEqual(len(self.sockets), 1)
        self.assertEqual(self.sleeps, [])

    def test_continuous_busy_is_bounded_and_preserves_error(self):
        self.effects = [windows_error() for _ in range(100)]
        with self.assertRaises(process.ProcessError) as caught:
            process.port_is_free('127.0.0.1', 8080, raise_on_error=True)
        error = caught.exception
        self.assertEqual((error.operation, error.errno, error.winerror), ('port_bind', 10048, 10048))
        self.assertEqual(error.timeout_seconds, 10)
        self.assertEqual(error.elapsed_seconds, 10)
        self.assertLessEqual(len(self.sockets), 41)
        self.assertEqual(sum(self.sleeps), 10)
        self.assertTrue(all(item.closed for item in self.sockets))
        self.assertNotIn('synthetic-private', str(error))

    def test_stalled_clock_still_has_an_attempt_limit(self):
        self.effects = [windows_error() for _ in range(100)]
        self.clock.sleep = Mock()
        with self.assertRaises(process.ProcessError) as caught:
            process.port_is_free('127.0.0.1', 8080, raise_on_error=True)
        self.assertEqual(len(self.sockets), 41)
        self.assertEqual(self.clock.sleep.call_count, 40)
        self.assertEqual(caught.exception.timeout_seconds, 10)
        self.assertTrue(all(item.closed for item in self.sockets))

    def test_final_sleep_is_capped_to_remaining_budget(self):
        self.effects = [windows_error() for _ in range(3)]
        self.clock.monotonic = Mock(side_effect=[100.0, 109.9, 110.0, 110.0])
        with self.assertRaises(process.ProcessError):
            process.port_is_free('127.0.0.1', 8080, raise_on_error=True)
        self.assertEqual(len(self.sleeps), 2)
        self.assertEqual(self.sleeps[0], .25)
        self.assertAlmostEqual(self.sleeps[1], .1)

    def test_boolean_probe_remains_single_attempt(self):
        self.effects = [windows_error(), None]
        self.assertFalse(process.port_is_free('127.0.0.1', 8080))
        self.assertEqual(len(self.sockets), 1)
        self.assertEqual(self.sleeps, [])

    def test_non_windows_busy_does_not_retry(self):
        self.os.name = 'posix'
        self.effects = [OSError(errno.EADDRINUSE, 'busy')]
        with self.assertRaises(process.ProcessError):
            process.port_is_free('127.0.0.1', 8080, raise_on_error=True)
        self.assertEqual(self.sleeps, [])
        self.sockets[0].setsockopt.assert_called_once_with(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def test_errno_only_windows_busy_is_supported(self):
        self.effects = [windows_error(winerror=False), None]
        self.assertTrue(process.port_is_free('127.0.0.1', 8080, raise_on_error=True))
        self.assertEqual(self.sleeps, [.25])

    def test_access_denied_does_not_retry(self):
        self.effects = [windows_error(10013)]
        with self.assertRaises(process.ProcessError) as caught:
            process.port_is_free('127.0.0.1', 8080, raise_on_error=True)
        self.assertEqual(caught.exception.winerror, 10013)
        self.assertEqual(self.sleeps, [])

    def test_missing_interface_does_not_retry(self):
        self.effects = [windows_error(10049)]
        with self.assertRaises(process.ProcessError) as caught:
            process.port_is_free('127.0.0.1', 8080, raise_on_error=True)
        self.assertEqual(caught.exception.winerror, 10049)
        self.assertEqual(self.sleeps, [])

    def test_non_busy_error_after_retry_is_not_hidden(self):
        self.effects = [windows_error(), windows_error(10013)]
        with self.assertRaises(process.ProcessError) as caught:
            process.port_is_free('127.0.0.1', 8080, raise_on_error=True)
        self.assertEqual(caught.exception.winerror, 10013)
        self.assertEqual(self.sleeps, [.25])

    def test_winerror_takes_precedence_over_errno(self):
        error = windows_error()
        error.winerror = 10013
        self.effects = [error]
        with self.assertRaises(process.ProcessError):
            process.port_is_free('127.0.0.1', 8080, raise_on_error=True)
        self.assertEqual(self.sleeps, [])

    def test_socket_creation_error_is_not_retried(self):
        self.factory.side_effect = windows_error()
        with self.assertRaises(process.ProcessError) as caught:
            process.port_is_free('127.0.0.1', 8080, raise_on_error=True)
        self.assertEqual(caught.exception.operation, 'port_probe')
        self.assertEqual(self.sleeps, [])

    def test_socket_close_error_is_not_retried(self):
        self.exit_error = windows_error()
        with self.assertRaises(process.ProcessError) as caught:
            process.port_is_free('127.0.0.1', 8080, raise_on_error=True)
        self.assertEqual(caught.exception.operation, 'port_probe')
        self.assertEqual(self.sleeps, [])

    def test_close_error_after_failed_bind_is_not_retried(self):
        for bind_code, close_code in ((10048, 10048), (10013, 10048), (10048, 10013)):
            with self.subTest(bind_code=bind_code, close_code=close_code):
                self.effects = [windows_error(bind_code)]
                self.exit_error = windows_error(close_code)
                self.sleeps.clear()
                self.sockets.clear()
                with self.assertRaises(process.ProcessError) as caught:
                    process.port_is_free('127.0.0.1', 8080, raise_on_error=True)
                self.assertEqual(caught.exception.operation, 'port_probe')
                self.assertEqual(caught.exception.winerror, close_code)
                self.assertEqual(self.sleeps, [])
                self.assertEqual(len(self.sockets), 1)
                self.assertIsNone(caught.exception.timeout_seconds)

    def test_close_error_after_successful_retry_is_not_hidden(self):
        self.effects = [windows_error(), None]
        original_sleep = self.clock.sleep

        def after_wait(duration):
            original_sleep(duration)
            self.exit_error = windows_error()

        self.clock.sleep = after_wait
        with self.assertRaises(process.ProcessError) as caught:
            process.port_is_free('127.0.0.1', 8080, raise_on_error=True)
        self.assertEqual(caught.exception.operation, 'port_probe')
        self.assertEqual(self.sleeps, [.25])
        self.assertEqual(len(self.sockets), 2)

    def test_invalid_input_does_not_open_socket(self):
        for host, port in [('localhost', 8080), ('127.0.0.1', True), ('127.0.0.1', 0), ('fe80::1%1', 8080)]:
            with self.subTest(host=host, port=port), self.assertRaises(process.ProcessError):
                process.port_is_free(host, port, raise_on_error=True)
        self.factory.assert_not_called()

    def test_ipv6_uses_the_same_bounded_path(self):
        self.effects = [windows_error(), None]
        self.assertTrue(process.port_is_free('::1', 8080, raise_on_error=True))
        self.assertTrue(all(item.family_args == (socket.AF_INET6,) for item in self.sockets))

    def test_keyboard_interrupt_is_not_swallowed(self):
        self.effects = [KeyboardInterrupt()]
        with self.assertRaises(KeyboardInterrupt):
            process.port_is_free('127.0.0.1', 8080, raise_on_error=True)
        self.assertEqual(self.sleeps, [])
        self.assertTrue(self.sockets[0].closed)

    def test_start_never_launches_or_signals_on_persistent_busy(self):
        self.effects = [windows_error() for _ in range(100)]
        with patch.object(process.subprocess, 'Popen') as spawn, \
                patch.object(process, 'stop_server') as stop, \
                patch.object(process, 'terminate_registered_process') as terminate:
            with self.assertRaises(process.ProcessError):
                process.start_server('unused', 'unused', {}, '127.0.0.1', 8080, 'unused')
            spawn.assert_not_called()
            stop.assert_not_called()
            terminate.assert_not_called()


class RealPortTests(unittest.TestCase):
    def test_real_listener_stays_owned_and_usable(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen(1)
            port = listener.getsockname()[1]
            self.assertFalse(process.port_is_free('127.0.0.1', port))
            with socket.create_connection(('127.0.0.1', port), timeout=2) as client:
                accepted, _ = listener.accept()
                with accepted:
                    client.sendall(b'preserved')
                    self.assertEqual(accepted.recv(9), b'preserved')

    def test_real_unused_port_is_available(self):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        self.assertTrue(process.port_is_free('127.0.0.1', port, raise_on_error=True))


@unittest.skipUnless(sys.platform.startswith('linux'), 'Local lifecycle uses Linux; Windows remains a separate gate.')
class LocalLifecycleTests(unittest.TestCase):
    def test_owned_fake_child_stops_and_reuses_port(self):
        if int(Path('/proc/self/stat').read_text(encoding='utf-8').split()[0]) != os.getpid():
            self.skipTest('The mounted /proc uses a different PID namespace.')
        server_code = '''
import json, signal, sys, time
from http.server import HTTPServer, BaseHTTPRequestHandler
running = True
def stop(*_):
    global running
    running = False
signal.signal(signal.SIGINT, stop)
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({'status': True}).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *_):
        pass
server = HTTPServer((sys.argv[1], int(sys.argv[2])), Handler)
server.timeout = .1
end = time.monotonic() + 10
try:
    while running and time.monotonic() < end:
        server.handle_request()
finally:
    server.server_close()
'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sentinel = root / 'synthetic-user-skill.txt'
            sentinel.write_text('synthetic retained asset', encoding='utf-8')
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', 0))
                port = probe.getsockname()[1]
            with patch.object(process, 'SERVER_CODE', server_code):
                for _ in range(2):
                    identity = process.start_server(sys.executable, root, dict(os.environ),
                                                    '127.0.0.1', port, root / 'logs')
                    try:
                        process.wait_healthy(identity, timeout=5)
                        self.assertFalse(process.port_is_free('127.0.0.1', port))
                    finally:
                        process.stop_server(identity, timeout=3)
                    self.assertFalse(process.verify_identity(identity))
                    self.assertTrue(process.port_is_free('127.0.0.1', port, raise_on_error=True))
            self.assertEqual(sentinel.read_text(encoding='utf-8'), 'synthetic retained asset')


if __name__ == '__main__':
    unittest.main()
