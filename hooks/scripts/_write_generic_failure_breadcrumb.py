"""Fallback breadcrumb writer invoked by shell wrappers on hook non-zero exit.

SH-100629: `_bootstrap._write_breadcrumb` is only reachable from the hook's
own `except BootstrapError` handler. A failure ABOVE that handler -- any
import error at module scope -- kills the process before the handler exists,
so the richer breadcrumb never gets written. This script is the shell-side
backstop: the wrapper always runs it when the hook process exits non-zero,
and it writes a generic breadcrumb UNLESS the hook's own handler already
wrote a richer one during this same invocation.

Runs on the system's plain python3, never via uvx/the loreconvo package --
if the hook died on a broken package import, the fallback must not depend
on that same package to report it.

Freshness check: the wrapper records a timestamp just before launching the
hook. If hook_failure.json already exists and is newer than that timestamp,
the hook's own handler covered this failure already -- do not overwrite its
richer content (probed paths, actual exception) with this generic message.
"""

import json
import os
import sys
from datetime import datetime, timezone


def main(argv):
    if len(argv) != 4:
        sys.stderr.write(
            "usage: _write_generic_failure_breadcrumb.py "
            "<hook_name> <exit_code> <since_epoch>\n"
        )
        return 2

    hook_name, exit_code, since_epoch_str = argv[1], argv[2], argv[3]
    try:
        since_epoch = float(since_epoch_str)
    except ValueError:
        since_epoch = 0.0

    data_dir = os.environ.get("LORECONVO_DATA_DIR", os.path.expanduser("~/.loreconvo"))
    breadcrumb_path = os.path.join(data_dir, "hook_failure.json")

    if os.path.exists(breadcrumb_path) and os.path.getmtime(breadcrumb_path) >= since_epoch:
        # The hook's own BootstrapError handler already wrote a richer
        # breadcrumb for this run -- leave it alone.
        return 0

    try:
        os.makedirs(data_dir, exist_ok=True)
        payload = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "hook": hook_name,
            "error": (
                f"hook process exited {exit_code} before reaching its own "
                "error handler (likely a module-scope import failure)"
            ),
            "probed": [],
        }
        with open(breadcrumb_path, "w") as f:
            json.dump(payload, f)
        try:
            os.chmod(breadcrumb_path, 0o600)
        except OSError:
            pass
    except OSError as exc:
        sys.stderr.write(
            f"WARNING: Cannot write fallback hook failure breadcrumb to "
            f"{breadcrumb_path}: {exc}\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
