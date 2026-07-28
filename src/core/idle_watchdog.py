"""Idle-exit watchdog for the stdio MCP server.

Reaps abandoned / parked server processes. A stdio MCP server is supposed to
exit when the client closes the pipe, but some clients (notably the Claude
desktop app and Claude Code) keep the pipe open and park the server instead of
re-spawning it on the next tool call. Exiting the process on idle (the
original SH-12881 design) assumed the client would re-spawn; it does not --
Claude Code/Desktop mark a stdio server that exits while the pipe is still
open as FAILED and never restart it, so every real interactive session with
more than an idle-timeout gap between tool calls permanently lost the server
(SH-13610).

The fix (SH-13610): on idle expiry, RELEASE resources instead of exiting --
close the sqlite connection, which rolls back any dangling write transaction
and releases the write lock (the original SH-12881 problem), and reopen it
lazily on the next MCP message. The process stays alive so parked clients keep
a working connection. A much longer backstop timeout, if configured, still
hard-exits as a last resort for processes that are genuinely abandoned (e.g.
the client itself is long gone), so long-idle processes do not accumulate
forever.
"""

import os
import sys
import threading
import time

import mcp.types as types

DEFAULT_IDLE_TIMEOUT = 300.0  # 5 minutes: triggers a resource release, not exit.
DEFAULT_BACKSTOP_TIMEOUT = 86400.0  # 24 hours: last-resort process exit.


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
    """Tracks last-activity time; releases idle resources, and (optionally,
    after a much longer backstop timeout) exits the process as a last resort.
    """

    def __init__(self, timeout, clock=time.monotonic, release_func=None,
                 exit_func=None, backstop_timeout=None, check_interval=None):
        self.timeout = timeout
        self.backstop_timeout = backstop_timeout
        self._clock = clock
        self._release_func = release_func if release_func is not None else (lambda: None)
        self._exit_func = exit_func if exit_func is not None else (lambda: os._exit(0))
        # Check often enough to react promptly, but never busier than 1/sec.
        self._check_interval = check_interval or min(60.0, max(1.0, timeout / 10.0))
        self._lock = threading.Lock()
        self._last = clock()
        self._released = False
        self._thread = None

    def touch(self):
        """Record activity now, resetting the idle clock."""
        with self._lock:
            self._last = self._clock()
            self._released = False

    def idle_seconds(self):
        with self._lock:
            return self._clock() - self._last

    def expired(self):
        return self.idle_seconds() >= self.timeout

    def backstop_expired(self):
        if self.backstop_timeout is None:
            return False
        return self.idle_seconds() >= self.backstop_timeout

    def _safe_log(self, message):
        try:
            sys.stderr.write(message)
            sys.stderr.flush()
        except Exception:
            # stderr may be a broken pipe/socket once the client parks or
            # drops the connection. Logging must never block the release/exit
            # action -- a raise here would kill this thread and leak the
            # process forever.
            pass

    def _run(self):
        while True:
            time.sleep(self._check_interval)

            if self.backstop_expired():
                self._safe_log(
                    "[idle-watchdog] no MCP activity for %.0fs (>= backstop "
                    "%.0fs); exiting as a last resort\n"
                    % (self.idle_seconds(), self.backstop_timeout)
                )
                self._exit_func()
                return

            if self.expired():
                with self._lock:
                    already_released = self._released
                    self._released = True
                if already_released:
                    continue
                self._safe_log(
                    "[idle-watchdog] no MCP activity for %.0fs (>= %.0fs); "
                    "releasing idle resources (process stays alive)\n"
                    % (self.idle_seconds(), self.timeout)
                )
                self._release_func()

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(
                target=self._run, name="idle-watchdog", daemon=True
            )
            self._thread.start()
        return self


def _is_ping(message):
    """True if an inbound _handle_message payload is a client PingRequest.

    A client that parks the pipe open but keeps sending keepalive pings (e.g.
    Hermes) would otherwise reset the idle timer forever, defeating the
    watchdog for exactly the parked-connection case it exists to catch.
    """
    request = getattr(message, "request", None)
    root = getattr(request, "root", None)
    return isinstance(root, types.PingRequest)


def install(mcp, env_var, default_timeout=DEFAULT_IDLE_TIMEOUT,
            clock=time.monotonic, release_func=None, exit_func=None,
            backstop_env_var=None, default_backstop_timeout=DEFAULT_BACKSTOP_TIMEOUT,
            start=True):
    """Attach an IdleWatchdog to a FastMCP server.

    Wraps the low-level server's message handler so every inbound MCP message
    except a bare PingRequest resets the idle timer, then (by default) starts
    the watchdog thread. Returns the watchdog so callers/tests can inspect it.

    release_func is called once per idle period once `timeout` elapses with no
    activity (e.g. closing a held DB connection); the process keeps running.
    If backstop_env_var is given, a much longer backstop timeout is resolved
    from that env var (falling back to default_backstop_timeout) and
    exit_func is called as a last resort once idle time reaches it. Leaving
    backstop_env_var as None disables the hard-exit path entirely.
    """
    timeout = resolve_timeout(env_var, default_timeout)
    backstop_timeout = None
    if backstop_env_var is not None:
        backstop_timeout = resolve_timeout(backstop_env_var, default_backstop_timeout)
    watchdog = IdleWatchdog(
        timeout, clock=clock, release_func=release_func, exit_func=exit_func,
        backstop_timeout=backstop_timeout,
    )

    server = mcp._mcp_server  # low-level Server; mcp version is pinned
    original_handle_message = server._handle_message

    async def _handle_message(*args, **kwargs):
        message = args[0] if args else None
        if not _is_ping(message):
            watchdog.touch()
        return await original_handle_message(*args, **kwargs)

    server._handle_message = _handle_message
    if start:
        watchdog.start()
    return watchdog
