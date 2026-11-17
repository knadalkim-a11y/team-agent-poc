"""TEMPORARY investigation probe; delete before any merge.

Windows only. Reproduces the intermittent failure of
test_another_process_can_stop_saved_identity and measures what the process
handle reports while the stopped server is exiting.

Phase A repeats the test's own scenario: another Python process stops the
saved identity through the product's stop_server().
Phase B samples the same Windows calls the product uses, as fast as possible,
from before the stop signal until the process is gone.
Phase C calls the product's _identity() the same way and counts what it raises.
"""
import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import tests.test_ees_deploy_process as lifecycle  # noqa: E402

manager = lifecycle.manager
MODULE = lifecycle.MODULE
FAKE_SERVER = lifecycle.FAKE_SERVER

STOP_CODE = ('import importlib.util,json,sys; '
             's=importlib.util.spec_from_file_location("m",sys.argv[1]); '
             'm=importlib.util.module_from_spec(s);s.loader.exec_module(m)\n'
             'try:\n'
             ' m.stop_server(json.loads(sys.argv[2]),timeout=3)\n'
             'except m.ProcessError as error:\n'
             ' fields=("operation","reason","errno","winerror","elapsed_seconds","timeout_seconds","exit_code")\n'
             ' print("EVIDENCE "+json.dumps({key:getattr(error,key) for key in fields},sort_keys=True))\n'
             ' sys.exit(3)\n')


def kernel32():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.GetProcessTimes.restype = wintypes.BOOL
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    return kernel


def ensure_console(kernel):
    count = (ctypes.c_ulong * 1)()
    if kernel.GetConsoleProcessList(count, 1) == 0 and not kernel.AllocConsole():
        raise RuntimeError('A real console is required.')


class Server:
    """One synthetic server started exactly as the lifecycle tests start it."""

    def __init__(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            self.port = listener.getsockname()[1]
        with patch.object(manager, 'SERVER_CODE', FAKE_SERVER):
            self.identity = manager.start_server(sys.executable, self.root, dict(os.environ),
                                                 '127.0.0.1', self.port, self.root / 'logs')
        manager.wait_healthy(self.identity, timeout=10)

    def close(self):
        child = manager._CHILDREN.pop(self.identity['pid'], None)
        if child is not None:
            try:
                child.wait(timeout=20)
            except subprocess.TimeoutExpired:
                pass
        try:
            self.directory.cleanup()
        except OSError:
            pass


def phase_a(rounds):
    failures, seconds = [], []
    for index in range(rounds):
        server = Server()
        try:
            started = time.perf_counter()
            completed = subprocess.run([sys.executable, '-c', STOP_CODE, str(MODULE), json.dumps(server.identity)],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            seconds.append(time.perf_counter() - started)
            if completed.returncode:
                text = completed.stdout.decode(errors='replace')
                evidence = next((json.loads(line[9:]) for line in text.splitlines() if line.startswith('EVIDENCE ')), None)
                failures.append({'round': index, 'returncode': completed.returncode, 'evidence': evidence})
        finally:
            server.close()
    return {'rounds': rounds, 'failed': len(failures), 'failures': failures[:20],
            'stop_seconds_median': sorted(seconds)[len(seconds) // 2] if seconds else None}


def sample(kernel, pid):
    """The product's own sequence on one fresh handle, with every result kept."""
    ctypes.set_last_error(0)
    handle = kernel.OpenProcess(0x1000 | 0x100000, False, pid)
    if not handle:
        return {'open': False, 'open_error': ctypes.get_last_error()}
    try:
        record = {'open': True, 'wait_before': kernel.WaitForSingleObject(handle, 0)}
        times = [wintypes.FILETIME() for _ in range(4)]
        ctypes.set_last_error(0)
        record['times_ok'] = bool(kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in times)))
        record['times_error'] = ctypes.get_last_error()
        image, length = ctypes.create_unicode_buffer(32768), wintypes.DWORD(32768)
        ctypes.set_last_error(0)
        record['image_ok'] = bool(kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(length)))
        record['image_error'] = ctypes.get_last_error()
        code = wintypes.DWORD()
        record['exit_code'] = code.value if kernel.GetExitCodeProcess(handle, ctypes.byref(code)) else None
        record['wait_after'] = kernel.WaitForSingleObject(handle, 0)
        if record['wait_before'] != 0 and not (record['times_ok'] and record['image_ok']) and record['wait_after'] != 0:
            # The exact state in which the product raises identity_unavailable.
            started = time.perf_counter()
            record['settle_wait'] = kernel.WaitForSingleObject(handle, 10000)
            record['settle_ms'] = round((time.perf_counter() - started) * 1000, 3)
        return record
    finally:
        kernel.CloseHandle(handle)


def phase_b(kernel, rounds):
    denied_rounds, settle, errors, samples_total, examples, helper_errors = 0, [], {}, 0, [], []
    for index in range(rounds):
        server = Server()
        pid = server.identity['pid']
        anomalies, stop, count = [], threading.Event(), [0]

        def watch():
            while not stop.is_set():
                record = sample(kernel, pid)
                count[0] += 1
                if not record['open']:
                    if record['open_error'] != 87:  # 87: the PID no longer exists.
                        anomalies.append(record)
                    return
                if record['wait_before'] == 0:
                    return
                if 'settle_ms' in record:
                    anomalies.append(record)
                    return

        thread = threading.Thread(target=watch)
        thread.start()
        try:
            try:
                manager._request_windows_stop(server.identity)
            except manager.ProcessError as error:
                helper_errors.append('%s/%s/winerror=%s' % (error.operation, error.reason, error.winerror))
            thread.join(timeout=20)
        finally:
            stop.set()
            thread.join(timeout=5)
            server.close()
        samples_total += count[0]
        if anomalies:
            denied_rounds += 1
            record = anomalies[0]
            if not record['open']:
                key = 'open_error=%s' % record['open_error']
                errors[key] = errors.get(key, 0) + 1
                continue
            settle.append(record['settle_ms'])
            key = 'times=%s/%s image=%s/%s exit_code=%s settle_wait=%s' % (
                record['times_ok'], record['times_error'], record['image_ok'], record['image_error'],
                record['exit_code'], record['settle_wait'])
            errors[key] = errors.get(key, 0) + 1
            if len(examples) < 3:
                examples.append(record)
    settle.sort()
    return {'rounds': rounds, 'rounds_with_refused_query_before_exit': denied_rounds, 'samples': samples_total,
            'refusal_kinds': errors, 'examples': examples, 'helper_errors': helper_errors[:10],
            'settle_ms': {'min': settle[0], 'median': settle[len(settle) // 2], 'max': settle[-1]} if settle else None}


def phase_c(rounds):
    raised, kinds, calls = 0, {}, 0
    for index in range(rounds):
        server = Server()
        pid = server.identity['pid']
        child = manager._CHILDREN.pop(pid, None)  # Inspect as another process would, without the owned child.
        outcome, stop, count = [], threading.Event(), [0]

        def watch():
            while not stop.is_set():
                try:
                    count[0] += 1
                    if manager._identity(pid) is None:
                        return
                except manager.ProcessError as error:
                    outcome.append('%s/%s/winerror=%s' % (error.operation, error.reason, error.winerror))
                    return

        thread = threading.Thread(target=watch)
        thread.start()
        try:
            try:
                manager._request_windows_stop(server.identity)
            except manager.ProcessError as error:
                outcome.append('helper:%s/%s/winerror=%s' % (error.operation, error.reason, error.winerror))
            thread.join(timeout=20)
        finally:
            stop.set()
            thread.join(timeout=5)
            if child is not None:
                try:
                    child.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    pass
            try:
                server.directory.cleanup()
            except OSError:
                pass
        calls += count[0]
        if outcome:
            raised += 1
            kinds[outcome[0]] = kinds.get(outcome[0], 0) + 1
    return {'rounds': rounds, 'rounds_where_identity_raised': raised, 'calls': calls, 'kinds': kinds}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--a', type=int, default=150)
    parser.add_argument('--b', type=int, default=60)
    parser.add_argument('--c', type=int, default=60)
    args = parser.parse_args()
    if os.name != 'nt':
        print('Windows only.')
        return 0
    kernel = kernel32()
    ensure_console(kernel)
    result = {'python': sys.version.split()[0], 'windows': sys.getwindowsversion().build}
    if args.b:
        result['B_raw_windows_calls'] = phase_b(kernel, args.b)
        print('PROBE_B ' + json.dumps(result['B_raw_windows_calls'], sort_keys=True), flush=True)
    if args.c:
        result['C_product_identity'] = phase_c(args.c)
        print('PROBE_C ' + json.dumps(result['C_product_identity'], sort_keys=True), flush=True)
    if args.a:
        result['A_test_scenario'] = phase_a(args.a)
        print('PROBE_A ' + json.dumps(result['A_test_scenario'], sort_keys=True), flush=True)
    print('PROBE_DONE ' + json.dumps({'python': result['python'], 'windows': result['windows']}), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
