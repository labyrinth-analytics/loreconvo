"""
Pipeline helpers for the Scout -> Gina -> Ron opportunity workflow.

Provides read/write access to the opportunity pipeline stored in LoreConvo's
sessions.db. Pipeline items are stored as sessions with surface='pipeline'.

Status lifecycle:
    scouted -> approved-for-review -> architecture-proposed -> approved -> in-progress -> completed
    scouted -> archived (Debbie skips it)
    architecture-proposed -> rejected (with disposition: rearchitect or archive)

Usage from any scheduled task or Cowork session:
    import sys
    sys.path.insert(0, os.path.expanduser('~/.loreconvo'))
    from pipeline_helpers import PipelineDB

    db = PipelineDB()
    db.add_opportunity('Smart SQL Server MCP', 'Schema-aware MCP...', ['mcp', 'sql-server'])
    items = db.get_by_status('approved-for-review')
    db.update_status('OPP-001', 'architecture-proposed')
    db.close()

In Cowork VMs (scheduled tasks), the database may be mounted at a different path.
PipelineDB auto-discovers it by searching common mount points. You can also pass
an explicit path: PipelineDB(db_path='/sessions/.../mnt/.loreconvo/sessions.db')
"""

import sqlite3
import os
import glob
import json
from datetime import datetime


def find_db_path():
    """Auto-discover the LoreConvo sessions.db path.

    Checks in order:
    1. Native host path: ~/.loreconvo/sessions.db (works on Debbie's Mac directly)
    2. Cowork VM mounted paths: /sessions/*/mnt/.loreconvo/sessions.db
    3. Cowork VM mounted paths: /sessions/*/mnt/sessions.db (if .loreconvo is the mounted dir)
    """
    # 1. Native path (works on host, not in VM)
    native = os.path.expanduser('~/.loreconvo/sessions.db')
    if os.path.exists(native):
        return native

    # 2. Mounted as subdirectory (e.g., workspace has .loreconvo inside it)
    for path in glob.glob('/sessions/*/mnt/.loreconvo/sessions.db'):
        return path

    # 3. Mounted directly (e.g., .loreconvo IS the mounted folder)
    for path in glob.glob('/sessions/*/mnt/sessions.db'):
        return path

    # 4. Search more broadly
    for path in glob.glob('/sessions/*/mnt/**/sessions.db', recursive=True):
        # Verify it has a pipeline surface
        try:
            conn = sqlite3.connect(path)
            cursor = conn.execute("SELECT COUNT(*) FROM sessions WHERE surface='pipeline'")
            count = cursor.fetchone()[0]
            conn.close()
            if count >= 0:  # Valid LoreConvo DB
                return path
        except Exception:
            continue

    return native  # Fallback -- will fail with a clear error


DB_PATH = find_db_path()

# Valid status transitions
VALID_STATUSES = [
    'scouted',
    'approved-for-review',
    'architecture-proposed',
    'approved',
    'in-progress',
    'completed',
    'rejected',
    'archived',
]

# Fibonacci effort scale
EFFORT_SCALE = {
    1: 'afternoon',
    2: 'half-day',
    3: 'weekend',
    5: 'several days',
    8: 'full week',
    13: 'multi-week',
}


class PipelineDB:
    """Read/write interface to the opportunity pipeline in LoreConvo."""

    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # -------------------------------------------------------------------------
    # Read operations
    # -------------------------------------------------------------------------

    def get_next_opp_id(self):
        """Get the next OPP-XXX ID by finding the current max."""
        cursor = self.conn.execute(
            "SELECT id FROM sessions WHERE surface = 'pipeline' ORDER BY id DESC LIMIT 1"
        )
        row = cursor.fetchone()
        if row is None:
            return 'OPP-001'
        # Parse OPP-NNN
        current_num = int(row['id'].split('-')[1])
        return f'OPP-{current_num + 1:03d}'

    def get_by_status(self, status):
        """Get all pipeline items with the given status, ordered by priority then date."""
        cursor = self.conn.execute(
            "SELECT * FROM sessions WHERE surface = 'pipeline' AND tags LIKE ?",
            (f'%"status:{status}"%',)
        )
        rows = [dict(r) for r in cursor.fetchall()]
        # Parse tags and sort by priority then scouted date
        for row in rows:
            row['_tags'] = json.loads(row['tags']) if row['tags'] else []
            row['_status'] = self._extract_tag(row['_tags'], 'status')
            row['_priority'] = self._extract_tag(row['_tags'], 'priority')
            row['_effort'] = self._extract_tag(row['_tags'], 'effort')
        # Sort: P1 before P2 before P3, then by start_date (oldest first)
        rows.sort(key=lambda r: (
            r['_priority'] or 'P99',
            r['start_date'] or '9999'
        ))
        return rows

    def get_all_pipeline(self):
        """Get all pipeline items regardless of status."""
        cursor = self.conn.execute(
            "SELECT * FROM sessions WHERE surface = 'pipeline' ORDER BY id"
        )
        rows = [dict(r) for r in cursor.fetchall()]
        for row in rows:
            row['_tags'] = json.loads(row['tags']) if row['tags'] else []
            row['_status'] = self._extract_tag(row['_tags'], 'status')
            row['_priority'] = self._extract_tag(row['_tags'], 'priority')
            row['_effort'] = self._extract_tag(row['_tags'], 'effort')
        return rows

    def get_opportunity(self, opp_id):
        """Get a single pipeline item by ID."""
        cursor = self.conn.execute(
            "SELECT * FROM sessions WHERE id = ? AND surface = 'pipeline'",
            (opp_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        result = dict(row)
        result['_tags'] = json.loads(result['tags']) if result['tags'] else []
        result['_status'] = self._extract_tag(result['_tags'], 'status')
        result['_priority'] = self._extract_tag(result['_tags'], 'priority')
        result['_effort'] = self._extract_tag(result['_tags'], 'effort')
        return result

    def search(self, query):
        """Full-text search across pipeline items."""
        cursor = self.conn.execute(
            """SELECT s.* FROM sessions s
               JOIN sessions_fts fts ON s.rowid = fts.rowid
               WHERE fts.sessions_fts MATCH ? AND s.surface = 'pipeline'""",
            (query,)
        )
        return [dict(r) for r in cursor.fetchall()]

    # -------------------------------------------------------------------------
    # Write operations
    # -------------------------------------------------------------------------

    def add_opportunity(self, title, summary, extra_tags=None, scout_run_date=None):
        """Add a new scouted opportunity. Returns the new OPP-ID."""
        opp_id = self.get_next_opp_id()
        run_date = scout_run_date or datetime.now().strftime('%Y-%m-%d')

        tags = [
            f'status:scouted',
            f'scout-run:{run_date}',
        ]
        if extra_tags:
            tags.extend(extra_tags)

        self.conn.execute(
            """INSERT INTO sessions (id, title, surface, project, start_date, summary, tags, created_at)
               VALUES (?, ?, 'pipeline', 'side_hustle', ?, ?, ?, datetime('now'))""",
            (opp_id, title, run_date, summary, json.dumps(tags))
        )
        # Update FTS index
        self._update_fts(opp_id, title, summary, '')
        self.conn.commit()
        return opp_id

    def update_status(self, opp_id, new_status):
        """Change the status tag on a pipeline item."""
        if new_status not in VALID_STATUSES:
            raise ValueError(f'Invalid status: {new_status}. Must be one of {VALID_STATUSES}')

        item = self.get_opportunity(opp_id)
        if item is None:
            raise ValueError(f'Opportunity {opp_id} not found')

        tags = item['_tags']
        # Remove old status tag, add new one
        tags = [t for t in tags if not t.startswith('status:')]
        tags.insert(0, f'status:{new_status}')

        self.conn.execute(
            "UPDATE sessions SET tags = ? WHERE id = ?",
            (json.dumps(tags), opp_id)
        )
        self.conn.commit()

    def set_priority(self, opp_id, priority):
        """Set priority (P1, P2, P3, etc.) on a pipeline item."""
        item = self.get_opportunity(opp_id)
        if item is None:
            raise ValueError(f'Opportunity {opp_id} not found')

        tags = item['_tags']
        tags = [t for t in tags if not t.startswith('priority:')]
        tags.append(f'priority:{priority}')

        self.conn.execute(
            "UPDATE sessions SET tags = ? WHERE id = ?",
            (json.dumps(tags), opp_id)
        )
        self.conn.commit()

    def set_effort(self, opp_id, effort):
        """Set Fibonacci effort estimate on a pipeline item."""
        if effort not in EFFORT_SCALE:
            raise ValueError(f'Invalid effort: {effort}. Must be one of {list(EFFORT_SCALE.keys())}')

        item = self.get_opportunity(opp_id)
        if item is None:
            raise ValueError(f'Opportunity {opp_id} not found')

        tags = item['_tags']
        tags = [t for t in tags if not t.startswith('effort:')]
        tags.append(f'effort:{effort}')

        self.conn.execute(
            "UPDATE sessions SET tags = ? WHERE id = ?",
            (json.dumps(tags), opp_id)
        )
        self.conn.commit()

    def set_architecture(self, opp_id, architecture_text):
        """Write Gina's architectural proposal into the decisions field and save as a markdown doc.

        Saves to: ~/Documents/Claude/Projects/Side Hustle/Architecture/OPP-XXX_Product_Name.md
        Also stores the proposal in the LoreConvo decisions column for agent access.
        """
        item = self.get_opportunity(opp_id)
        if item is None:
            raise ValueError(f'Opportunity {opp_id} not found')

        self.conn.execute(
            "UPDATE sessions SET decisions = ? WHERE id = ?",
            (architecture_text, opp_id)
        )
        # Update FTS
        self._update_fts(opp_id, item['title'], item['summary'], architecture_text)
        self.conn.commit()

        # Write architecture doc to Side Hustle project folder
        doc_path = self._write_architecture_doc(opp_id, item['title'], architecture_text, item)
        return doc_path

    def _write_architecture_doc(self, opp_id, title, architecture_text, item):
        """Write a standalone markdown architecture doc to the Side Hustle folder."""
        # Build a clean filename: OPP-001_Smart_SQL_Server_MCP.md
        safe_title = title.replace(' ', '_').replace('/', '_').replace('\\', '_')
        safe_title = ''.join(c for c in safe_title if c.isalnum() or c in ('_', '-'))
        filename = f'{opp_id}_{safe_title}.md'

        # Find the Architecture directory -- check common locations
        arch_dirs = [
            os.path.expanduser('~/Documents/Claude/Projects/Side Hustle/Architecture'),
        ]
        # Also check Cowork VM mount points
        for path in glob.glob('/sessions/*/mnt'):
            candidate = os.path.join(path, 'Architecture')
            if os.path.isdir(candidate):
                arch_dirs.insert(0, candidate)
            # Check if Side Hustle project is mounted with its full structure
            for sub in glob.glob(os.path.join(path, '**/Architecture'), recursive=True):
                if 'Side Hustle' in sub or 'side_hustle' in sub:
                    arch_dirs.insert(0, sub)

        # Use first existing dir, or create the native one
        arch_dir = None
        for d in arch_dirs:
            if os.path.isdir(d):
                arch_dir = d
                break
        if arch_dir is None:
            arch_dir = arch_dirs[0]  # native path
            os.makedirs(arch_dir, exist_ok=True)

        # Build the full document
        priority = self._extract_tag(item.get('_tags', []), 'priority') or '-'
        effort = self._extract_tag(item.get('_tags', []), 'effort') or '-'
        doc_lines = [
            f'# {opp_id}: {title}',
            '',
            f'**Priority:** {priority}',
            f'**Effort:** {effort}',
            f'**Status:** {self._extract_tag(item.get("_tags", []), "status") or "unknown"}',
            f'**Scouted:** {item.get("start_date", "unknown")}',
            '',
            '## Scout Summary',
            '',
            item.get('summary', '') or '(no summary)',
            '',
            '## Architectural Proposal',
            '',
            architecture_text,
        ]

        # Add dependencies if present
        deps = item.get('artifacts', '')
        if deps:
            doc_lines.extend(['', '## Dependencies', '', deps])

        # Add open questions if present
        questions = item.get('open_questions', '')
        if questions:
            doc_lines.extend(['', '## Open Questions', '', questions])

        filepath = os.path.join(arch_dir, filename)
        with open(filepath, 'w') as f:
            f.write('\n'.join(doc_lines) + '\n')

        return filepath

    def set_dependencies(self, opp_id, dependencies_text):
        """Set dependency notes on a pipeline item."""
        item = self.get_opportunity(opp_id)
        if item is None:
            raise ValueError(f'Opportunity {opp_id} not found')

        self.conn.execute(
            "UPDATE sessions SET artifacts = ? WHERE id = ?",
            (dependencies_text, opp_id)
        )
        self.conn.commit()

    def set_open_questions(self, opp_id, questions_text):
        """Set open questions on a pipeline item."""
        self.conn.execute(
            "UPDATE sessions SET open_questions = ? WHERE id = ?",
            (questions_text, opp_id)
        )
        self.conn.commit()

    def reject(self, opp_id, reason, disposition='archive'):
        """Reject a pipeline item. Disposition is 'archive' or 'rearchitect'."""
        if disposition not in ('archive', 'rearchitect'):
            raise ValueError(f'Invalid disposition: {disposition}')

        item = self.get_opportunity(opp_id)
        if item is None:
            raise ValueError(f'Opportunity {opp_id} not found')

        self.update_status(opp_id, 'rejected')

        # Reload after status update
        item = self.get_opportunity(opp_id)
        tags = item['_tags']
        tags = [t for t in tags if not t.startswith('disposition:')]
        tags.append(f'disposition:{disposition}')

        existing_decisions = item['decisions'] or ''
        rejection_note = f'\n\n--- REJECTED ({datetime.now().strftime("%Y-%m-%d")}) ---\nDisposition: {disposition}\nReason: {reason}'

        self.conn.execute(
            "UPDATE sessions SET tags = ?, decisions = ? WHERE id = ?",
            (json.dumps(tags), existing_decisions + rejection_note, opp_id)
        )
        self.conn.commit()

    def link_persona(self, opp_id, persona_name, note=None):
        """Link an agent persona (Scout, Gina, Ron) to a pipeline item."""
        self.conn.execute(
            """INSERT OR REPLACE INTO persona_sessions (persona_name, session_id, relevance_note)
               VALUES (?, ?, ?)""",
            (persona_name, opp_id, note)
        )
        self.conn.commit()

    def link_opportunities(self, from_opp, to_opp, link_type='depends-on'):
        """Link two pipeline items (e.g., OPP-005 depends on OPP-001)."""
        self.conn.execute(
            """INSERT OR REPLACE INTO session_links (from_session_id, to_session_id, link_type)
               VALUES (?, ?, ?)""",
            (from_opp, to_opp, link_type)
        )
        self.conn.commit()

    # -------------------------------------------------------------------------
    # Dashboard generation
    # -------------------------------------------------------------------------

    def generate_markdown_dashboard(self):
        """Generate a markdown pipeline dashboard from current DB state."""
        items = self.get_all_pipeline()
        active = [i for i in items if i['_status'] not in ('rejected', 'archived')]
        inactive = [i for i in items if i['_status'] in ('rejected', 'archived')]

        lines = ['# Opportunity Pipeline Dashboard', '']
        lines.append(f'> Auto-generated from LoreConvo on {datetime.now().strftime("%Y-%m-%d %H:%M")}')
        lines.append(f'> Database: ~/.loreconvo/sessions.db (surface=pipeline)')
        lines.append('')

        # Active pipeline table
        lines.append('## Active Pipeline')
        lines.append('')
        lines.append('| ID | Name | Status | Priority | Effort | Scouted | Summary |')
        lines.append('|---|---|---|---|---|---|---|')
        for item in active:
            priority = item['_priority'] or '-'
            effort = item['_effort'] or '-'
            summary = (item['summary'] or '')[:100]
            if len(item['summary'] or '') > 100:
                summary += '...'
            lines.append(f"| {item['id']} | {item['title']} | {item['_status']} | {priority} | {effort} | {item['start_date']} | {summary} |")

        lines.append('')

        # Rejection/archive log
        if inactive:
            lines.append('## Rejected/Archived')
            lines.append('')
            lines.append('| ID | Name | Disposition | Date |')
            lines.append('|---|---|---|---|')
            for item in inactive:
                disp = self._extract_tag(item['_tags'], 'disposition') or item['_status']
                lines.append(f"| {item['id']} | {item['title']} | {disp} | {item['start_date']} |")

        return '\n'.join(lines)

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _extract_tag(tags, prefix):
        """Extract value from a tag like 'status:scouted' -> 'scouted'."""
        for tag in tags:
            if tag.startswith(f'{prefix}:'):
                return tag.split(':', 1)[1]
        return None

    def _update_fts(self, opp_id, title, summary, decisions):
        """Update full-text search index for a pipeline item."""
        # Get rowid for this session
        cursor = self.conn.execute(
            "SELECT rowid FROM sessions WHERE id = ?", (opp_id,)
        )
        row = cursor.fetchone()
        if row:
            rowid = row[0]
            # Delete old FTS entry and insert new one
            self.conn.execute(
                "INSERT INTO sessions_fts(sessions_fts, rowid, title, summary, decisions) VALUES('delete', ?, ?, ?, ?)",
                (rowid, title or '', summary or '', decisions or '')
            )
            self.conn.execute(
                "INSERT INTO sessions_fts(rowid, title, summary, decisions) VALUES(?, ?, ?, ?)",
                (rowid, title or '', summary or '', decisions or '')
            )
