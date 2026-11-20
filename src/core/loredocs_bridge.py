"""Bridge to LoreDocs cross-product data WITHOUT importing the loredocs package.

SH-100670: marketplace installs run each product in an isolated uvx
environment, so ``from loredocs.storage import ...`` raises ImportError
even when LoreDocs is installed and its database is present. This module
reaches LoreDocs the same way LoreDocs already reaches LoreConvo in the
reverse direction: direct sqlite3 access to ~/.loredocs/loredocs.db.

Single-source-of-truth statement (drift rule 1)
------------------------------------------------
The cross-link constants below (CROSS_LINK_SCHEMA_VERSION,
REQUIRED_CROSS_LINK_SCHEMA_VERSION, CROSS_LINK_EMBEDDING_MODEL,
CROSS_LINK_EMBEDDING_DIM, CROSS_LINK_L2_THRESHOLD,
CROSS_LINK_CAP, CROSS_LINK_DEBOUNCE_SECS, LOREDOCS_DEFAULT_ROOT,
and LOREDOCS_DB_FILENAME) are vendored copies of the definitions in
ron_skills/loredocs/loredocs/storage.py. The source of truth for each
fact is the loredocs definition; this vendored copy is *checked*, not
trusted: tests/test_loredocs_bridge.py::TestConstantSync imports the
real loredocs.storage (when importable in the monorepo test
environment) and asserts equality -- error, not skip, when loredocs is
not importable. This mirrors the trust_framing.py vendored-copy
convention (check_trust_framing_sync.py).
"""

from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Vendored constants -- single source of truth: ron_skills/loredocs/loredocs/storage.py
# Checked by tests/test_loredocs_bridge.py::TestConstantSync (drift rule 1).
# ---------------------------------------------------------------------------

CROSS_LINK_SCHEMA_VERSION = 1
REQUIRED_CROSS_LINK_SCHEMA_VERSION = 1
CROSS_LINK_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
CROSS_LINK_EMBEDDING_DIM = 384
CROSS_LINK_L2_THRESHOLD = 0.6  # L2-normalized distance ceiling (cosine 0.80 ~ dist 0.632)
CROSS_LINK_CAP = 5               # max cross-product links per session/doc
CROSS_LINK_DEBOUNCE_SECS = 600   # 10-minute per-entity debounce
LIFETIME_AUTO_LINK_CAP = 500     # max total auto session links per doc (both directions)

# SH-106620: vendored copy of the document-endpoint auto-link rule from
# loredocs.storage (_DOC_AUTO_LINK_WHERE_SQL / _DOC_AUTO_LINK_RANK_SQL). A
# doc's auto session links are the rows where it is the loredocs endpoint in
# EITHER direction; this writer (loreconvo->loredocs) is the dominant one and
# must honour the same per-doc cap or a trimmed store refills. Checked, not
# trusted: TestConstantSync asserts byte equality with loredocs.storage.
DOC_AUTO_LINK_WHERE_SQL = (
    "link_type = 'auto' AND ("
    "(source_product = 'loredocs' AND source_id = ?) OR "
    "(target_product = 'loredocs' AND target_id = ?))"
)
DOC_AUTO_LINK_RANK_SQL = (
    "similarity_score ASC, created_at ASC, "
    "CASE WHEN source_product = 'loreconvo' THEN source_id ELSE target_id END ASC"
)

# SH-106805: vendored copy of loredocs.storage._CROSS_LINK_PAIR_WHERE_SQL. One
# (session, doc) pair is one link whichever way the row points; LoreDocs writes
# its auto links loredocs->loreconvo, this bridge writes loreconvo->loredocs, so
# a writer that matches only its own direction lands a second row for the same
# pair. Params: the (source_product, source_id, target_product, target_id)
# tuple twice. Checked, not trusted: TestConstantSync asserts byte equality.
CROSS_LINK_PAIR_WHERE_SQL = (
    "(source_product = ? AND source_id = ? AND target_product = ? AND target_id = ?)"
    " OR "
    "(target_product = ? AND target_id = ? AND source_product = ? AND source_id = ?)"
)

LOREDOCS_DEFAULT_ROOT = Path.home() / ".loredocs"
LOREDOCS_DB_FILENAME = "loredocs.db"
LOREDOCS_LANCE_DIRNAME = "docs.lance"

CROSS_PRODUCT_EXPECTED_COLUMNS = (
    "id", "source_product", "source_id", "target_product", "target_id",
    "similarity_score", "embedding_model", "embedding_dim",
    "link_type", "tier_required", "created_at",
)

# ---------------------------------------------------------------------------
# Exceptions -- distinguishable failure branches (SH-100670 Part B)
# ---------------------------------------------------------------------------

class LoreDocsAccessError(Exception):
    """LoreDocs appears installed (env-var override set) but its DB is
    invalid or unreadable.  Callers should report ``LoreDocs installed but
    unreachable: <detail>``."""


class LoreDocsSchemaError(Exception):
    """LoreDocs database exists but the cross_product_links table is missing
    or has the wrong shape (schema too old or corrupted)."""


# ---------------------------------------------------------------------------
# DB discovery -- mirrors loredocs.storage.discover_product_db
# ---------------------------------------------------------------------------

def discover_loredocs_db() -> Optional[Path]:
    """Return the LoreDocs DB path or None if not installed.

    Respects ``LOREDOCS_DB_PATH`` env override (validated the same way
    loredocs.storage.discover_product_db validates overrides: must be
    under $HOME, end in .db, exist, and be readable SQLite).

    Raises:
        LoreDocsAccessError: env override is set but invalid/unreadable.
    """
    env_override = os.environ.get("LOREDOCS_DB_PATH")
    if env_override:
        p = Path(env_override)
        home = Path.home()
        try:
            p.resolve().relative_to(home.resolve())
        except ValueError:
            raise LoreDocsAccessError(
                f"LOREDOCS_DB_PATH={env_override!r} is outside "
                f"$HOME ({home}) -- refusing to open it"
            )
        if p.suffix != ".db":
            raise LoreDocsAccessError(
                f"LOREDOCS_DB_PATH={env_override!r} does not end in "
                f".db -- check the path"
            )
        if not p.exists():
            raise LoreDocsAccessError(
                f"LOREDOCS_DB_PATH={env_override!r} set but file does "
                f"not exist. Check LoreDocs installation or unset "
                f"LOREDOCS_DB_PATH."
            )
        # Validate it is a readable SQLite file
        try:
            c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
            c.execute("SELECT 1")
            c.close()
        except Exception as exc:
            raise LoreDocsAccessError(
                f"LOREDOCS_DB_PATH={env_override!r} is not a readable "
                f"SQLite file: {exc}"
            )
        return p

    default = Path.home() / LOREDOCS_DEFAULT_ROOT.name / LOREDOCS_DB_FILENAME
    if default.exists():
        log.debug("discover_loredocs_db: found at default path")
        return default
    log.debug("discover_loredocs_db: LoreDocs not installed (default path absent)")
    return None


# ---------------------------------------------------------------------------
# Connection helpers -- mirror VaultStorage._db() and LoreDocs-reverse write precedent
# ---------------------------------------------------------------------------

@contextmanager
def _connect_readonly(db_path: Path):
    """Open a read-only LoreDocs connection with 5s busy_timeout."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def _connect_readwrite(db_path: Path):
    """Open a read-write LoreDocs connection mirroring VaultStorage._db().

    Sets busy_timeout=5000, foreign_keys=ON, row_factory=Row.
    Commits on success, rolls back on exception.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA secure_delete=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schema verification
# ---------------------------------------------------------------------------

def _verify_schema(conn: sqlite3.Connection) -> None:
    """Raise LoreDocsSchemaError if cross_product_links table is missing
    or doesn't have the expected columns."""
    table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name='cross_product_links'"
    ).fetchone()
    if not table:
        raise LoreDocsSchemaError(
            "cross_product_links table missing "
            "(LoreDocs schema too old; upgrade LoreDocs)"
        )
    actual_cols = {
        row[1] for row in conn.execute("PRAGMA table_info(cross_product_links)")
    }
    missing = [c for c in CROSS_PRODUCT_EXPECTED_COLUMNS if c not in actual_cols]
    if missing:
        raise LoreDocsSchemaError(
            f"cross_product_links missing columns: {', '.join(missing)} "
            f"(LoreDocs schema too old; upgrade LoreDocs)"
        )


# ---------------------------------------------------------------------------
# Read cross-product links -- mirrors VaultStorage.get_cross_product_links
# ---------------------------------------------------------------------------

def get_cross_product_links(
    db_path: Path,
    *,
    source_product: str = "loreconvo",
    source_id: str,
    current_embedding_model: str = CROSS_LINK_EMBEDDING_MODEL,
    limit: int = 5,
    is_pro: bool = False,
) -> Dict[str, Any]:
    """Return cross-product links for a source entity (bidirectional).

    Matches links where the entity is the stored source OR target, so links
    written by LoreDocs (cross_link_doc) are visible from the session side.

    Filters stale-model links (marks them is_stale=True, still returned so
    callers can surface an upgrade message). Manual links bypass model check.

    Returns dict with:
      schema_version, cross_product_available, tier_gate, links

    Raises:
        LoreDocsSchemaError: table missing or wrong shape.
    """
    if not is_pro:
        return {
            "schema_version": CROSS_LINK_SCHEMA_VERSION,
            "cross_product_available": True,
            "tier_gate": "pro_required",
            "message": "Cross-product linking requires Pro tier.",
            "links": [],
        }

    with _connect_readonly(db_path) as conn:
        _verify_schema(conn)
        rows = conn.execute(
            """SELECT
                 target_product, target_id, similarity_score,
                 embedding_model, embedding_dim, link_type, created_at
               FROM (
                 SELECT target_product, target_id, similarity_score,
                        embedding_model, embedding_dim, link_type, created_at
                 FROM cross_product_links
                 WHERE source_product = ? AND source_id = ?
                 UNION ALL
                 SELECT source_product AS target_product, source_id AS target_id,
                        similarity_score, embedding_model, embedding_dim, link_type, created_at
                 FROM cross_product_links
                 WHERE target_product = ? AND target_id = ?
               ) AS combined
               ORDER BY
                 CASE link_type WHEN 'manual' THEN 0 ELSE 1 END,
                 CASE WHEN embedding_model = ? THEN 0 ELSE 1 END,
                 similarity_score DESC
               LIMIT ?""",
            (source_product, source_id, source_product, source_id,
             current_embedding_model, limit),
        ).fetchall()

    seen: set = set()
    links: List[Dict[str, Any]] = []
    for row in rows:
        link_key = (row["target_product"], row["target_id"])
        if link_key in seen:
            continue
        seen.add(link_key)
        is_stale = (
            row["link_type"] != "manual"
            and row["embedding_model"] != current_embedding_model
        )
        entry: Dict[str, Any] = {
            "target_product": row["target_product"],
            "target_id": row["target_id"],
            "similarity_score": row["similarity_score"],
            "link_type": row["link_type"],
            "created_at": row["created_at"],
            "is_stale": is_stale,
        }
        if is_stale:
            entry["upgrade_message"] = (
                "This link was created with a different embedding model. "
                "Re-index both products to refresh cross-product links."
            )
        links.append(entry)

    return {
        "schema_version": CROSS_LINK_SCHEMA_VERSION,
        "cross_product_available": True,
        "tier_gate": "satisfied",
        "links": links,
    }


# ---------------------------------------------------------------------------
# Write a cross-product link -- mirrors VaultStorage._write_cross_product_link
# ---------------------------------------------------------------------------

def write_cross_product_link(
    conn: sqlite3.Connection,
    *,
    source_product: str,
    source_id: str,
    target_product: str,
    target_id: str,
    similarity_score: Optional[float] = None,
    embedding_model: str = "manual",
    embedding_dim: int = 0,
    link_type: str = "auto",
    tier_required: str = "pro",
) -> str:
    """Write a single cross-product link. Mirrors VaultStorage._write_cross_product_link.

    Manual links are always free-tier accessible (tier_required='free').
    If a manual link is requested and an auto link already exists for this pair,
    the auto link is upgraded to manual. The pair is matched in EITHER direction
    (SH-106805): a loredocs->loreconvo auto row written by LoreDocs satisfies a
    loreconvo->loredocs manual request and is upgraded in place, so one pair
    never holds two rows.

    Returns:
        str: "created" (new row inserted), "upgraded_from_auto" (auto upgraded to manual),
             "already_manual" (already exists as manual), "noop_auto" (auto link, no change)
    """
    if link_type == "manual":
        tier_required = "free"

    pair_params = (source_product, source_id, target_product, target_id) * 2
    row = conn.execute(
        f"""SELECT id, link_type FROM cross_product_links
            WHERE {CROSS_LINK_PAIR_WHERE_SQL}""",
        pair_params,
    ).fetchone()

    if row:
        existing_link_type = row["link_type"]
        if link_type == "manual" and existing_link_type == "auto":
            conn.execute(
                """UPDATE cross_product_links
                   SET link_type = ?, tier_required = ?,
                       similarity_score = ?, embedding_model = ?,
                       embedding_dim = ?
                   WHERE id = ?""",
                (link_type, tier_required, similarity_score, embedding_model,
                 embedding_dim, row["id"]),
            )
            return "upgraded_from_auto"
        elif link_type == "manual" and existing_link_type == "manual":
            return "already_manual"
        else:
            return "noop_auto"
    else:
        conn.execute(
            """INSERT INTO cross_product_links
               (source_product, source_id, target_product, target_id,
                similarity_score, embedding_model, embedding_dim,
                link_type, tier_required)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                source_product, source_id, target_product, target_id,
                similarity_score, embedding_model, embedding_dim,
                link_type, tier_required,
            ),
        )
        return "created"


# ---------------------------------------------------------------------------
# Per-document auto-link cap -- mirrors loredocs.storage.count_doc_auto_links
# and doc_auto_links_lowest_first (SH-106620)
# ---------------------------------------------------------------------------

def count_doc_auto_links(conn: sqlite3.Connection, doc_id: str) -> int:
    """Number of auto session links on ``doc_id``, both directions."""
    return conn.execute(
        f"SELECT COUNT(*) FROM cross_product_links WHERE {DOC_AUTO_LINK_WHERE_SQL}",
        (doc_id, doc_id),
    ).fetchone()[0]


def doc_auto_links_lowest_first(
    conn: sqlite3.Connection, doc_id: str, limit: Optional[int] = None
) -> List[sqlite3.Row]:
    """``doc_id``'s auto session links (both directions) as rows of
    ``(id, similarity_score)``, lowest similarity first."""
    sql = (
        f"SELECT id, similarity_score FROM cross_product_links "
        f"WHERE {DOC_AUTO_LINK_WHERE_SQL} ORDER BY {DOC_AUTO_LINK_RANK_SQL}"
    )
    params: tuple = (doc_id, doc_id)
    if limit is not None:
        sql += " LIMIT ?"
        params = params + (limit,)
    return conn.execute(sql, params).fetchall()


# ---------------------------------------------------------------------------
# Manual link write -- mirrors VaultStorage.link_session_to_doc
# ---------------------------------------------------------------------------

def link_session_to_doc(
    db_path: Path,
    *,
    session_id: str,
    doc_id: str,
    vault_id: str,
    link_type: str = "manual",
    similarity_score: Optional[float] = None,
    is_pro: bool = False,
) -> Dict[str, Any]:
    """Write a manual cross-product link from a LoreConvo session to a LoreDocs doc.

    Checks vault opt-out, doc existence, and vault existence.
    Manual links use embedding_model='manual', dim=0, tier_required='free'
    (manual links are free-tier accessible per architecture decision).

    Returns dict with ok, reason (on failure), session_id, doc_id.

    Raises:
        LoreDocsSchemaError: cross_product_links table missing or wrong shape.
    """
    # Manual links allowed for all tiers per architecture decision.
    # is_pro only gates auto-links; manual links pass through.

    with _connect_readwrite(db_path) as conn:
        _verify_schema(conn)

        vault_row = conn.execute(
            "SELECT cross_link_opt_out FROM vaults WHERE id = ?", (vault_id,)
        ).fetchone()
        if not vault_row:
            return {"ok": False, "reason": "vault not found"}
        if vault_row["cross_link_opt_out"]:
            return {"ok": False, "reason": "vault has cross-linking disabled"}

        doc_row = conn.execute(
            "SELECT 1 FROM documents WHERE id = ? AND deleted = 0", (doc_id,)
        ).fetchone()
        if not doc_row:
            return {"ok": False, "reason": "document not found"}

        link_status = write_cross_product_link(
            conn,
            source_product="loreconvo",
            source_id=session_id,
            target_product="loredocs",
            target_id=doc_id,
            similarity_score=similarity_score,
            embedding_model="manual",
            embedding_dim=0,
            link_type="manual",
            tier_required="free",
        )

    return {
        "ok": True,
        "session_id": session_id,
        "doc_id": doc_id,
        "link_status": link_status,
    }


# ---------------------------------------------------------------------------
# Lance DB path discovery -- mirrors loredocs.semantic_search.get_lance_db_path
# ---------------------------------------------------------------------------

def get_lancedb_path(db_path: Path) -> Optional[Path]:
    """Return the docs.lance/ directory for this LoreDocs install, or None.

    Used by cross_link_session to locate the LoreDocs Lance index for
    cross-product similarity queries without importing loredocs.
    """
    lance_dir = db_path.parent / LOREDOCS_LANCE_DIRNAME
    return lance_dir if lance_dir.exists() else None