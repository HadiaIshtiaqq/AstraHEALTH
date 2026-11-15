"""Offline enforcement.

When ALLOW_EXTERNAL_NETWORK is false, every outbound socket connection to a
non-loopback address is refused *in code*. An environment variable alone is not
proof that no network calls occur, so this guard patches the socket layer and keeps
a counter of blocked attempts that is reported by /api/v1/system/health.
"""
from __future__ import annotations

import ipaddress
import logging
import socket
import threading

log = logging.getLogger("astrahealth.netguard")

_LOOPBACK_NAMES = {"localhost", "localhost.localdomain", "ip6-localhost"}
_state = {"installed": False, "blocked_attempts": 0, "last_blocked": None}
_lock = threading.Lock()
_original_connect = socket.socket.connect
_original_connect_ex = socket.socket.connect_ex
_original_create_connection = socket.create_connection
_original_getaddrinfo = socket.getaddrinfo


class ExternalNetworkBlocked(ConnectionRefusedError):
    """Raised when code attempts an outbound connection in offline mode."""


def is_loopback_host(host: object) -> bool:
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode(errors="ignore")
    host = str(host).strip("[]").lower()
    if host in _LOOPBACK_NAMES or host == "":
        return True
    try:
        return ipaddress.ip_address(host.split("%")[0]).is_loopback
    except ValueError:
        return False


def _record_block(host: object) -> None:
    with _lock:
        _state["blocked_attempts"] += 1
        _state["last_blocked"] = str(host)
    log.warning("Blocked outbound network attempt to %s (offline mode)", host)


def _check_address(address: object) -> None:
    if isinstance(address, tuple) and address:
        host = address[0]
        if not is_loopback_host(host):
            _record_block(host)
            raise ExternalNetworkBlocked(f"External network disabled (offline mode): {host}")


def _guarded_connect(self: socket.socket, address):  # type: ignore[no-untyped-def]
    if self.family in (socket.AF_INET, socket.AF_INET6):
        _check_address(address)
    return _original_connect(self, address)


def _guarded_connect_ex(self: socket.socket, address):  # type: ignore[no-untyped-def]
    if self.family in (socket.AF_INET, socket.AF_INET6):
        _check_address(address)
    return _original_connect_ex(self, address)


def _guarded_create_connection(address, *args, **kwargs):  # type: ignore[no-untyped-def]
    _check_address(address)
    return _original_create_connection(address, *args, **kwargs)


def _guarded_getaddrinfo(host, *args, **kwargs):  # type: ignore[no-untyped-def]
    # Refuse DNS resolution of external names so no lookup leaves the machine.
    if not is_loopback_host(host):
        _record_block(host)
        raise ExternalNetworkBlocked(f"External DNS disabled (offline mode): {host}")
    return _original_getaddrinfo(host, *args, **kwargs)


def install() -> None:
    with _lock:
        if _state["installed"]:
            return
        socket.socket.connect = _guarded_connect  # type: ignore[method-assign]
        socket.socket.connect_ex = _guarded_connect_ex  # type: ignore[method-assign]
        socket.create_connection = _guarded_create_connection  # type: ignore[assignment]
        socket.getaddrinfo = _guarded_getaddrinfo  # type: ignore[assignment]
        _state["installed"] = True
    log.info("Offline network guard installed: only loopback connections are allowed")


def uninstall() -> None:
    with _lock:
        socket.socket.connect = _original_connect  # type: ignore[method-assign]
        socket.socket.connect_ex = _original_connect_ex  # type: ignore[method-assign]
        socket.create_connection = _original_create_connection  # type: ignore[assignment]
        socket.getaddrinfo = _original_getaddrinfo  # type: ignore[assignment]
        _state["installed"] = False


def status() -> dict:
    with _lock:
        return dict(_state)
