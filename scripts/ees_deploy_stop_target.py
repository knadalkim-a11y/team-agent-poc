"""Resolve one Windows EES server, including CPython's waiting venv launcher.

This is an explicit recovery helper, never a process-tree terminator. Windows
CPython 3.11's venv launcher forwards its command line to one base interpreter
and waits for that child. Only that narrow, verified shape is accepted here;
unknown children block recovery. No remote command line or secret is collected.
Launcher behavior: https://github.com/python/cpython/blob/3.11/PC/launcher.c
"""

import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ees_deploy_process as processes


def _failure(message, reason='identity_changed', cause=None):
    return processes.ProcessError(message, operation='process_inspect', reason=reason, cause=cause)


def _windows_processes():
    """Read PID/parent PID only through the documented Tool Help API."""
    import ctypes
    from ctypes import wintypes

    class Entry(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
                    ('th32ProcessID', wintypes.DWORD), ('th32DefaultHeapID', ctypes.c_size_t),
                    ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
                    ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', wintypes.LONG),
                    ('dwFlags', wintypes.DWORD), ('szExeFile', wintypes.WCHAR * 260)]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.Process32FirstW.restype = wintypes.BOOL
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.Process32NextW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL

    def failed():
        cause = OSError()
        cause.winerror = ctypes.get_last_error()
        return _failure('Process relationships could not be inspected; no process was terminated.',
                        'identity_unavailable', cause)

    handle = kernel.CreateToolhelp32Snapshot(0x00000002, 0)  # TH32CS_SNAPPROCESS
    if handle in (None, 0, ctypes.c_void_p(-1).value):
        raise failed()
    try:
        entry = Entry()
        entry.dwSize = ctypes.sizeof(Entry)
        if not kernel.Process32FirstW(handle, ctypes.byref(entry)):
            raise failed()
        result = {}
        while True:
            pid = int(entry.th32ProcessID)
            if pid in result:
                raise _failure('Process relationships changed; no process was terminated.')
            result[pid] = int(entry.th32ParentProcessID)
            if not kernel.Process32NextW(handle, ctypes.byref(entry)):
                if ctypes.get_last_error() != 18:  # ERROR_NO_MORE_FILES
                    raise failed()
                return result
    finally:
        kernel.CloseHandle(handle)


def _direct_children(snapshot, pid):
    return {child for child, parent in snapshot.items() if parent == pid and child != pid}


def _path(value):
    return os.path.normcase(os.path.realpath(value))


def _base_python(source_python):
    """Probe the registered interpreter without Open WebUI or site imports."""
    command = (
        'import json,sys;print(json.dumps({'
        '"implementation":sys.implementation.name,"version":list(sys.version_info[:2]),'
        '"executable":sys.executable,"base":getattr(sys,"_base_executable",None)}))'
    )
    try:
        result = subprocess.run([str(source_python), '-I', '-S', '-c', command],
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=10, check=True)
        info = json.loads(result.stdout)
        if (not isinstance(info, dict) or info.get('implementation') != 'cpython'
                or info.get('version') != [3, 11]
                or not isinstance(info.get('executable'), str)
                or _path(info['executable']) != _path(source_python)
                or not isinstance(info.get('base'), str)
                or not Path(info['base']).is_absolute() or not Path(info['base']).is_file()
                or _path(info['base']) == _path(source_python)):
            raise ValueError
        return _path(info['base'])
    except (OSError, ValueError, TypeError, subprocess.SubprocessError):
        raise _failure('The Python launcher could not be verified; no process was terminated.',
                       'identity_unavailable') from None


def _check_identity(identity, *, allow_exited=False):
    actual = processes._identity(identity['pid'])
    if actual is None and allow_exited:
        return False
    if not processes._same(actual, identity):
        raise _failure('Process identity changed; recovery stopped.')
    return True


def resolve_server_target(identity, source_python):
    """Return target/parent identities; an exited registry returns target=None.

    The caller holds the operation lock and validates the saved deployment. A
    live process with no children is its own target. A verified venv launcher
    with exactly one leaf base-interpreter child targets only that child.
    """
    if os.name != 'nt':
        raise _failure('Explicit server recovery is supported only on Windows.')
    pid = identity.get('pid') if isinstance(identity, dict) else None
    if (type(pid) is not int or not 1 <= pid <= 0xFFFFFFFF
            or identity.get('group_id') != pid
            or not isinstance(identity.get('executable'), str)
            or not isinstance(identity.get('created_at'), str)
            or not identity['created_at'].isdigit()
            or not isinstance(source_python, (str, Path))
            or not Path(source_python).is_absolute()
            or _path(source_python) != identity['executable']):
        raise _failure('The registered interpreter does not match the saved process.')
    snapshot = _windows_processes()
    children = _direct_children(snapshot, pid)
    if not _check_identity(identity, allow_exited=True):
        if children:
            raise _failure('A child remains after the registered process exited; recovery stopped.')
        return {'target': None, 'parent': None}
    if pid not in snapshot:
        raise _failure('Process relationships changed; no process was terminated.')
    parent = None
    target = identity
    if children:
        if len(children) != 1:
            raise _failure('The managed server has unexpected children; no process was terminated.')
        child_pid = next(iter(children))
        if _direct_children(snapshot, child_pid):
            raise _failure('The managed server has unexpected descendants; no process was terminated.')
        base_python = _base_python(source_python)
        child = processes._identity(child_pid)
        if (child is None or child['executable'] != base_python
                or int(child['created_at']) < int(identity['created_at'])):
            raise _failure('The Python child does not match the registered launcher.')
        parent = identity
        target = {**child, 'group_id': pid}
    # Check again after the interpreter probe, immediately before handing the
    # selected immutable identity to the same-handle termination primitive.
    current = _windows_processes()
    if (pid not in current or _direct_children(current, pid) != children
            or (parent is not None and _direct_children(current, target['pid']))):
        raise _failure('Process relationships changed; no process was terminated.')
    _check_identity(identity)
    if parent is not None:
        _check_identity(target)
    return {'target': target, 'parent': parent}


def terminate_server_target(identity, source_python, timeout=10):
    """Terminate one resolved process and confirm any waiting launcher exits.

    There is no fallback kill, tree signal, or second termination. Unknown
    identities, lingering descendants, or a launcher that does not exit prevent
    the caller from replacing program files or starting another server.
    """
    if (type(timeout) not in (int, float) or not math.isfinite(timeout)
            or not 0 < timeout <= 60):
        raise _failure('Use a recovery timeout greater than zero and no more than 60 seconds.')
    selected = resolve_server_target(identity, source_python)
    target, parent = selected['target'], selected['parent']
    if target is None:
        return False
    changed = processes.terminate_registered_process(
        target, timeout=timeout,
        expected_group_id=parent['pid'] if parent is not None else None)
    try:
        deadline = time.monotonic() + timeout
        while parent is not None and _check_identity(parent, allow_exited=True):
            if time.monotonic() >= deadline:
                raise processes.ProcessError('The Python launcher did not exit; recovery stopped.',
                                             operation='process_wait', reason='termination_timeout',
                                             timeout_seconds=timeout)
            time.sleep(min(0.05, max(0, deadline - time.monotonic())))
        if _check_identity(target, allow_exited=True):
            raise _failure('The selected process is still running; recovery stopped.')
        final = _windows_processes()
        if (_direct_children(final, identity['pid'])
                or _direct_children(final, target['pid'])):
            raise _failure('A child remains after recovery; program replacement stopped.')
    except (processes.ProcessError, OSError) as error:
        # Preserve the completed termination even when the safe-to-restart
        # confirmation fails. The caller must not report that nothing changed.
        error.terminated = changed
        raise
    return changed
