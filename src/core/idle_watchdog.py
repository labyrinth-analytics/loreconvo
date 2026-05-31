"""Idle-exit watchdog for the stdio MCP server.

Reaps abandoned / parked server processes. A stdio MCP server is supposed to
exit when the client closes the pipe, but some clients (notably the Claude
desktop app) keep the pipe open and park the server, so processes accumulate
for days. A long-lived server that ever left a write transaction uncommitted
then sits on the sqlite write lock indefinitely, blocking every other writer.

This watchdog bounds that: if no MCP message arrives for the idle timeout, the
process exits cleanly. Exiting closes the database connection, which rolls back
any dangling write transaction and releases the lock. The client re-spawns the
server on its next tool call.
"""

import os
import sys
import threading
import time

DEFAULT_IDLE_TIMEOUT = 1800.0  # 30 minutes


def resolve_timeout(env_var, default=DEFAULT_IDLE_TIMEOUT):
    """Return the idle timeout in seconds, allowing an env override.

    A non-positive or unparseable value falls back to the default.
    """
    raw = os.environ.get(env_var)
    if raw is None:
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


class IdleWatchdog:
    """Tracks last-activity time and exits the process once idle too long."""

    def __init__(self, timeout, clock=time.monotonic, exit_func=None,
                 check_interval=None):
        self.timeout = timeout
        self._clock = clock
        self._exit_func = exit_func if exit_func is not None else (lambda: os._exit(0))
        # Check often enough to react promptly, but never busier than 1/sec.
        self._check_interval = check_interval or min(60.0, max(1.0, timeout / 10.0))
        self._lock = threading.Lock()
        self._last = clock()
        self._thread = None

    def touch(self):
        """Record activity now, resetting the idle clock."""
        with self._lock:
            self._last = self._clock()

    def idle_seconds(self):
        with self._lock:
            return self._clock() - self._last

    def expired(self):
        return self.idle_seconds() >= self.timeout

    def _run(self):
        while True:
            time.sleep(self._check_interval)
            if self.expired():
                sys.stderr.write(
                    "[idle-watchdog] no MCP activity for %.0fs (>= %.0fs); "
                    "exiting to release resources\n"
                    % (self.idle_seconds(), self.timeout)
                )
                sys.stderr.flush()
                self._exit_func()
                return

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(
                target=self._run, name="idle-watchdog", daemon=True
            )
            self._thread.start()
        return self


def install(mcp, env_var, default_timeout=DEFAULT_IDLE_TIMEOUT,
            clock=time.monotonic, exit_func=None, start=True):
    """Attach an IdleWatchdog to a FastMCP server.

    Wraps the low-level server's message handler so every inbound MCP message
    resets the idle timer, then (by default) starts the watchdog thread.
    Returns the watchdog so callers/tests can inspect it.
    """
    timeout = resolve_timeout(env_var, default_timeout)
    watchdog = IdleWatchdog(timeout, clock=clock, exit_func=exit_func)

    server = mcp._mcp_server  # low-level Server; mcp version is pinned
    original_handle_message = server._handle_message

    async def _handle_message(*args, **kwargs):
        watchdog.touch()
        return await original_handle_message(*args, **kwargs)

    server._handle_message = _handle_message
    if start:
        watchdog.start()
    return watchdog
