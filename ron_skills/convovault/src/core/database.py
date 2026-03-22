"""SQLite database operations with FTS5 search."""

import json
import sqlite3
from datetime import datetime, timedelta
from typing import List, Optional

from .config import Config
from .models import (
    PersonaTag, Project, SearchResult, Session, SessionLink, SkillUsage
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    surface         TEXT NOT NULL,
    project         TEXT,
    start_date      TEXT NOT NULL,
    end_date        TEXT,
    summary         TEXT,
    decisions       TEXT,
    artifacts       TEXT,
    open_questions  TEXT,
    tags            TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS session_skills (
    session_id       TEXT NOT NULL REFERENCES sessions(id),
    skill_name       TEXT NOT NULL,
    skill_source     TEXT,
    invocation_count INTEGER DEFAULT 1,
    PRIMARY KEY (session_id, skill_name)
);

CREATE TABLE IF NOT EXISTS projects (
    name            TEXT PRIMARY KEY,
    description     TEXT,
    expected_skills TEXT,
    default_persona TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS persona_sessions (
    persona_name    TEXT NOT NULL,
    session_id      TEXT NOT NULL REFERENCES sessions(id),
    relevance_note  TEXT,
    PRIMARY KEY (persona_name, session_id)
);

CREATE TABLE IF NOT EXISTS session_links (
    from_session_id TEXT NOT NULL REFERENCES sessions(id),
    to_session_id   TEXT NOT NULL REFERENCES sessions(id),
    link_type       TEXT DEFAULT 'continues',
    PRIMARY KEY (from_session_id, to_session_id)
);
"""

FTS_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5(
    title, summary, decisions, content=sessions, content_rowid=rowid
);
"""

FTS_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS sessions_ai AFTER INSERT ON sessions BEGIN
    INSERT INTO sessions_fts(rowid, title, summary, decisions)
    VALUES (new.rowid, new.title, new.summary, new.decisions);
END;

CREATE TRIGGER IF NOT EXISTS sessions_au AFTER UPDATE ON sessions BEGIN
    UPDATE sessions_fts SET title = new.title, summary = new.summary,
        decisions = new.decisions WHERE rowid = old.rowid;
END;

CREATE TRIGGER IF NOT EXISTS sessions_ad AFTER DELETE ON sessions BEGIN
    DELETE FROM sessions_fts WHERE rowid = old.rowid;
END;
"""


class SessionDatabase:
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.config.ensure_db_dir()
        self.conn = sqlite3.connect(self.config.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript(SCHEMA_SQL)
        self.conn.executescript(FTS_SQL)
        self.conn.executescript(FTS_TRIGGERS)
        self.conn.commit()

    def close(self):
        self.conn.close()

    # -- Session CRUD --

    def save_session(self, session: Session) -> str:
        self.conn.execute(
            """INSERT OR REPLACE INTO sessions
               (id, title, surface, project, start_date, end_date, summary,
                decisions, artifacts, open_questions, tags, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session.id, session.title, session.surface, session.project,
                session.start_date, session.end_date, session.summary,
                json.dumps(session.decisions), json.dumps(session.artifacts),
                json.dumps(session.open_questions), json.dumps(session.tags),
                session.created_at
            )
        )
        for skill_name in session.skills_used:
            self.conn.execute(
                """INSERT OR REPLACE INTO session_skills
                   (session_id, skill_name, invocation_count)
                   VALUES (?, ?, 1)""",
                (session.id, skill_name)
            )
        self.conn.commit()
        return session.id

    def get_session(self, session_id: str) -> Optional[Session]:
        row = self.conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if not row:
            return None
        session = self._row_to_session(row)
        skills = self.conn.execute(
            "SELECT skill_name FROM session_skills WHERE session_id = ?",
            (session_id,)
        ).fetchall()
        session.skills_used = [s["skill_name"] for s in skills]
        return session

    def get_recent_sessions(
        self, limit: int = 10, days_back: int = 30,
        project: Optional[str] = None, skill: Optional[str] = None
    ) -> List[Session]:
        cutoff = (datetime.now() - timedelta(days=days_back)).isoformat()
        query = "SELECT * FROM sessions WHERE start_date >= ?"
        params = [cutoff]

        if project:
            query += " AND project = ?"
            params.append(project)

        if skill:
            query += " AND id IN (SELECT session_id FROM session_skills WHERE skill_name = ?)"
            params.append(skill)

        query += " ORDER BY start_date DESC LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(query, params).fetchall()
        return [self._row_to_session(r) for r in rows]

    def search_sessions(
        self, query: str, persona: Optional[str] = None,
        tags: Optional[List[str]] = None, skills: Optional[List[str]] = None,
        project: Optional[str] = None, limit: int = 10
    ) -> List[SearchResult]:
        fts_query = query.replace('"', '""')
        sql = """
            SELECT s.*, sessions_fts.rank
            FROM sessions s
            JOIN sessions_fts ON s.rowid = sessions_fts.rowid
            WHERE sessions_fts MATCH ?
        """
        params = [fts_query]

        if persona:
            sql += " AND s.id IN (SELECT session_id FROM persona_sessions WHERE persona_name LIKE ?)"
            params.append(persona + "%")

        if project:
            sql += " AND s.project = ?"
            params.append(project)

        if skills:
            placeholders = ",".join("?" * len(skills))
            sql += f" AND s.id IN (SELECT session_id FROM session_skills WHERE skill_name IN ({placeholders}))"
            params.extend(skills)

        sql += " ORDER BY sessions_fts.rank LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(sql, params).fetchall()
        results = []
        for row in rows:
            session = self._row_to_session(row)
            results.append(SearchResult(
                session=session,
                match_score=abs(row["rank"]) if row["rank"] else 0.0
            ))

        if tags:
            results = [
                r for r in results
                if any(t in r.session.tags for t in tags)
            ]

        return results

    def get_context_for(self, topic: str, max_results: int = 5) -> List[SearchResult]:
        return self.search_sessions(query=topic, limit=max_results)

    def get_skill_history(
        self, skill_name: str, days_back: int = 90
    ) -> List[Session]:
        cutoff = (datetime.now() - timedelta(days=days_back)).isoformat()
        rows = self.conn.execute(
            """SELECT s.* FROM sessions s
               JOIN session_skills sk ON s.id = sk.session_id
               WHERE sk.skill_name = ? AND s.start_date >= ?
               ORDER BY s.start_date DESC""",
            (skill_name, cutoff)
        ).fetchall()
        return [self._row_to_session(r) for r in rows]

    # -- Persona operations --

    def tag_session(
        self, session_id: str, persona_name: str,
        relevance_note: Optional[str] = None
    ):
        self.conn.execute(
            """INSERT OR REPLACE INTO persona_sessions
               (persona_name, session_id, relevance_note)
               VALUES (?, ?, ?)""",
            (persona_name, session_id, relevance_note)
        )
        self.conn.commit()

    def get_persona_sessions(
        self, persona_name: str, limit: int = 20
    ) -> List[Session]:
        rows = self.conn.execute(
            """SELECT s.* FROM sessions s
               JOIN persona_sessions ps ON s.id = ps.session_id
               WHERE ps.persona_name LIKE ?
               ORDER BY s.start_date DESC LIMIT ?""",
            (persona_name + "%", limit)
        ).fetchall()
        return [self._row_to_session(r) for r in rows]

    # -- Session linking --

    def link_sessions(
        self, from_id: str, to_id: str, link_type: str = "continues"
    ):
        self.conn.execute(
            """INSERT OR REPLACE INTO session_links
               (from_session_id, to_session_id, link_type)
               VALUES (?, ?, ?)""",
            (from_id, to_id, link_type)
        )
        self.conn.commit()

    def get_session_chain(self, session_id: str) -> List[Session]:
        chain_ids = set()
        to_visit = [session_id]
        while to_visit:
            current = to_visit.pop(0)
            if current in chain_ids:
                continue
            chain_ids.add(current)
            links = self.conn.execute(
                """SELECT to_session_id FROM session_links WHERE from_session_id = ?
                   UNION
                   SELECT from_session_id FROM session_links WHERE to_session_id = ?""",
                (current, current)
            ).fetchall()
            for link in links:
                to_visit.append(link[0])

        sessions = []
        for sid in chain_ids:
            s = self.get_session(sid)
            if s:
                sessions.append(s)
        sessions.sort(key=lambda s: s.start_date)
        return sessions

    # -- Project operations --

    def create_project(
        self, name: str, description: str = "",
        expected_skills: Optional[List[str]] = None,
        default_persona: Optional[str] = None
    ):
        self.conn.execute(
            """INSERT OR REPLACE INTO projects
               (name, description, expected_skills, default_persona)
               VALUES (?, ?, ?, ?)""",
            (name, description, json.dumps(expected_skills or []), default_persona)
        )
        self.conn.commit()

    def get_project(self, project_name: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM projects WHERE name = ?", (project_name,)
        ).fetchone()
        if not row:
            return None

        sessions = self.get_recent_sessions(
            limit=20, days_back=365, project=project_name
        )

        skill_counts = {}
        for s in sessions:
            skill_rows = self.conn.execute(
                "SELECT skill_name, invocation_count FROM session_skills WHERE session_id = ?",
                (s.id,)
            ).fetchall()
            for sr in skill_rows:
                skill_counts[sr["skill_name"]] = skill_counts.get(sr["skill_name"], 0) + sr["invocation_count"]

        return {
            "name": row["name"],
            "description": row["description"],
            "expected_skills": json.loads(row["expected_skills"] or "[]"),
            "default_persona": row["default_persona"],
            "session_count": len(sessions),
            "recent_sessions": [
                {"id": s.id, "title": s.title, "date": s.start_date}
                for s in sessions[:10]
            ],
            "skill_usage": dict(sorted(skill_counts.items(), key=lambda x: -x[1]))
        }

    def list_projects(self) -> List[dict]:
        rows = self.conn.execute("SELECT * FROM projects ORDER BY name").fetchall()
        results = []
        for row in rows:
            count = self.conn.execute(
                "SELECT COUNT(*) as c FROM sessions WHERE project = ?",
                (row["name"],)
            ).fetchone()
            results.append({
                "name": row["name"],
                "description": row["description"],
                "session_count": count["c"]
            })
        return results

    # -- Helpers --

    def _row_to_session(self, row) -> Session:
        return Session(
            id=row["id"],
            title=row["title"],
            surface=row["surface"],
            project=row["project"],
            start_date=row["start_date"],
            end_date=row["end_date"],
            summary=row["summary"] or "",
            decisions=json.loads(row["decisions"] or "[]"),
            artifacts=json.loads(row["artifacts"] or "[]"),
            open_questions=json.loads(row["open_questions"] or "[]"),
            tags=json.loads(row["tags"] or "[]"),
            created_at=row["created_at"] or ""
        )

    def session_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) as c FROM sessions").fetchone()
        return row["c"]
