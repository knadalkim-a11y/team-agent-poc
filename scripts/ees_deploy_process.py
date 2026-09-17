"""Own one foreground-console WebUI process; never kill an unrelated process.

Only the recorded executable + creation time authorize a graceful signal.
Explicit recovery can terminate that one Windows process through a verified handle.
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


_OPERATIONS = {'port_probe', 'port_bind', 'process_open', 'process_inspect',
               'process_terminate', 'process_wait', 'console_attach', 'console_signal', 'stop_helper'}
_REASONS = {'health_timeout', 'process_exited', 'identity_unavailable',
            'identity_changed', 'launch_failed', 'launch_unverified',
            'termination_failed', 'termination_timeout', 'stop_signal_failed',
            'stop_helper_failed', 'stop_helper_timeout', 'stop_timeout', 'accept_guard_incompatible'}


class ProcessError(RuntimeError):
    """Starting, identifying, or stopping the managed server failed."""

    def __init__(self, message, *, cause=None, operation=None, reason=None,
                 elapsed_seconds=None, timeout_seconds=None, exit_code=None, log_id=None,
                 terminated=None):
        super().__init__(message)
        self.errno = getattr(cause, 'errno', None)
        self.winerror = getattr(cause, 'winerror', None)
        if type(self.errno) is not int:
            self.errno = None
        if type(self.winerror) is not int:
            self.winerror = None
        self.operation = operation if type(operation) is str and operation in _OPERATIONS else None
        self.reason = reason if type(reason) is str and reason in _REASONS else None
        self.elapsed_seconds = _duration(elapsed_seconds)
        self.timeout_seconds = _duration(timeout_seconds)
        self.exit_code = exit_code if type(exit_code) is int else None
        self.log_id = (log_id if type(log_id) is str
                       and re.fullmatch(r'server-[0-9a-f]{32}\.log', log_id) else None)
        self.terminated = terminated if type(terminated) is bool else None


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
    frontends = {'0.11.3+ees.1': '_ees1', '0.11.3+ees.2': '_ees2', '0.11.3+ees.3': '_ees3', '0.11.3+ees.4': '_ees4', '0.11.3+ees.5': '_ees5', '0.11.3+ees.6': '_ees6', '0.11.3+ees.7': '_ees7', '0.11.3+ees.8': '_ees8', '0.11.3+ees.9': '_ees9', '0.11.3+ees.10': '_ees10'}
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

    def failure(message, operation, reason='identity_unavailable', *, windows_error=True):
        cause = None
        if windows_error:
            cause = OSError()
            cause.winerror = ctypes.get_last_error()
        return ProcessError(message, cause=cause, operation=operation, reason=reason)

    try:
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    except OSError as error:
        raise ProcessError("Process access could not be prepared; no signal was sent.",
                           cause=error, operation='process_open', reason='identity_unavailable') from None
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
    kernel.AttachConsole.argtypes = [wintypes.DWORD]
    kernel.AttachConsole.restype = wintypes.BOOL
    kernel.GenerateConsoleCtrlEvent.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.GenerateConsoleCtrlEvent.restype = wintypes.BOOL
    kernel.FreeConsole.argtypes = []
    kernel.FreeConsole.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x1000 | 0x100000, False, pid)
    if not handle:
        if ctypes.get_last_error() == 87:  # No such process, not an access denial.
            return None
        raise failure("Process identity could not be inspected; no signal was sent.", 'process_open')

    def exited():
        result = kernel.WaitForSingleObject(handle, 0)
        if result == 0xFFFFFFFF:
            raise failure("Process exit could not be inspected; no signal was sent.", 'process_wait')
        if result not in (0, 258):
            raise failure("Process exit status is unknown; no signal was sent.", 'process_wait',
                          windows_error=False)
        return result == 0

    try:
        if exited():
            return None
        times = [wintypes.FILETIME() for _ in range(4)]
        image, length = ctypes.create_unicode_buffer(32768), wintypes.DWORD(32768)
        if (not kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in times))
                or not kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(length))):
            error = failure("Process identity could not be inspected; no signal was sent.", 'process_inspect')
            # A process can finish between the wait and image query. Only the
            # same handle becoming signaled proves that this is an ordinary exit.
            if exited():
                return None
            raise error
        actual = {'pid': pid, 'executable': os.path.normcase(os.path.realpath(image.value)),
                  'created_at': str((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)}
        if send_to is not None:
            if not _same(actual, send_to) or send_to.get('group_id') != pid:
                raise ProcessError("Process identity changed; no signal was sent.",
                                   operation='process_inspect', reason='identity_changed')
            # Keep the process handle open across identity check and signal.
            # A separate helper detaches itself, never the user's PowerShell.
            kernel.FreeConsole()
            if not kernel.AttachConsole(pid):
                error = failure("Cannot attach to the server console; stop it in its original window.",
                                'console_attach', 'stop_signal_failed')
                if exited():
                    return None
                raise error
            try:
                if not kernel.GenerateConsoleCtrlEvent(1, pid):  # CTRL_BREAK_EVENT, never broadcast.
                    error = failure("The graceful stop signal could not be delivered.",
                                    'console_signal', 'stop_signal_failed')
                    if exited():
                        return None
                    raise error
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
        fields = Path(f'/proc/{pid}/stat').read_text(encoding='utf-8').rsplit(')', 1)[1].split()
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


def terminate_registered_process(identity, timeout=10, *, expected_group_id=None):
    """Explicit Windows recovery only; return whether this call terminated one process.

    The caller must obtain recovery authorization and hold its operation lock.
    PID, image, creation time, and the recorded group must all match. A verified
    redirector child requires the caller's independently checked launcher group.
    All queries,
    termination, and exit confirmation use the same handle so PID reuse cannot
    redirect the operation. This never signals a console, descendant, or group.
    """
    pid = identity.get('pid') if isinstance(identity, dict) else None
    group_id = pid if expected_group_id is None else expected_group_id
    if (type(pid) is not int or not 1 <= pid <= 0xFFFFFFFF
            or type(group_id) is not int or not 1 <= group_id <= 0xFFFFFFFF
            or type(identity.get('group_id')) is not int or identity['group_id'] != group_id
            or type(identity.get('executable')) is not str or not identity['executable']
            or not os.path.isabs(identity['executable'])
            or type(identity.get('created_at')) is not str
            or re.fullmatch(r'[1-9][0-9]*', identity['created_at']) is None):
        raise ProcessError("The saved process identity is invalid; no process was terminated.",
                           reason='identity_changed', terminated=False)
    if (type(timeout) not in (int, float) or not 0 < timeout <= 60
            or not math.isfinite(timeout)):
        raise ProcessError("Use a termination timeout greater than zero and no more than 60 seconds.",
                           terminated=False)
    if os.name != 'nt':
        raise ProcessError("Explicit registered-process termination is available only on Windows.",
                           terminated=False)

    import ctypes
    from ctypes import wintypes

    started = time.monotonic()
    termination_requested = False

    def failure(message, operation, reason, *, windows_error=False):
        cause = None
        if windows_error:
            # Store only the numeric Windows cause, never its path-bearing text.
            cause = OSError()
            cause.winerror = ctypes.get_last_error()
        return ProcessError(message, cause=cause, operation=operation, reason=reason,
                            elapsed_seconds=time.monotonic() - started,
                            timeout_seconds=timeout,
                            terminated=None if termination_requested else False)

    try:
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    except OSError as error:
        raise ProcessError("Process access could not be prepared; no process was terminated.",
                           cause=error, operation='process_open', reason='identity_unavailable',
                           terminated=False) from None
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
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.TerminateProcess.restype = wintypes.BOOL
    # PROCESS_TERMINATE | PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE.
    handle = kernel.OpenProcess(0x0001 | 0x1000 | 0x100000, False, pid)
    if not handle:
        if ctypes.get_last_error() == 87:  # ERROR_INVALID_PARAMETER: PID no longer exists.
            return False
        raise failure("Process access was refused; no process was terminated.",
                      'process_open', 'identity_unavailable', windows_error=True) from None

    def wait(milliseconds):
        result = kernel.WaitForSingleObject(handle, milliseconds)
        if result == 0xFFFFFFFF:  # WAIT_FAILED, never treat it as a running process.
            raise failure("Process exit could not be inspected.", 'process_wait',
                          'identity_unavailable', windows_error=True) from None
        if result not in (0, 258):  # WAIT_OBJECT_0 or WAIT_TIMEOUT only.
            raise failure("Process exit status is unknown.", 'process_wait',
                          'identity_unavailable') from None
        return result

    try:
        if wait(0) == 0:
            return False
        times = [wintypes.FILETIME() for _ in range(4)]
        image, length = ctypes.create_unicode_buffer(32768), wintypes.DWORD(32768)
        if (not kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in times))
                or not kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(length))):
            raise failure("Process identity could not be inspected; no process was terminated.",
                          'process_inspect', 'identity_unavailable', windows_error=True) from None
        actual = {'pid': pid, 'executable': os.path.normcase(os.path.realpath(image.value)),
                  'created_at': str((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)}
        if not _same(actual, identity):
            raise failure("Process identity changed; no process was terminated.",
                          'process_inspect', 'identity_changed') from None
        if wait(0) == 0:
            return False
        if not kernel.TerminateProcess(handle, 1):
            raise failure("The registered process could not be terminated.",
                          'process_terminate', 'termination_failed', windows_error=True) from None
        termination_requested = True
        if wait(math.ceil(timeout * 1000)) != 0:
            raise failure("The registered process did not finish terminating in time.",
                          'process_wait', 'termination_timeout') from None
        return True
    finally:
        kernel.CloseHandle(handle)


def check_accept_runtime(python_exe, cwd):
    """Probe the selected interpreter without importing WebUI or binding a port."""
    if sys.platform != 'win32':
        return 'not_applicable'
    guard = Path(__file__).resolve().with_name('ees_deploy_accept.py')
    try:
        result = subprocess.run([str(python_exe), '-I', '-B', str(guard), '--check'],
                                cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True,
                                timeout=10, check=False)
        if result.returncode == 0 and result.stdout.strip() == b'EES accept_check=compatible':
            return 'compatible'
    except (OSError, subprocess.SubprocessError):
        pass
    raise ProcessError('The selected Python does not pass the accept guard check; no server was changed.',
                       reason='accept_guard_incompatible') from None


def accept_guard_status(identity):
    """Read only the new child's fixed startup marker, without exposing its log."""
    if sys.platform != 'win32':
        return 'not_applicable'
    try:
        with Path(identity['log_file']).open('rb') as log:
            if b'EES accept_guard=win64_retry loop=proactor' in log.read(4096).splitlines():
                return 'win64_retry'
    except (KeyError, TypeError, OSError):
        pass
    raise ProcessError('The current child accept guard could not be verified; inspect its local log.',
                       reason='accept_guard_incompatible') from None


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
    # Only the child changes IOCP accept; Stop/Status and the operator are unchanged.
    guard = Path(__file__).resolve().with_name('ees_deploy_accept.py')
    guard_code = f"import runpy; runpy.run_path({str(guard)!r})['install']()\n"
    code_index = command.index('-c') + 1
    command[code_index] = guard_code + command[code_index]
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


def _parse_stop_helper_failure(payload):
    """Accept only the helper's bounded, fixed metadata; never propagate its text."""
    if type(payload) is not bytes or len(payload) > 4096:
        return None
    try:
        detail = json.loads(payload.decode('utf-8'))
    except (ValueError, UnicodeError, RecursionError):
        return None
    if type(detail) is not dict or set(detail) != {'operation', 'reason', 'errno', 'winerror'}:
        return None
    for key, allowed in (('operation', _OPERATIONS), ('reason', _REASONS)):
        if detail[key] is not None and (type(detail[key]) is not str or detail[key] not in allowed):
            return None
    if any(detail[key] is not None and type(detail[key]) is not int for key in ('errno', 'winerror')):
        return None
    cause = OSError()
    cause.errno, cause.winerror = detail['errno'], detail['winerror']
    return ProcessError("Graceful stop could not be delivered; use the original server console.",
                        cause=cause, operation=detail['operation'] or 'stop_helper',
                        reason=detail['reason'] or 'stop_helper_failed')


def _request_windows_stop(identity):
    try:
        helper = subprocess.Popen([sys.executable, '-I', str(Path(__file__).resolve()), '--break', json.dumps(identity)],
                                  stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
    except OSError as error:
        raise ProcessError("The console helper could not be started; no signal was sent.",
                           cause=error, operation='stop_helper', reason='stop_helper_failed',
                           timeout_seconds=5) from None
    try:
        try:
            exit_code = helper.wait(timeout=5)
        except subprocess.TimeoutExpired:
            raise ProcessError("The console helper did not finish; no force kill was attempted.",
                               operation='stop_helper', reason='stop_helper_timeout', timeout_seconds=5) from None
        if exit_code != 0:
            # The internal helper emits at most one small JSON record and has
            # exited before this bounded read. Arbitrary output is discarded.
            error = _parse_stop_helper_failure(helper.stdout.read(4097))
            if error is None:
                error = ProcessError("Graceful stop could not be delivered; use the original server console.",
                                     operation='stop_helper', reason='stop_helper_failed')
            error.exit_code = exit_code if type(exit_code) is int else None
            error.timeout_seconds = 5
            raise error
    except OSError as error:
        raise ProcessError("The console helper result could not be inspected.",
                           cause=error, operation='stop_helper', reason='stop_helper_failed',
                           timeout_seconds=5) from None
    finally:
        if helper.stdout is not None:
            helper.stdout.close()


def _stop_server(identity, timeout):
    if not isinstance(identity, dict) or identity.get('group_id') != identity.get('pid'):
        raise ProcessError("The saved process group is invalid; no signal was sent.",
                           operation='process_inspect', reason='identity_changed')
    actual = _identity(identity.get('pid'))
    if actual is None:
        return
    if not _same(actual, identity):
        raise ProcessError("Process identity changed; no signal was sent.",
                           operation='process_inspect', reason='identity_changed')
    if os.name == 'nt':
        _request_windows_stop(identity)
    else:
        if os.getpgid(identity['pid']) != identity['group_id'] or not verify_identity(identity):
            raise ProcessError("Process group changed; no signal was sent.",
                               operation='process_inspect', reason='identity_changed')
        try:
            os.killpg(identity['group_id'], signal.SIGINT)
        except OSError as error:
            raise ProcessError("The graceful stop signal could not be delivered.", cause=error,
                               operation='console_signal', reason='stop_signal_failed') from None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _same(_identity(identity['pid']), identity):
            return
        time.sleep(min(0.1, max(0, deadline - time.monotonic())))
    raise ProcessError("Graceful stop timed out; the process was not force-killed.",
                       operation='process_wait', reason='stop_timeout', timeout_seconds=timeout)


def stop_server(identity, timeout=30):
    started = time.monotonic()
    try:
        _stop_server(identity, timeout)
    except (ProcessError, OSError) as error:
        log_file = identity.get('log_file') if isinstance(identity, dict) else None
        messages = {
            'identity_changed': "Process identity changed; no signal was sent.",
            'stop_signal_failed': "The graceful stop signal could not be delivered.",
            'stop_helper_failed': "Graceful stop could not be delivered; use the original server console.",
            'stop_helper_timeout': "The console helper did not finish; no force kill was attempted.",
            'stop_timeout': "Graceful stop timed out; the process was not force-killed.",
        }
        message = messages.get(getattr(error, 'reason', None),
                               "Graceful stop failed; inspect the saved operation details.")
        failure = ProcessError(message, cause=error,
                               operation=getattr(error, 'operation', None) or 'process_inspect',
                               reason=getattr(error, 'reason', None) or 'identity_unavailable',
                               elapsed_seconds=time.monotonic() - started,
                               timeout_seconds=(getattr(error, 'timeout_seconds', None)
                                                if getattr(error, 'timeout_seconds', None) is not None else timeout),
                               exit_code=getattr(error, 'exit_code', None),
                               log_id=Path(log_file).name if type(log_file) is str else None)
        raise failure from None


def _console_helper_main():
    try:
        if os.name != 'nt' or len(sys.argv) != 3 or sys.argv[1] != '--break':
            raise ProcessError("Internal console helper only.")
        saved = json.loads(sys.argv[2])
        _windows_identity(saved['pid'], send_to=saved)
    except (ProcessError, OSError, ValueError, KeyError, TypeError) as error:
        safe = ProcessError("Console helper failed.", cause=error,
                            operation=getattr(error, 'operation', None) or 'stop_helper',
                            reason=getattr(error, 'reason', None) or 'stop_helper_failed')
        print(json.dumps({key: getattr(safe, key) for key in ('operation', 'reason', 'errno', 'winerror')},
                         separators=(',', ':')))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(_console_helper_main())
