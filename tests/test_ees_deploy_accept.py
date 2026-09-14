"""WinError64 recovery, ownership/cancellation, and Windows real IOCP smoke.

The Windows test injects a synthetic 64 ONLY after a real AcceptEx completion.
It never contacts an EES instance, changes system Python, or reads a database.
"""

import asyncio
import contextlib
import io
import socket
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import ees_deploy_accept as guard


def winerror(number):
    error = OSError('synthetic private data must not be logged')
    error.winerror = number
    return error


class Socket:
    family = socket.AF_INET
    def __init__(self):
        self.fd = 25
        self.closed = 0
    def fileno(self):
        return self.fd
    def close(self):
        self.closed += 1
        self.fd = -1
    def setsockopt(self, *args):
        pass
    def settimeout(self, timeout):
        pass
    def gettimeout(self):
        return 0
    def getpeername(self):
        return ('127.0.0.1', 10000)


class Overlapped:
    SO_UPDATE_ACCEPT_CONTEXT = 123
    def __init__(self, error=None, synchronous=False):
        self.error = error
        self.synchronous = synchronous
    def Overlapped(self, _zero):
        return self
    def AcceptEx(self, *args):
        if self.synchronous and self.error:
            error, self.error = self.error, None
            raise error
    def getresult(self):
        if self.error:
            error, self.error = self.error, None
            raise error


class Proactor:
    def __init__(self, loop, pending=False):
        self._loop = loop
        self._stopped_serving = set()
        self.sockets = []
        self.pending = pending
        self.futures = []
        self.callback = None
        self.overlapped = None
    def _check_closed(self):
        if self._loop.is_closed():
            raise RuntimeError('closed')
    def _register_with_iocp(self, listener):
        pass
    def _get_accept_socket(self, family):
        conn = Socket()
        self.sockets.append(conn)
        return conn
    def _register(self, ov, listener, callback):
        future = self._loop.create_future()
        self.futures.append(future)
        self.callback, self.overlapped = callback, ov
        if not self.pending:
            try:
                future.set_result(callback(None, None, ov))
            except OSError as exc:
                future.set_exception(exc)
        return future


class AcceptTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.loop = asyncio.get_running_loop()
        self.proactor = Proactor(self.loop)
        self.listener = Socket()

    async def test_success_transfers_socket_ownership(self):
        conn, address = await guard._make_accept(Overlapped())(self.proactor, self.listener)
        self.assertIs(conn, self.proactor.sockets[0])
        self.assertEqual(conn.closed, 0)
        self.assertEqual(self.listener.closed, 0)
        conn.close()

    async def test_completion64_closes_only_failed_client_and_retries(self):
        with patch.object(guard, 'RETRY_DELAY', 0), self.assertLogs(guard._logger, 'WARNING') as logs:
            conn, _ = await guard._make_accept(Overlapped(winerror(64)))(self.proactor, self.listener)
        self.assertEqual([s.closed for s in self.proactor.sockets], [1, 0])
        self.assertEqual(self.listener.closed, 0)
        self.assertNotIn('private', ''.join(logs.output))
        conn.close()

    async def test_synchronous64_also_retries(self):
        with patch.object(guard, 'RETRY_DELAY', 0), patch.object(guard._logger, 'warning'):
            conn, _ = await guard._make_accept(Overlapped(winerror(64), True))(self.proactor, self.listener)
        self.assertEqual(len(self.proactor.sockets), 2)
        self.assertEqual(self.proactor.sockets[0].closed, 1)
        conn.close()

    async def test_other_os_errors_are_not_swallowed(self):
        for number in (5, 6, 995, 10038, 10054):
            with self.subTest(number=number):
                proactor = Proactor(self.loop)
                error = winerror(number)
                with self.assertRaises(OSError) as caught:
                    await guard._make_accept(Overlapped(error))(proactor, self.listener)
                self.assertIs(caught.exception, error)
                self.assertEqual(len(proactor.sockets), 1)
                self.assertEqual(proactor.sockets[0].closed, 1)

    async def test_non_os_error_closes_client(self):
        with patch.object(self.proactor, '_register', side_effect=ValueError('synthetic')):
            with self.assertRaises(ValueError):
                await guard._make_accept(Overlapped())(self.proactor, self.listener)
        self.assertEqual(self.proactor.sockets[0].closed, 1)

    async def test_cancellation_propagates_to_pending_overlapped(self):
        self.proactor.pending = True
        task = guard._make_accept(Overlapped())(self.proactor, self.listener)
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(self.proactor.futures[0].cancelled())
        self.assertEqual(self.proactor.sockets[0].closed, 1)

    async def test_cancel_after_completion_before_task_resume_closes_socket(self):
        self.proactor.pending = True
        task = guard._make_accept(Overlapped())(self.proactor, self.listener)
        await asyncio.sleep(0)
        result = self.proactor.callback(None, None, self.proactor.overlapped)
        self.proactor.futures[0].set_result(result)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.proactor.sockets[0].closed, 1)

    async def test_cancel_before_first_step_creates_no_socket(self):
        task = guard._make_accept(Overlapped())(self.proactor, self.listener)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.proactor.sockets, [])

    async def test_closed_or_stopped_listener_is_not_reopened(self):
        for closed in (True, False):
            proactor = Proactor(self.loop)
            listener = Socket()
            if closed:
                listener.close()
            else:
                proactor._stopped_serving.add(listener)
            with self.assertRaises(asyncio.CancelledError):
                await guard._make_accept(Overlapped())(proactor, listener)
            self.assertEqual(proactor.sockets, [])

    async def test_cancel_during_retry_delay_does_not_restart_accept(self):
        waiting = asyncio.Event()
        async def delay(seconds):
            self.assertGreater(seconds, 0)
            waiting.set()
            await asyncio.Future()
        with patch.object(guard.asyncio, 'sleep', delay), patch.object(guard._logger, 'warning'):
            task = guard._make_accept(Overlapped(winerror(64)))(self.proactor, self.listener)
            await waiting.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(len(self.proactor.sockets), 1)
        self.assertEqual(self.proactor.sockets[0].closed, 1)

    async def test_repeated64_is_delayed_and_bounded_in_logging(self):
        class Repeated(Overlapped):
            n = 0
            def getresult(self):
                self.n += 1
                if self.n <= 16:
                    raise winerror(64)
        delays = []
        async def delay(seconds):
            delays.append(seconds)
        with patch.object(guard.asyncio, 'sleep', delay), self.assertLogs(guard._logger, 'WARNING') as logs:
            conn, _ = await guard._make_accept(Repeated())(self.proactor, self.listener)
        self.assertEqual(len(delays), 16)
        self.assertTrue(all(v > 0 for v in delays))
        self.assertEqual(len(logs.output), 5)
        self.assertEqual([s.closed for s in self.proactor.sockets], [1] * 16 + [0])
        conn.close()

    async def test_shutdown_during_delay_never_issues_another_accept(self):
        for close_socket in (True, False):
            proactor, listener = Proactor(self.loop), Socket()
            async def delay(seconds):
                if close_socket:
                    listener.close()
                else:
                    proactor._stopped_serving.add(listener)
            with patch.object(guard.asyncio, 'sleep', delay), patch.object(guard._logger, 'warning'):
                with self.assertRaises(asyncio.CancelledError):
                    await guard._make_accept(Overlapped(winerror(64)))(proactor, listener)
            self.assertEqual(len(proactor.sockets), 1)
            self.assertEqual(proactor.sockets[0].closed, 1)


class InstallationTests(unittest.TestCase):
    def test_non_windows_has_no_effect(self):
        with patch.object(guard.sys, 'platform', 'linux'):
            self.assertFalse(guard.install())

    def test_unknown_python_is_rejected(self):
        with patch.object(guard.sys, 'platform', 'win32'), patch.object(guard.sys, 'version_info', (3, 12)):
            with self.assertRaisesRegex(RuntimeError, 'requires reviewed'):
                guard.install()

    def test_unknown_source_is_rejected(self):
        def foreign(proactor, listener):
            pass
        fake = SimpleNamespace(IocpProactor=type('P', (), {'accept': foreign}))
        with patch.object(guard.sys, 'platform', 'win32'), patch.object(guard.sys, 'version_info', (3, 11)), \
             patch.dict(sys.modules, {'_overlapped': SimpleNamespace(ERROR_NETNAME_DELETED=64)}), \
             patch.object(asyncio, 'windows_events', fake, create=True):
            with self.assertRaisesRegex(RuntimeError, 'does not recognize'):
                guard.install()
        self.assertIs(fake.IocpProactor.accept, foreign)


class LaunchWiringTests(unittest.TestCase):
    def test_preflight_failure_does_not_start_server_or_echo_child_output(self):
        import subprocess
        import ees_deploy_process as processes
        for result in (subprocess.CompletedProcess([], 1, b'private', b'private'),
                       subprocess.CompletedProcess([], 0, b'unexpected', b''),
                       subprocess.TimeoutExpired('private', 10), OSError('private')):
            with self.subTest(result=type(result).__name__), \
                 patch.object(processes.sys, 'platform', 'win32'), \
                 patch.object(processes.subprocess, 'run') as run:
                if isinstance(result, Exception):
                    run.side_effect = result
                else:
                    run.return_value = result
                with self.assertRaises(processes.ProcessError) as caught:
                    processes.check_accept_runtime('selected-python', 'selected-cwd')
                self.assertEqual(caught.exception.reason, 'accept_guard_incompatible')
                self.assertNotIn('private', str(caught.exception))
                command = run.call_args.args[0]
                self.assertEqual(command[0], 'selected-python')
                self.assertEqual(command[1:3], ['-I', '-B'])
                self.assertEqual(command[-1], '--check')
                self.assertNotIn('-c', command)
                self.assertEqual(run.call_args.kwargs['timeout'], 10)

    def test_preflight_success_and_marker_are_distinct(self):
        import tempfile
        import subprocess
        import ees_deploy_process as processes
        with tempfile.TemporaryDirectory() as folder, patch.object(processes.sys, 'platform', 'win32'):
            marker = Path(folder) / 'child.log'
            with patch.object(processes.subprocess, 'run', return_value=subprocess.CompletedProcess(
                    [], 0, b'EES accept_check=compatible\r\n', b'')):
                self.assertEqual(processes.check_accept_runtime('selected-python', folder), 'compatible')
            for text in ('', 'EES accept_check=compatible\n', 'prefix EES accept_guard=win64_retry loop=proactor\n'):
                marker.write_text(text)
                with self.assertRaises(processes.ProcessError):
                    processes.accept_guard_status({'log_file': str(marker)})
            marker.write_bytes(b'EES accept_guard=win64_retry loop=proactor\r\n')
            self.assertEqual(processes.accept_guard_status({'log_file': str(marker)}), 'win64_retry')

    def test_original_and_customized_keep_environment_and_install_before_webui(self):
        import tempfile
        import ees_deploy_process as processes
        from unittest.mock import Mock
        branding = SimpleNamespace(VERSION='0.11.3+ees.4',
                                   PROGRAM_FRONTENDS={'0.11.3+ees.4': '_ees4'})
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            program = root / 'program'
            program.mkdir()
            for selected in (None, str(program)):
                child = Mock(pid=123)
                identity = {'pid': 123, 'executable': sys.executable, 'created_at': '1'}
                env = {'SYNTHETIC_KEY': 'not-a-secret'}
                with self.subTest(customized=selected is not None), \
                     patch.dict(sys.modules, {'build_ees_webui': branding}), \
                     patch.object(processes, 'port_is_free', return_value=True), \
                     patch.object(processes, '_identity', return_value=identity), \
                     patch.object(processes.subprocess, 'Popen', return_value=child) as launch:
                    processes.start_server(sys.executable, root, env, '127.0.0.1', 18080,
                                           root / 'logs', program_path=selected)
                    args, options = launch.call_args
                    command = args[0]
                    code = command[command.index('-c') + 1]
                    self.assertLess(code.index("['install']()"), code.index('open_webui'))
                    self.assertIn('ees_deploy_accept.py', code)
                    self.assertIs(options['env'], env)
                    self.assertEqual(options['cwd'], root.resolve())
                    self.assertEqual(command[command.index('-c') + 2:][:2], ['127.0.0.1', '18080'])
                    if selected is not None:
                        self.assertIn('-I', command)
                        self.assertIn('-B', command)
                    processes._CHILDREN.pop(123, None)


@unittest.skipUnless(sys.platform == 'win32' and sys.version_info[:2] == (3, 11), 'Windows CPython 3.11 only')
class WindowsIocpTests(unittest.TestCase):
    def test_real_accept_reset_then_new_client_and_subprocess(self):
        from asyncio import windows_events
        old = windows_events.IocpProactor.accept
        old_installed = guard._INSTALLED
        contexts = []
        loop = None
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertTrue(guard.install())
                installed = windows_events.IocpProactor.accept
                self.assertTrue(guard.install())
                self.assertIs(windows_events.IocpProactor.accept, installed)
            loop = asyncio.ProactorEventLoop()
            loop.set_exception_handler(lambda loop, context: contexts.append(context))
            proactor = loop._proactor
            register = proactor._register
            injected = []
            completed_count = []
            sockets = []
            get_socket = proactor._get_accept_socket
            def track_socket(family):
                conn = get_socket(family)
                sockets.append(conn)
                return conn
            proactor._get_accept_socket = track_socket
            def instrument(ov, obj, callback):
                if callback.__name__ == 'finish_accept':
                    original = callback
                    def callback(transferred, key, completed):
                        completed_count.append(True)
                        if len(completed_count) == 2:
                            completed.getresult()  # Real IOCP completion, before synthetic reset.
                            injected.append(True)
                            raise winerror(64)
                        return original(transferred, key, completed)
                return register(ov, obj, callback)
            proactor._register = instrument

            class Reply(asyncio.Protocol):
                def connection_made(self, transport):
                    transport.write(b'ok')
                    transport.close()

            async def scenario():
                server = await loop.create_server(Reply, '127.0.0.1', 0)
                port = server.sockets[0].getsockname()[1]
                writers = []
                try:
                    reader, writer = await asyncio.open_connection('127.0.0.1', port)
                    writers.append(writer)
                    self.assertEqual(await asyncio.wait_for(reader.readexactly(2), 3), b'ok')
                    reader, writer = await asyncio.open_connection('127.0.0.1', port)
                    writers.append(writer)
                    try:
                        await asyncio.wait_for(reader.read(), 3)
                    except ConnectionResetError:
                        pass
                    self.assertEqual(injected, [True])
                    reader, writer = await asyncio.open_connection('127.0.0.1', port)
                    writers.append(writer)
                    self.assertEqual(await asyncio.wait_for(reader.readexactly(2), 3), b'ok')
                    self.assertTrue(server.is_serving())
                    proc = await asyncio.create_subprocess_exec(sys.executable, '-c', 'print("ok")',
                                                                stdout=asyncio.subprocess.PIPE)
                    output, _ = await asyncio.wait_for(proc.communicate(), 5)
                    self.assertEqual(output.strip(), b'ok')
                    self.assertEqual(proc.returncode, 0)
                finally:
                    for writer in writers:
                        writer.close()
                        with contextlib.suppress(ConnectionError):
                            await writer.wait_closed()
                    server.close()
                    await server.wait_closed()
                    await asyncio.sleep(0.05)
            with patch.object(guard._logger, 'warning'):
                loop.run_until_complete(scenario())
            self.assertEqual(contexts, [])
            self.assertTrue(sockets)
            self.assertTrue(all(conn.fileno() == -1 for conn in sockets))
            self.assertFalse(asyncio.all_tasks(loop))
        finally:
            if loop is not None:
                loop.close()
                self.assertEqual(loop._proactor, None)
            windows_events.IocpProactor.accept = old
            guard._INSTALLED = old_installed

    def test_real_completion_then_shutdown_during_retry_or_other_error(self):
        from asyncio import windows_events
        for number in (64, 5):
            with self.subTest(winerror=number):
                old, old_installed = windows_events.IocpProactor.accept, guard._INSTALLED
                loop = None
                try:
                    with contextlib.redirect_stdout(io.StringIO()):
                        guard.install()
                    loop = asyncio.ProactorEventLoop()
                    proactor = loop._proactor
                    contexts, clients, injected = [], [], []
                    loop.set_exception_handler(lambda _, context: contexts.append(context))
                    register, get_socket = proactor._register, proactor._get_accept_socket
                    def track(family):
                        conn = get_socket(family)
                        clients.append(conn)
                        return conn
                    proactor._get_accept_socket = track
                    def instrument(ov, obj, callback):
                        if callback.__name__ == 'finish_accept':
                            def callback(transferred, key, completed):
                                completed.getresult()
                                injected.append(True)
                                raise winerror(number)
                        return register(ov, obj, callback)
                    proactor._register = instrument
                    async def scenario():
                        server = await loop.create_server(asyncio.Protocol, '127.0.0.1', 0)
                        writer = None
                        try:
                            reader, writer = await asyncio.open_connection('127.0.0.1', server.sockets[0].getsockname()[1])
                            with contextlib.suppress(ConnectionResetError):
                                await asyncio.wait_for(reader.read(), 3)
                            self.assertEqual(injected, [True])
                            await asyncio.sleep(0)
                            if number == 64:
                                self.assertTrue(server.is_serving())
                                self.assertEqual(contexts, [])
                            else:
                                self.assertEqual(len(contexts), 1)
                                self.assertEqual(contexts[0]['exception'].winerror, 5)
                                self.assertEqual(server.sockets[0].fileno(), -1)
                        finally:
                            if writer is not None:
                                writer.close()
                                with contextlib.suppress(ConnectionError):
                                    await writer.wait_closed()
                            server.close()
                            await server.wait_closed()
                            await asyncio.sleep(0)
                            await asyncio.sleep(0)
                    # Cancellation must interrupt this delay; do not wait for it.
                    with patch.object(guard, 'RETRY_DELAY', 60), patch.object(guard._logger, 'warning'):
                        loop.run_until_complete(asyncio.wait_for(scenario(), 5))
                    self.assertEqual(len(clients), 1)
                    self.assertEqual(clients[0].fileno(), -1)
                    self.assertFalse(asyncio.all_tasks(loop))
                    loop.close()
                    self.assertEqual(proactor._cache, {})
                    self.assertEqual(len(contexts), 0 if number == 64 else 1)
                finally:
                    if loop is not None and not loop.is_closed():
                        loop.close()
                    windows_events.IocpProactor.accept = old
                    guard._INSTALLED = old_installed


if __name__ == '__main__':
    if '--require-windows' in sys.argv:
        sys.argv.remove('--require-windows')
        if sys.platform != 'win32' or sys.version_info[:2] != (3, 11):
            raise SystemExit('Windows CPython 3.11 is required; SKIP is not a pass.')
    unittest.main()
