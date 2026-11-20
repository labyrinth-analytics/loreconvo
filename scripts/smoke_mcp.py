#!/usr/bin/env python3
"""Cross-platform MCP stdio smoke test for the Lore products.

For a product it verifies, over a real stdio MCP connection:
  1. the MCP server starts and answers `initialize`,
  2. `tools/list` returns the same number of tools as `@mcp.tool` decorators
     in the server source (count derived at runtime from the source -- never
     a hardcoded number),
  3. the product's critical tools are present,
  4. a save -> search -> recall round trip succeeds end-to-end.

Exit 0 = all checks passed; exit 1 = any check failed. Driven by
.github/workflows/smoke.yml (GitHub Actions cross-platform matrix).

Env isolation: sets a fresh data dir (LORECONVO_DB / LOREDOCS_ROOT) and
strips LORECONVO_PRO / LOREDOCS_PRO / LAB_DEV_MODE so the smoke run never
touches a developer's real DB or tier.

Usage:
    python3 scripts/smoke_mcp.py --product loreconvo
    python3 scripts/smoke_mcp.py --product loredocs
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import json
import os
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Overall ceiling for the whole stdio session (SH-106804).
SMOKE_TIMEOUT_SECONDS = 120

# ---------------------------------------------------------------------------
# Per-product configuration
# ---------------------------------------------------------------------------
# server_py is relative to the repo root (the working directory when the
# GitHub Actions workflow or Docker smoke runs). The smoke script is at
# scripts/smoke_mcp.py; both products' server source sits next to it in the
# checked-out tree.
PRODUCTS = {
    "loreconvo": {
        "module": "loreconvo.server",
        "server_py": "src/server.py",
        "critical": ["save_session", "search_sessions", "get_session"],
    },
    "loredocs": {
        "module": "loredocs.server",
        "server_py": "loredocs/server.py",
        "critical": [
            "vault_create",
            "vault_add_doc",
            "vault_search",
            "vault_get_doc",
        ],
    },
}


# ---------------------------------------------------------------------------
# Tool-count accessor: counts @mcp.tool decorators via AST so the smoke test
# derives the expected count from the source instead of a magic number.
# ---------------------------------------------------------------------------
def _tool_decorator(fn) -> ast.Call | ast.Name | None:
    for dec in fn.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(target, ast.Attribute) and target.attr == "tool":
            return dec
        if isinstance(target, ast.Name) and target.id == "tool":
            return dec
    return None


def count_tools(server_py: Path) -> tuple[int, int]:
    """Count @mcp.tool-decorated defs in server.py -> (registered, conditional).

    Mirrors the monorepo count_mcp_tools.py: 'registered' is the count of
    module-top-level decorated defs (always active); 'conditional' is the
    count of decorated defs nested inside an if/with/try (env-gated, register
    only when their gate is satisfied). A live server therefore registers
    between `registered` and `registered + conditional` tools depending on the
    environment -- never a hardcoded number.
    """
    tree = ast.parse(server_py.read_text(encoding="utf-8"))
    registered = 0
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if _tool_decorator(node) is not None:
                registered += 1
    conditional = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.Try, ast.With)):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if _tool_decorator(child) is not None:
                        conditional += 1
    return registered, conditional


# ---------------------------------------------------------------------------
# MCP helpers
# ---------------------------------------------------------------------------
async def call_tool(session: ClientSession, name: str, arguments: dict) -> str:
    result = await session.call_tool(name, arguments=arguments)
    if result.isError:
        raise RuntimeError(f"tool '{name}' returned an error: {result}")
    if result.content and len(result.content) > 0:
        return result.content[0].text
    return ""


def _as_json(text: str):
    """Parse a tool result as JSON, tolerating markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    return json.loads(text)


# ---------------------------------------------------------------------------
# Round trips
# ---------------------------------------------------------------------------
async def _round_trip_loreconvo(session: ClientSession) -> str:
    # Single clean alphanumeric token (no dash) so FTS5 tokenizes the marker
    # as one term and the search query matches it exactly.
    marker = f"smokemarker{uuid.uuid4().hex[:12]}"
    saved_raw = await call_tool(
        session,
        "save_session",
        {
            "title": f"Smoke test {marker}",
            "surface": "smoke",
            "summary": f"Cross-platform smoke marker {marker}",
            "tags": ["smoke"],
        },
    )
    saved = _as_json(saved_raw)
    session_id = saved.get("id") or saved.get("session_id")
    if not session_id:
        raise RuntimeError(f"save_session returned no id: {saved_raw[:200]}")

    found_raw = await call_tool(session, "search_sessions", {"query": marker})
    found = _as_json(found_raw)
    # search_sessions returns a single object when there is one hit and a
    # list when there are several -- normalize both to a list.
    if isinstance(found, dict):
        found = [found]
    if not isinstance(found, list) or len(found) == 0:
        raise RuntimeError(f"search_sessions found nothing for {marker}")
    ids = [str(f.get("id")) for f in found if isinstance(f, dict)]
    if session_id not in ids:
        raise RuntimeError(
            f"search_sessions did not return the saved session {session_id} "
            f"(got {ids})"
        )

    recalled_raw = await call_tool(session, "get_session", {"session_id": session_id})
    recalled = _as_json(recalled_raw)
    summary = recalled.get("summary", "")
    if marker not in summary:
        raise RuntimeError(f"recalled summary missing marker {marker}")
    return session_id


async def _round_trip_loredocs(session: ClientSession) -> str:
    marker = f"smokemarker{uuid.uuid4().hex[:12]}"
    vault_name = f"smoke{uuid.uuid4().hex[:8]}"

    created_raw = await call_tool(
        session,
        "vault_create",
        {"name": vault_name, "response_format": "json"},
    )
    created = _as_json(created_raw)
    if created.get("id") is None:
        raise RuntimeError(f"vault_create returned no id: {created_raw[:200]}")

    added_raw = await call_tool(
        session,
        "vault_add_doc",
        {
            "vault": vault_name,
            "name": f"Smoke doc {marker}",
            "content": f"Cross-platform smoke marker {marker}",
            "response_format": "json",
        },
    )
    added = _as_json(added_raw)
    doc_id = added.get("id")
    if doc_id is None:
        raise RuntimeError(f"vault_add_doc returned no id: {added_raw[:200]}")

    found_raw = await call_tool(
        session,
        "vault_search",
        {"query": marker, "vault": vault_name, "response_format": "json"},
    )
    if marker not in found_raw:
        raise RuntimeError(f"vault_search found nothing for {marker}")

    got_raw = await call_tool(
        session,
        "vault_get_doc",
        {"doc_id": doc_id, "include_content": True, "response_format": "markdown"},
    )
    if marker not in got_raw:
        raise RuntimeError(f"vault_get_doc content missing marker {marker}")
    return doc_id


ROUND_TRIPS = {
    "loreconvo": _round_trip_loreconvo,
    "loredocs": _round_trip_loredocs,
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def run(product: str, repo_root: Path) -> int:
    cfg = PRODUCTS[product]
    server_py = repo_root / cfg["server_py"]
    if not server_py.exists():
        print(f"[FAIL] server source not found at {server_py}")
        return 1
    registered, conditional = count_tools(server_py)
    print(
        f"[INFO] {product}: {registered} registered + {conditional} conditional "
        f"tools (from {cfg['server_py']})"
    )

    # Isolate data + strip any leaked Pro/dev tier from the environment.
    tmp = tempfile.mkdtemp(prefix=f"smoke-{product}-")
    env = os.environ.copy()
    for var in ("LORECONVO_PRO", "LOREDOCS_PRO", "LAB_DEV_MODE"):
        env.pop(var, None)
    if product == "loreconvo":
        env["LORECONVO_DB"] = str(Path(tmp) / "sessions.db")
    else:
        env["LOREDOCS_ROOT"] = tmp

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", cfg["module"]],
        env=env,
    )

    async def _run() -> int:
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                print("[OK] initialize")

                tools = await session.list_tools()
                names = [t.name for t in tools.tools]
                actual = len(names)
                print(f"[INFO] tools/list returned {actual} tools")
                if not (registered <= actual <= registered + conditional):
                    print(
                        f"[FAIL] tool count out of range: expected "
                        f"{registered}..{registered + conditional}, got {actual}"
                    )
                    return 1
                print(
                    f"[OK] tool count in range {registered}..{registered + conditional}"
                    f" (got {actual})"
                )

                missing = [t for t in cfg["critical"] if t not in names]
                if missing:
                    print(f"[FAIL] critical tools missing: {missing}")
                    return 1
                print(f"[OK] critical tools present: {cfg['critical']}")

                artifact_id = await ROUND_TRIPS[product](session)
                print(f"[OK] save -> search -> recall round trip ({artifact_id})")

        return 0

    try:
        return await asyncio.wait_for(_run(), timeout=SMOKE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        print(
            f"[FAIL] {product} smoke timed out after {SMOKE_TIMEOUT_SECONDS}s "
            "(server did not complete initialize/list/round trip)"
        )
        return 2
    except Exception as exc:  # noqa: BLE001 -- smoke test must fail loudly
        import traceback

        print(f"[FAIL] {product} smoke failed: {exc}")
        traceback.print_exc()
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--product",
        required=True,
        choices=sorted(PRODUCTS),
        help="Which product to smoke-test.",
    )
    ap.add_argument(
        "--repo-root",
        default=".",
        help="Repo root containing server.py source (default: current dir).",
    )
    args = ap.parse_args()
    return asyncio.run(run(args.product, Path(args.repo_root)))


if __name__ == "__main__":
    sys.exit(main())
