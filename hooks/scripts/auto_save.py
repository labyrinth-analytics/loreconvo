"""LoreConvo SessionEnd auto-save hook.

Receives session metadata via stdin JSON from Claude Code's SessionEnd hook.
Parses the transcript JSONL to extract a summary, then saves directly to SQLite.

Designed to run within the 3-5 second timeout window.
"""

import json
import os
import sys
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path


def get_db_path():
    """Get database path, matching core/config.py logic."""
    return os.environ.get("LORECONVO_DB", os.path.expanduser("~/.loreconvo/sessions.db"))


def parse_transcript(transcript_path):
    """Parse a Claude Code JSONL transcript into structured session data.

    Extracts: title (from first user message), surface, summary of key exchanges,
    decisions (lines starting with decision-like language), and artifacts.
    """
    if not transcript_path or not os.path.exists(transcript_path):
        return None

    messages = []
    try:
        with open(transcript_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    messages.append(entry)
                except json.JSONDecodeError:
                    continue
    except (IOError, PermissionError):
        return None

    if not messages:
        return None

    # Extract user and assistant messages
    user_messages = []
    assistant_messages = []
    tool_uses = []

    for msg in messages:
        # Real Claude Code transcripts wrap messages: {"type":"user", "message": {"role":..., "content":...}}
        inner = msg.get("message", msg)
        role = inner.get("role", "") if isinstance(inner, dict) else msg.get("role", "")
        content = inner.get("content", "") if isinstance(inner, dict) else msg.get("content", "")

        # Handle content that's a list of blocks
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        tool_uses.append(block.get("name", "unknown"))
                elif isinstance(block, str):
                    text_parts.append(block)
            content = " ".join(text_parts)

        if role == "user" and content:
            user_messages.append(content[:500])  # Truncate long messages
        elif role == "assistant" and content:
            assistant_messages.append(content[:500])

    if not user_messages:
        return None

    # Title: first user message, truncated
    first_msg = user_messages[0]
    title = first_msg[:80].replace("\n", " ").strip()
    if len(first_msg) > 80:
        title += "..."

    # Summary: combine first few exchanges
    summary_parts = []
    for i, msg in enumerate(user_messages[:3]):
        summary_parts.append(f"User: {msg[:200]}")
        if i < len(assistant_messages):
            summary_parts.append(f"Assistant: {assistant_messages[i][:200]}")
    summary = "\n".join(summary_parts)

    # Truncate summary to reasonable length
    if len(summary) > 2000:
        summary = summary[:2000] + "..."

    # Detect decisions (simple heuristic)
    decisions = []
    decision_keywords = ["decided", "agreed", "confirmed", "chose", "will use", "going with", "settled on"]
    for msg in assistant_messages:
        msg_lower = msg.lower()
        for keyword in decision_keywords:
            if keyword in msg_lower:
                # Extract the sentence containing the keyword
                for sentence in msg.split("."):
                    if keyword in sentence.lower():
                        clean = sentence.strip()
                        if clean and len(clean) > 10:
                            decisions.append(clean[:200])
                break

    # Detect artifacts (file paths, URLs)
    artifacts = []
    for msg in assistant_messages:
        # Look for file paths
        for word in msg.split():
            if "/" in word and ("." in word.split("/")[-1]) and len(word) > 5:
                clean = word.strip("(),\"'`")
                if clean not in artifacts and len(artifacts) < 10:
                    artifacts.append(clean)

    # Unique tools used
    unique_tools = list(set(tool_uses))[:20]

    return {
        "title": title,
        "summary": summary,
        "decisions": decisions[:10],
        "artifacts": artifacts[:10],
        "tools_used": unique_tools,
        "message_count": len(user_messages) + len(assistant_messages),
    }


def ensure_tables(conn):
    """Create tables if they don't exist (matches core/database.py schema)."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            surface TEXT NOT NULL,
            project TEXT,
            summary TEXT,
            decisions TEXT DEFAULT '[]',
            artifacts TEXT DEFAULT '[]',
            open_questions TEXT DEFAULT '[]',
            tags TEXT DEFAULT '[]',
            start_date TEXT,
            end_date TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS session_skills (
            session_id TEXT NOT NULL,
            skill_name TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id),
            UNIQUE(session_id, skill_name)
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5(
            title, summary, decisions, artifacts, open_questions,
            content='sessions', content_rowid='rowid'
        );
    """)


def save_to_db(db_path, session_id, parsed):
    """Save parsed session data directly to SQLite."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        ensure_tables(conn)

        # Use Claude's session_id as our primary key so dedup actually works.
        # Previous bug: generated a random UUID for id but checked WHERE id = session_id,
        # so the duplicate guard never matched anything.
        session_uuid = session_id

        # Check if session already exists (e.g., resumed session or duplicate hook fire)
        cursor = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_uuid,))
        if cursor.fetchone():
            # Already saved -- update instead of duplicate
            now = datetime.now().isoformat()
            conn.execute(
                """UPDATE sessions SET summary = ?, decisions = ?, artifacts = ?,
                   tags = ?, end_date = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    parsed["summary"],
                    json.dumps(parsed["decisions"]),
                    json.dumps(parsed["artifacts"]),
                    json.dumps(["auto-saved"]),
                    now,
                    now,
                    session_uuid,
                ),
            )
            conn.commit()
            return True  # Updated existing record

        now = datetime.now().isoformat()

        conn.execute(
            """INSERT INTO sessions (id, title, surface, summary, decisions, artifacts,
               open_questions, tags, start_date, end_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_uuid,
                parsed["title"],
                "code",
                parsed["summary"],
                json.dumps(parsed["decisions"]),
                json.dumps(parsed["artifacts"]),
                json.dumps([]),
                json.dumps(["auto-saved"]),
                now,
                now,
            ),
        )

        # Update FTS index
        try:
            conn.execute(
                """INSERT INTO sessions_fts(rowid, title, summary, decisions, artifacts, open_questions)
                   SELECT rowid, title, summary, decisions, artifacts, open_questions
                   FROM sessions WHERE id = ?""",
                (session_uuid,),
            )
        except sqlite3.OperationalError:
            pass  # FTS table might not exist in older DBs

        # Save skill/tool usage
        for tool in parsed.get("tools_used", []):
            try:
                conn.execute(
                    "INSERT INTO session_skills (session_id, skill_name) VALUES (?, ?)",
                    (session_uuid, tool),
                )
            except sqlite3.IntegrityError:
                pass

        conn.commit()
        return True
    except Exception as e:
        sys.stderr.write(f"LoreConvo auto-save DB error: {e}\n")
        return False
    finally:
        conn.close()


def main():
    """Main entry point for SessionEnd hook."""
    try:
        # Read hook input from stdin
        stdin_data = sys.stdin.read()
        if not stdin_data:
            sys.exit(0)

        hook_input = json.loads(stdin_data)
        session_id = hook_input.get("session_id", "unknown")
        transcript_path = hook_input.get("transcript_path", "")

        # Parse transcript
        parsed = parse_transcript(transcript_path)
        if not parsed:
            sys.exit(0)

        # Skip very short sessions (less than 2 messages)
        if parsed["message_count"] < 2:
            sys.exit(0)

        # Save to database
        db_path = get_db_path()
        saved = save_to_db(db_path, session_id, parsed)

        if saved:
            sys.stderr.write(f"LoreConvo: Auto-saved session '{parsed['title']}'\n")

    except json.JSONDecodeError:
        sys.exit(0)
    except Exception as e:
        sys.stderr.write(f"LoreConvo auto-save error: {e}\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
