"""Process-local CPython 3.11 IOCP accept workaround for python/cpython#93821.

Keep the Proactor loop and its subprocess/pipe support. Retry ONLY WinError 64,
close the failed client socket, and let cancellation/other errors propagate.
No application import, filesystem writes, environment changes or service control.
The original accept implementation is AST-pinned; unknown implementations fail
closed before Open WebUI is imported. Reassess this workaround on Python upgrade.
"""

import ast
import asyncio
import hashlib
import inspect
import logging
import socket
import struct
import sys
import textwrap


RETRY_DELAY = 0.1
ORIGINAL_ACCEPT_AST = 'd8f4c966cac56c7940ddda0020dfee3f50dde12a57f1a931326bfa565f3c57e6'
_INSTALLED = None
_logger = logging.getLogger('ees.runtime.accept')


def _source_digest(method):
    # A field-based representation avoids ast.dump default changes after 3.11.
    def canonical(value):
        if isinstance(value, ast.AST):
            return (type(value).__name__, tuple((key, canonical(item))
                    for key, item in ast.iter_fields(value)
                    if key != 'type_params' or item))
        if isinstance(value, list):
            return tuple(canonical(item) for item in value)
        return value
    tree = ast.parse(textwrap.dedent(inspect.getsource(method)))
    return hashlib.sha256(repr(canonical(tree)).encode()).hexdigest()


def _make_accept(overlapped):
    async def accept_retry(proactor, listener):
        while True:
            proactor._check_closed()
            if listener.fileno() == -1 or listener in proactor._stopped_serving:
                raise asyncio.CancelledError()
            proactor._register_with_iocp(listener)
            conn = proactor._get_accept_socket(listener.family)
            try:
                ov = overlapped.Overlapped(0)
                ov.AcceptEx(listener.fileno(), conn.fileno())

                def finish_accept(transferred, key, completed):
                    completed.getresult()
                    conn.setsockopt(socket.SOL_SOCKET, overlapped.SO_UPDATE_ACCEPT_CONTEXT,
                                    struct.pack('@P', listener.fileno()))
                    conn.settimeout(listener.gettimeout())
                    return conn, conn.getpeername()

                # _register retains the OVERLAPPED until IOCP completion. Task
                # cancellation propagates to its _OverlappedFuture (CancelIoEx).
                future = proactor._register(ov, listener, finish_accept)
                return await future
            except OSError as error:
                conn.close()
                if getattr(error, 'winerror', None) != 64:
                    raise
                if listener.fileno() == -1 or listener in proactor._stopped_serving:
                    raise asyncio.CancelledError() from None
                count = getattr(proactor, '_ees_accept64_retries', 0) + 1
                proactor._ees_accept64_retries = count
                # Fixed labels only; exponentially spaced messages avoid flooding.
                if count & (count - 1) == 0:
                    _logger.warning('EES accept_retry winerror=64 count=%d', count)
                await asyncio.sleep(RETRY_DELAY)
            except BaseException:
                # Includes cancellation after IOCP succeeded but before the task
                # resumed: that accepted socket has no transport owner yet.
                conn.close()
                raise

    def accept(proactor, listener):
        proactor._check_closed()
        return proactor._loop.create_task(accept_retry(proactor, listener))

    return accept


def check():
    """Read-only compatibility check; never install into the operator process."""
    if sys.platform != 'win32':
        return False
    if sys.implementation.name != 'cpython' or sys.version_info[:2] != (3, 11):
        raise RuntimeError('EES accept guard requires reviewed Windows CPython 3.11; no fallback.')
    import _overlapped
    from asyncio import windows_events

    proactor = windows_events.IocpProactor
    if _INSTALLED is not None and proactor.accept is _INSTALLED:
        return True
    try:
        valid = (proactor.accept.__module__ == 'asyncio.windows_events'
                 and _source_digest(proactor.accept) == ORIGINAL_ACCEPT_AST
                 and _overlapped.ERROR_NETNAME_DELETED == 64
                 and all(callable(getattr(proactor, name, None)) for name in
                         ('_check_closed', '_register_with_iocp', '_get_accept_socket', '_register')))
    except (OSError, TypeError, ValueError, AttributeError, SyntaxError):
        valid = False
    if not valid:
        raise RuntimeError('EES accept guard does not recognize this runtime; no fallback.')
    return True


def install():
    """Install once, in the child only. Non-Windows test launches are unchanged."""
    global _INSTALLED
    if not check():
        return False
    import _overlapped
    from asyncio import windows_events
    if windows_events.IocpProactor.accept is not _INSTALLED:
        _INSTALLED = _make_accept(_overlapped)
        windows_events.IocpProactor.accept = _INSTALLED
    print('EES accept_guard=win64_retry loop=proactor', flush=True)
    return True


if __name__ == '__main__':
    if sys.argv[1:] != ['--check']:
        raise SystemExit(2)
    try:
        supported = check()
    except (RuntimeError, ImportError):
        print('EES accept_check=incompatible')
        raise SystemExit(1) from None
    print('EES accept_check=' + ('compatible' if supported else 'not_applicable'))
