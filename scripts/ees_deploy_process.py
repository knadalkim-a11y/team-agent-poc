"""Own one foreground-console WebUI process; never kill an unrelated process.

Only the recorded executable + creation time authorize a graceful signal.
Windows signals use an isolated helper so another PowerShell can stop the group.
Logs stay on this PC. Linux support exists for offline lifecycle tests.
"""

import ipaddress
import json
import math
import os
from pathlib import Path
import re
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

    def __init__(self, message, *, cause=None, operation=None, reason=None,
                 elapsed_seconds=None, timeout_seconds=None, exit_code=None, log_id=None):
        super().__init__(message)
        self.errno = getattr(cause, 'errno', None)
        self.winerror = getattr(cause, 'winerror', None)
        if type(self.errno) is not int:
            self.errno = None
        if type(self.winerror) is not int:
            self.winerror = None
        self.operation = operation if type(operation) is str and operation in {'port_probe', 'port_bind'} else None
        reasons = {'health_timeout', 'process_exited', 'identity_unavailable',
                   'identity_changed', 'launch_failed', 'launch_unverified'}
        self.reason = reason if type(reason) is str and reason in reasons else None
        self.elapsed_seconds = _duration(elapsed_seconds)
        self.timeout_seconds = _duration(timeout_seconds)
        self.exit_code = exit_code if type(exit_code) is int else None
        self.log_id = (log_id if type(log_id) is str
                       and re.fullmatch(r'server-[0-9a-f]{32}\.log', log_id) else None)


def _duration(value):
    if type(value) is int and value >= 0:
        return value
    if type(value) is float and math.isfinite(value) and value >= 0:
        return value
    return None


class LaunchUncertain(ProcessError):
    """A child was spawned but its identity is unverified; do not start a fallback."""


SERVER_CODE = (
    "import signal,sys; "
    "signal.signal(signal.SIGBREAK, signal.default_int_handler) if sys.platform == 'win32' else None; "
    "from open_webui import serve; serve(host=sys.argv[1], port=int(sys.argv[2]))"
)
# This entry point runs only for a selected wrapper program. Keep its import
# checks before Open WebUI: importing upstream can create or move runtime data.
CUSTOMIZED_SERVER_CODE = r'''
import importlib.metadata as metadata
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys

def reject():
    raise SystemExit("Selected program or existing runtime settings could not be verified; no fallback was started.")

try:
    root = Path(sys.argv[3])
    version, info_name, frontend_name = sys.argv[4:7]
    frontends = {'0.11.3+ees.1': '_ees1', '0.11.3+ees.2': '_ees2'}
    if (version not in frontends or info_name != f'open_webui-{version}.dist-info'
            or frontend_name != frontends[version]):
        reject()
    if not root.is_absolute() or not root.is_dir() or root.is_symlink():
        reject()
    root = root.resolve()
    package = root / 'open_webui'
    metadata_dir = root / info_name
    code = package / '__init__.py'
    required = (code, metadata_dir / 'METADATA', package / 'frontend' / 'index.html',
                package / 'frontend' / frontend_name / 'version.json')
    if (package.is_symlink() or metadata_dir.is_symlink()
            or any(not item.is_file() or item.is_symlink() for item in required)):
        reject()
    cwd = Path.cwd()
    if any(item.exists() or item.is_symlink() for item in
           (cwd / '.env', package / '.env', root / '.env', root.parent / '.env')):
        reject()
    data = Path(os.environ.get('DATA_DIR', ''))
    if (not data.is_absolute() or not data.is_dir()
            or not (data / 'webui.db').is_file() or (data / 'webui.db').stat().st_size == 0):
        reject()
    key = os.environ.get('WEBUI_SECRET_KEY')
    if key is not None:
        if not key.strip():
            reject()
    else:
        key_file = cwd / '.webui_secret_key'
        if not key_file.is_file() or key_file.is_symlink() or not key_file.read_bytes().strip():
            reject()
    if any(os.environ.get(name, '1') != '1' for name in ('UVICORN_WORKERS', 'WEB_CONCURRENCY')):
        reject()
    if any(os.environ.get(name, '').lower() not in ('', '0', 'false')
           for name in ('UVICORN_RELOAD', 'WEBUI_RELOAD')):
        reject()
    sys.path.insert(0, str(root))
    spec = importlib.util.find_spec('open_webui')
    if spec is None or spec.origin is None or Path(spec.origin).resolve() != code:
        reject()
    distribution = metadata.distribution('open-webui')
    if (distribution.metadata.get('Name') != 'open-webui' or distribution.version != version
            or Path(distribution.locate_file('')).resolve() != root
            or distribution.read_text('METADATA') != (metadata_dir / 'METADATA').read_text(encoding='utf-8')
            or json.loads(required[-1].read_text(encoding='utf-8')).get('version') != version):
        reject()
except (OSError, ValueError, TypeError, AttributeError, ImportError, IndexError):
    reject()

signal.signal(signal.SIGBREAK, signal.default_int_handler) if sys.platform == 'win32' else None
import open_webui
if Path(open_webui.__file__).resolve() != code:
    reject()
open_webui.serve(host=sys.argv[1], port=int(sys.argv[2]))
'''
_CHILDREN = {}


def _address(host, port):
    try:
        address = ipaddress.ip_address(host)
        if '%' in host or type(port) is not int or not 1 <= port <= 65535:
            raise ValueError
        return address
    except (TypeError, ValueError):
        raise ProcessError("Use an explicit listen IP and a port from 1 to 65535.") from None


def port_is_free(host, port, *, raise_on_error=False):
    """Probe binding with asyncio's platform defaults, without stopping a listener."""
    address = _address(host, port)
    operation = 'port_probe'
    try:
        with socket.socket(socket.AF_INET6 if address.version == 6 else socket.AF_INET) as listener:
            if os.name != 'nt':
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            operation = 'port_bind'
            listener.bind((host, port))
            operation = 'port_probe'
    except OSError as error:
        if raise_on_error:
            raise ProcessError("The listen port is unavailable; no existing process was stopped.",
                               cause=error, operation=operation) from None
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


def start_server(python_exe, cwd, env, host, port, log_dir, *, program_path=None, program_version=None):
    started = time.monotonic()
    if not port_is_free(host, port, raise_on_error=True):
        raise ProcessError("The listen port is unavailable; no existing process was stopped.")
    # Preserve a venv's executable path; resolving its symlink can select the base environment.
    python_exe, cwd = Path(python_exe).absolute(), Path(cwd).resolve()
    if not python_exe.is_file() or not cwd.is_dir():
        raise ProcessError("The existing Python executable and working directory are required.")
    command = [str(python_exe), '-c', SERVER_CODE, host, str(port)]
    if program_path is not None:
        if (type(program_path) is not str or not Path(program_path).is_absolute()
                or not Path(program_path).is_dir() or Path(program_path).is_symlink()):
            raise ProcessError("The selected program requires an existing absolute directory; no fallback was started.")
        # Original launch and the standalone stop helper need no builder import.
        try:
            from . import build_ees_webui as branding
        except ImportError:
            import build_ees_webui as branding
        version = branding.VERSION if program_version is None else program_version
        if type(version) is not str or version not in branding.PROGRAM_FRONTENDS:
            raise ProcessError("The selected program version is unsupported; no fallback was started.")
        command = [str(python_exe), '-I', '-B', '-c', CUSTOMIZED_SERVER_CODE, host, str(port),
                   str(Path(program_path).resolve()), version, f'open_webui-{version}.dist-info',
                   branding.PROGRAM_FRONTENDS[version]]
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = (log_dir / ('server-' + uuid.uuid4().hex + '.log')).resolve()
    options = ({'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt'
               else {'start_new_session': True})
    try:
        with log_file.open('xb') as log:
            child = subprocess.Popen(command,
                                     cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                     stdout=log, stderr=subprocess.STDOUT, **options)
    except OSError as error:
        raise ProcessError("Server launch failed; inspect the local server log.", cause=error,
                           reason='launch_failed', elapsed_seconds=time.monotonic() - started,
                           log_id=log_file.name) from None
    _CHILDREN[child.pid] = child
    try:
        identity = _identity(child.pid)
    except Exception:
        identity = None
    if identity is None:
        try:
            exit_code = child.poll()
            exited = type(exit_code) is int
        except Exception:
            exit_code = None
            exited = False
        if not exited:
            raise LaunchUncertain("A server was launched but its identity could not be verified. "
                                  "It may still be running; automatic recovery must not start another server.",
                                  reason='launch_unverified', elapsed_seconds=time.monotonic() - started,
                                  log_id=log_file.name) from None
        raise ProcessError("Server exited during startup; inspect the local server log.",
                           reason='process_exited', elapsed_seconds=time.monotonic() - started,
                           exit_code=exit_code, log_id=log_file.name)
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
    started = time.monotonic()
    deadline = started + timeout
    log_file = identity.get('log_file') if isinstance(identity, dict) else None
    log_id = Path(log_file).name if type(log_file) is str else None

    def failure(message, reason, *, cause=None, exit_code=None):
        return ProcessError(message, cause=cause, reason=reason,
                            elapsed_seconds=time.monotonic() - started, timeout_seconds=timeout,
                            exit_code=exit_code, log_id=log_id)

    def check_identity():
        # _identity's existing poll may remove a finished child from _CHILDREN.
        # Keep its Popen reference to use that poll's exit evidence, without polling again.
        pid = identity.get('pid') if isinstance(identity, dict) else None
        child = _CHILDREN.get(pid) if type(pid) is int else None
        try:
            verified = verify_identity(identity)
        except Exception as error:
            raise failure("Server identity could not be inspected while waiting for health.",
                          'identity_unavailable', cause=error) from None
        if verified:
            return
        exit_code = getattr(child, 'returncode', None)
        if type(exit_code) is int:
            raise failure("Server exited before becoming healthy; inspect the local server log.",
                          'process_exited', exit_code=exit_code)
        raise failure("Server identity changed or is unavailable; inspect the local server log.",
                      'identity_changed')

    while time.monotonic() < deadline:
        check_identity()
        if _healthy(identity['host'], identity['port'], min(2, max(0.01, deadline - time.monotonic()))):
            check_identity()
            return
        time.sleep(min(interval, max(0, deadline - time.monotonic())))
    raise failure("Server health timed out; inspect the local server log.", 'health_timeout')


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
