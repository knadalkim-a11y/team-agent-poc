"""Own one foreground-console WebUI process; never kill an unrelated process.

Only the recorded executable + creation time authorize a graceful signal.
Windows signals use an isolated helper so another PowerShell can stop the group.
Logs stay on this PC. Linux support exists for offline lifecycle tests.
"""

import ipaddress
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid


class ProcessError(RuntimeError):
    """Starting, identifying, or gracefully stopping the managed server failed."""


class LaunchUncertain(ProcessError):
    """A child was spawned but its identity is unverified; do not start a fallback."""


SERVER_CODE = (
    "import signal,sys; "
    "signal.signal(signal.SIGBREAK, signal.default_int_handler) if sys.platform == 'win32' else None; "
    "from open_webui import serve; serve(host=sys.argv[1], port=int(sys.argv[2]))"
)
_CHILDREN = {}


def _address(host, port):
    try:
        address = ipaddress.ip_address(host)
        if '%' in host or type(port) is not int or not 1 <= port <= 65535:
            raise ValueError
        return address
    except (TypeError, ValueError):
        raise ProcessError("Use an explicit listen IP and a port from 1 to 65535.") from None


def port_is_free(host, port):
    """Probe binding with asyncio's platform defaults, without stopping a listener."""
    address = _address(host, port)
    with socket.socket(socket.AF_INET6 if address.version == 6 else socket.AF_INET) as listener:
        if os.name != 'nt':
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind((host, port))
        except OSError:
            return False
    return True


def _same(actual, expected):
    return actual is not None and all(actual.get(key) == expected.get(key)
                                      for key in ('pid', 'executable', 'created_at'))


def _windows_identity(pid, send_to=None):
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.AttachConsole.argtypes = [wintypes.DWORD]
    kernel.GenerateConsoleCtrlEvent.argtypes = [wintypes.DWORD, wintypes.DWORD]
    handle = kernel.OpenProcess(0x1000 | 0x100000, False, pid)
    if not handle:
        if ctypes.get_last_error() == 87:  # No such process, not an access denial.
            return None
        raise ProcessError("Process identity could not be inspected; no signal was sent.")
    try:
        if kernel.WaitForSingleObject(handle, 0) == 0:
            return None
        times = [wintypes.FILETIME() for _ in range(4)]
        image, length = ctypes.create_unicode_buffer(32768), wintypes.DWORD(32768)
        if (not kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in times))
                or not kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(length))):
            raise ProcessError("Process identity could not be inspected; no signal was sent.")
        actual = {'pid': pid, 'executable': os.path.normcase(os.path.realpath(image.value)),
                  'created_at': str((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)}
        if send_to is not None:
            if not _same(actual, send_to) or send_to.get('group_id') != pid:
                raise ProcessError("Process identity changed; no signal was sent.")
            # Keep the process handle open across identity check and signal.
            # A separate helper detaches itself, never the user's PowerShell.
            kernel.FreeConsole()
            if not kernel.AttachConsole(pid):
                raise ProcessError("Cannot attach to the server console; stop it in its original window.")
            try:
                if not kernel.GenerateConsoleCtrlEvent(1, pid):  # CTRL_BREAK_EVENT, never broadcast.
                    raise ProcessError("The graceful stop signal could not be delivered.")
            finally:
                kernel.FreeConsole()
        return actual
    finally:
        kernel.CloseHandle(handle)


def _identity(pid):
    if type(pid) is not int or not 1 <= pid <= 0xFFFFFFFF:
        raise ProcessError("The saved process identity is invalid.")
    child = _CHILDREN.get(pid)
    if child is not None and child.poll() is not None:
        _CHILDREN.pop(pid, None)
        return None
    if os.name == 'nt':
        return _windows_identity(pid)
    if not sys.platform.startswith('linux'):
        raise ProcessError("This process manager supports Windows; Linux is for offline tests.")
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        if fields[0] in ('Z', 'X'):
            return None
        return {'pid': pid, 'executable': os.path.realpath(f'/proc/{pid}/exe'),
                'created_at': fields[19]}
    except FileNotFoundError:
        return None
    except OSError:
        raise ProcessError("Process identity could not be inspected; no signal was sent.") from None


def verify_identity(identity):
    return isinstance(identity, dict) and _same(_identity(identity.get('pid')), identity)


def start_server(python_exe, cwd, env, host, port, log_dir):
    if not port_is_free(host, port):
        raise ProcessError("The listen port is unavailable; no existing process was stopped.")
    # Preserve a venv's executable path; resolving its symlink can select the base environment.
    python_exe, cwd = Path(python_exe).absolute(), Path(cwd).resolve()
    if not python_exe.is_file() or not cwd.is_dir():
        raise ProcessError("The existing Python executable and working directory are required.")
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = (log_dir / ('server-' + uuid.uuid4().hex + '.log')).resolve()
    options = ({'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt'
               else {'start_new_session': True})
    try:
        with log_file.open('xb') as log:
            child = subprocess.Popen([str(python_exe), '-c', SERVER_CODE, host, str(port)],
                                     cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                     stdout=log, stderr=subprocess.STDOUT, **options)
    except OSError:
        raise ProcessError(f"Server launch failed; inspect the local log: {log_file}") from None
    _CHILDREN[child.pid] = child
    try:
        identity = _identity(child.pid)
    except Exception:
        identity = None
    if identity is None:
        try:
            exited = child.poll() is not None
        except Exception:
            exited = False
        if not exited:
            raise LaunchUncertain("A server was launched but its identity could not be verified. "
                                  "It may still be running; automatic recovery must not start another server.") from None
        raise ProcessError(f"Server exited during startup; inspect the local log: {log_file}")
    return {**identity, 'group_id': child.pid, 'host': host, 'port': port, 'log_file': str(log_file)}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        raise urllib.error.HTTPError(request.full_url, code, 'Redirect refused', headers, response)


def _healthy(host, port, timeout):
    address = _address(host, port)
    target = ('127.0.0.1' if address.version == 4 else '::1') if address.is_unspecified else host
    authority = f'[{target}]' if address.version == 6 else target
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(f'http://{authority}:{port}/health', timeout=timeout) as response:
            if response.status != 200:
                return False
            data = json.loads(response.read(4097))
            return isinstance(data, dict) and data.get('status') is True
    except urllib.error.HTTPError as error:
        error.close()
        return False
    except (OSError, ValueError):
        return False


def wait_healthy(identity, timeout=60, interval=0.2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not verify_identity(identity):
            raise ProcessError(f"Server exited before becoming healthy; inspect: {identity.get('log_file', '')}")
        if _healthy(identity['host'], identity['port'], min(2, max(0.01, deadline - time.monotonic()))):
            if verify_identity(identity):
                return
        time.sleep(min(interval, max(0, deadline - time.monotonic())))
    raise ProcessError(f"Server health timed out; inspect the local log: {identity.get('log_file', '')}")


def stop_server(identity, timeout=30):
    if not isinstance(identity, dict) or identity.get('group_id') != identity.get('pid'):
        raise ProcessError("The saved process group is invalid; no signal was sent.")
    actual = _identity(identity.get('pid'))
    if actual is None:
        return
    if not _same(actual, identity):
        raise ProcessError("Process identity changed; no signal was sent.")
    if os.name == 'nt':
        helper = subprocess.Popen([sys.executable, '-I', str(Path(__file__).resolve()), '--break', json.dumps(identity)],
                                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            if helper.wait(timeout=5) != 0:
                raise ProcessError("Graceful stop could not be delivered; use the original server console.")
        except subprocess.TimeoutExpired:
            raise ProcessError("The console helper did not finish; no force kill was attempted.") from None
    else:
        if os.getpgid(identity['pid']) != identity['group_id'] or not verify_identity(identity):
            raise ProcessError("Process group changed; no signal was sent.")
        os.killpg(identity['group_id'], signal.SIGINT)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _same(_identity(identity['pid']), identity):
            return
        time.sleep(min(0.1, max(0, deadline - time.monotonic())))
    raise ProcessError("Graceful stop timed out; the process was not force-killed.")


if __name__ == '__main__':
    try:
        if os.name != 'nt' or len(sys.argv) != 3 or sys.argv[1] != '--break':
            raise ProcessError("Internal console helper only.")
        saved = json.loads(sys.argv[2])
        _windows_identity(saved['pid'], send_to=saved)
    except (ProcessError, OSError, ValueError, KeyError, TypeError):
        sys.exit(1)
