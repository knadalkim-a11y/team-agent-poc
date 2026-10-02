"""One-server recovery boundary tests; real termination uses disposable Windows Python."""

import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts import ees_deploy_stop_target as target


class TargetTests(unittest.TestCase):
    def setUp(self):
        self.source = str(Path('/synthetic/venv/python.exe').absolute())
        self.base = str(Path('/synthetic/base/python.exe').absolute())
        self.parent = {'pid': 100, 'group_id': 100, 'executable': target._path(self.source),
                       'created_at': '1000'}
        self.child = {'pid': 101, 'executable': target._path(self.base), 'created_at': '1001'}
        self.identities = {100: self.parent, 101: self.child}
        self.patchers = [
            patch.object(target, 'os', SimpleNamespace(name='nt', path=os.path)),
            patch.object(target, '_windows_processes', return_value={100: 99, 101: 100}),
            patch.object(target, '_base_python', return_value=target._path(self.base)),
            patch.object(target.processes, '_identity', side_effect=lambda pid: self.identities.get(pid)),
            patch.object(target.processes, 'terminate_registered_process', return_value=True),
        ]
        self.windows, self.snapshot, self.base_probe, self.inspect, self.terminate = [p.start() for p in self.patchers]
        self.addCleanup(lambda: [p.stop() for p in reversed(self.patchers)])

    def test_leaf_registered_process_is_its_own_target(self):
        self.snapshot.return_value = {100: 99}
        result = target.resolve_server_target(self.parent, self.source)
        self.assertEqual(result, {'target': self.parent, 'parent': None})
        self.base_probe.assert_not_called()
        self.terminate.assert_not_called()

    def test_venv_redirector_selects_only_its_leaf_base_child(self):
        result = target.resolve_server_target(self.parent, self.source)
        self.assertEqual(result, {'target': {**self.child, 'group_id': 100}, 'parent': self.parent})
        self.base_probe.assert_called_once_with(self.source)

    def test_wrong_parent_identity_or_runtime_cannot_select_any_process(self):
        cases = [({**self.parent, 'created_at': '1009'}, self.source),
                 ({**self.parent, 'group_id': 5}, self.source),
                 (self.parent, self.base)]
        for identity, python in cases:
            with self.subTest(identity=identity), self.assertRaises(target.processes.ProcessError):
                target.resolve_server_target(identity, python)
        self.terminate.assert_not_called()

    def test_multiple_children_or_deeper_tree_blocks_recovery(self):
        for snapshot in ({100: 99, 101: 100, 102: 100}, {100: 99, 101: 100, 102: 101}):
            self.snapshot.return_value = snapshot
            with self.subTest(snapshot=snapshot), self.assertRaises(target.processes.ProcessError):
                target.resolve_server_target(self.parent, self.source)
        self.terminate.assert_not_called()

    def test_child_executable_age_or_disappearance_cannot_authorize_termination(self):
        for child in ({**self.child, 'executable': 'unrelated'},
                      {**self.child, 'created_at': '999'}, None):
            self.identities[101] = child
            with self.subTest(child=child), self.assertRaises(target.processes.ProcessError):
                target.resolve_server_target(self.parent, self.source)
        self.terminate.assert_not_called()

    def test_child_topology_or_identity_changes_during_probe_block_termination(self):
        self.snapshot.side_effect = [{100: 99, 101: 100}, {100: 99, 101: 100, 102: 101}]
        with self.assertRaises(target.processes.ProcessError):
            target.resolve_server_target(self.parent, self.source)
        self.snapshot.side_effect = None
        self.inspect.side_effect = [self.parent, self.child, self.parent,
                                    {**self.child, 'created_at': '9999'}]
        with self.assertRaises(target.processes.ProcessError):
            target.resolve_server_target(self.parent, self.source)
        self.terminate.assert_not_called()

    def test_exited_parent_with_orphan_child_blocks_recovery(self):
        self.identities.pop(100)
        self.snapshot.return_value = {101: 100}
        with self.assertRaises(target.processes.ProcessError):
            target.terminate_server_target(self.parent, self.source)
        self.terminate.assert_not_called()

    def test_exited_parent_without_children_is_noop(self):
        self.identities.clear()
        self.snapshot.return_value = {200: 199}
        self.assertFalse(target.terminate_server_target(self.parent, self.source))
        self.terminate.assert_not_called()

    def test_child_is_only_termination_call_and_parent_exits_naturally(self):
        def terminated(*args, **kwargs):
            self.identities.clear()
            self.snapshot.return_value = {}
            return True
        self.terminate.side_effect = terminated
        self.assertTrue(target.terminate_server_target(self.parent, self.source, timeout=2))
        self.terminate.assert_called_once_with({**self.child, 'group_id': 100}, timeout=2,
                                               expected_group_id=100)

    def test_lingering_parent_blocks_replacement_without_second_kill(self):
        def terminated(*args, **kwargs):
            self.identities.pop(101)
            return True
        self.terminate.side_effect = terminated
        with self.assertRaises(target.processes.ProcessError) as failure:
            target.terminate_server_target(self.parent, self.source, timeout=.01)
        self.assertEqual(failure.exception.reason, 'termination_timeout')
        self.assertTrue(failure.exception.terminated)
        self.terminate.assert_called_once()

    def test_descendant_created_during_termination_blocks_replacement(self):
        def terminated(*args, **kwargs):
            self.identities.clear()
            self.snapshot.return_value = {102: 101}
            return True
        self.terminate.side_effect = terminated
        with self.assertRaises(target.processes.ProcessError) as failure:
            target.terminate_server_target(self.parent, self.source)
        self.assertTrue(failure.exception.terminated)
        self.terminate.assert_called_once()


class ProbeTests(unittest.TestCase):
    def test_isolated_probe_accepts_only_cpython_311_and_matching_distinct_base(self):
        source = str(Path(sys.executable).absolute())
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary) / 'base.exe'
            base.write_bytes(b'synthetic')
            good = {'implementation': 'cpython', 'version': [3, 11],
                    'executable': source, 'base': str(base)}
            cases = [(good, True), ({**good, 'implementation': 'pypy'}, False),
                     ({**good, 'version': [3, 12]}, False),
                     ({**good, 'executable': str(base)}, False),
                     ({**good, 'base': source}, False),
                     ({**good, 'base': None}, False)]
            for info, accepted in cases:
                with self.subTest(info=info), patch.object(target.subprocess, 'run',
                        return_value=SimpleNamespace(stdout=json.dumps(info).encode())) as run:
                    if accepted:
                        self.assertEqual(target._base_python(source), target._path(base))
                    else:
                        with self.assertRaises(target.processes.ProcessError):
                            target._base_python(source)
                    self.assertEqual(run.call_args.args[0][1:4], ['-I', '-S', '-c'])

    def test_probe_failure_does_not_echo_private_subprocess_output(self):
        for failure in (subprocess.TimeoutExpired('synthetic-private', 10),
                        subprocess.CalledProcessError(1, 'synthetic-private', stderr=b'secret')):
            with self.subTest(failure=failure), patch.object(target.subprocess, 'run', side_effect=failure):
                with self.assertRaises(target.processes.ProcessError) as raised:
                    target._base_python(sys.executable)
                self.assertNotIn('synthetic-private', str(raised.exception))
                self.assertNotIn('secret', str(raised.exception))


class ToolHelpTests(unittest.TestCase):
    def test_snapshot_reads_parent_relationships_and_closes_handle(self):
        kernel = Mock()
        kernel.CreateToolhelp32Snapshot.return_value = 99
        rows = iter([(10, 1), (11, 10), (12, 1)])
        def advance(handle, pointer):
            try:
                pid, parent = next(rows)
            except StopIteration:
                return False
            pointer._obj.th32ProcessID = pid
            pointer._obj.th32ParentProcessID = parent
            return True
        kernel.Process32FirstW.side_effect = advance
        kernel.Process32NextW.side_effect = advance
        with patch.object(ctypes, 'WinDLL', return_value=kernel, create=True), \
                patch.object(ctypes, 'get_last_error', return_value=18, create=True):
            self.assertEqual(target._windows_processes(), {10: 1, 11: 10, 12: 1})
        kernel.CloseHandle.assert_called_once_with(99)

    def test_partial_snapshot_is_rejected_and_error_contains_no_process_details(self):
        kernel = Mock()
        kernel.CreateToolhelp32Snapshot.return_value = 99
        kernel.Process32FirstW.return_value = True
        kernel.Process32NextW.return_value = False
        with patch.object(ctypes, 'WinDLL', return_value=kernel, create=True), \
                patch.object(ctypes, 'get_last_error', return_value=5, create=True):
            with self.assertRaises(target.processes.ProcessError) as failure:
                target._windows_processes()
        self.assertEqual(failure.exception.winerror, 5)
        kernel.CloseHandle.assert_called_once_with(99)


@unittest.skipUnless(os.name == 'nt' and sys.version_info[:2] == (3, 11),
                     'Disposable CPython 3.11 Windows venv fixture')
class WindowsVenvTests(unittest.TestCase):
    def test_actual_venv_child_termination_releases_waiting_launcher(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            environment = root / 'venv'
            subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(environment)],
                           check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            python = environment / 'Scripts' / 'python.exe'
            marker = root / 'runtime.json'
            code = ('import json,os,sys,time;from pathlib import Path;'
                    'Path(sys.argv[1]+".tmp").write_text(json.dumps({"pid":os.getpid()}),encoding="utf-8");'
                    'os.replace(sys.argv[1]+".tmp",sys.argv[1]);time.sleep(30)')
            child = subprocess.Popen([str(python), '-I', '-S', '-c', code, str(marker)],
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL,
                                     creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            server = None
            try:
                deadline = time.monotonic() + 10
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(.05)
                self.assertTrue(marker.exists())
                actual_pid = json.loads(marker.read_text(encoding='utf-8'))['pid']
                self.assertNotEqual(actual_pid, child.pid)
                parent = target.processes._identity(child.pid)
                parent['group_id'] = child.pid
                server = target.processes._identity(actual_pid)
                selected = target.resolve_server_target(parent, str(python))
                self.assertEqual(selected['target']['pid'], actual_pid)
                self.assertEqual(selected['parent']['pid'], child.pid)
                with patch.object(target.processes, 'terminate_registered_process',
                                  wraps=target.processes.terminate_registered_process) as terminate:
                    self.assertTrue(target.terminate_server_target(parent, str(python), timeout=5))
                self.assertEqual(terminate.call_count, 1)
                self.assertEqual(terminate.call_args.args[0]['pid'], actual_pid)
                child.wait(timeout=5)
                self.assertIsNone(target.processes._identity(actual_pid))
            finally:
                # Only disposable test-owned processes; never a process tree.
                if server is not None and target.processes._same(
                        target.processes._identity(server['pid']), server):
                    target.processes.terminate_registered_process({**server, 'group_id': server['pid']})
                if child.poll() is None:
                    child.terminate()
                    child.wait(timeout=5)


if __name__ == '__main__':
    unittest.main()
