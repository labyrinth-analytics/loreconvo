"""Tests for LoreConvo auto_save.py hook.

Added by Meg QA 2026-03-29. Covers:
- parse_transcript() - message parsing, Skill tool detection, artifact detection
- save_to_db() - insert and dedup (update) behavior
- Edge cases: empty transcript, None input, Skill with missing/None input
"""

import json
import os
import sqlite3
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'hooks', 'scripts'))

import auto_save


# ============================================================
# Helpers
# ============================================================

def write_jsonl_transcript(messages, path):
    """Write a list of message dicts to a JSONL file."""
    with open(path, 'w') as f:
        for msg in messages:
            f.write(json.dumps(msg) + '\n')


def simple_transcript(tmp_path, user_msgs=None, assistant_msgs=None):
    """Write a simple transcript file and return the path."""
    user_msgs = user_msgs or ['Hello, help me with something']
    assistant_msgs = assistant_msgs or ['Sure, I can help you with that.']
    messages = []
    for u, a in zip(user_msgs, assistant_msgs):
        messages.append({'role': 'user', 'content': u})
        messages.append({'role': 'assistant', 'content': a})
    path = str(tmp_path / 'transcript.jsonl')
    write_jsonl_transcript(messages, path)
    return path


# ============================================================
# parse_transcript tests
# ============================================================

class TestParseTranscript:
    def test_none_path_returns_none(self):
        result = auto_save.parse_transcript(None)
        assert result is None

    def test_nonexistent_path_returns_none(self):
        result = auto_save.parse_transcript('/does/not/exist.jsonl')
        assert result is None

    def test_empty_file_returns_none(self, tmp_path):
        path = str(tmp_path / 'empty.jsonl')
        open(path, 'w').close()
        result = auto_save.parse_transcript(path)
        assert result is None

    def test_basic_transcript_parsed(self, tmp_path):
        path = simple_transcript(tmp_path)
        result = auto_save.parse_transcript(path)
        assert result is not None
        assert result['title'] != ''
        assert result['message_count'] >= 2

    def test_title_truncated_at_80_chars(self, tmp_path):
        long_msg = 'A' * 200
        messages = [
            {'role': 'user', 'content': long_msg},
            {'role': 'assistant', 'content': 'OK'}
        ]
        path = str(tmp_path / 'transcript.jsonl')
        write_jsonl_transcript(messages, path)
        result = auto_save.parse_transcript(path)
        assert result is not None
        assert len(result['title']) <= 83  # 80 + '...'

    def test_skill_tool_use_detected(self, tmp_path):
        messages = [
            {'role': 'user', 'content': 'Make a presentation'},
            {'role': 'assistant', 'content': [
                {'type': 'tool_use', 'name': 'Skill', 'input': {'skill': 'pptx'}},
                {'type': 'text', 'text': 'Using the pptx skill for you.'}
            ]}
        ]
        path = str(tmp_path / 'transcript.jsonl')
        write_jsonl_transcript(messages, path)
        result = auto_save.parse_transcript(path)
        assert 'skill:pptx' in result['tools_used']

    def test_regular_tool_use_recorded_by_name(self, tmp_path):
        messages = [
            {'role': 'user', 'content': 'Read my file'},
            {'role': 'assistant', 'content': [
                {'type': 'tool_use', 'name': 'Read', 'input': {'file_path': '/tmp/test.py'}},
                {'type': 'text', 'text': 'File contents are...'}
            ]}
        ]
        path = str(tmp_path / 'transcript.jsonl')
        write_jsonl_transcript(messages, path)
        result = auto_save.parse_transcript(path)
        assert 'Read' in result['tools_used']

    def test_skill_with_no_skill_key_falls_back_to_Skill(self, tmp_path):
        """Skill tool_use with empty input dict should not crash and uses 'Skill' fallback."""
        messages = [
            {'role': 'user', 'content': 'Do something'},
            {'role': 'assistant', 'content': [
                {'type': 'tool_use', 'name': 'Skill', 'input': {}},
                {'type': 'text', 'text': 'Done.'}
            ]}
        ]
        path = str(tmp_path / 'transcript.jsonl')
        write_jsonl_transcript(messages, path)
        result = auto_save.parse_transcript(path)
        assert result is not None
        # Falls back to 'Skill' string when no skill name found
        assert 'Skill' in result['tools_used']

    def test_malformed_json_lines_skipped(self, tmp_path):
        path = str(tmp_path / 'transcript.jsonl')
        with open(path, 'w') as f:
            f.write('not json at all\n')
            f.write(json.dumps({'role': 'user', 'content': 'Valid message'}) + '\n')
            f.write(json.dumps({'role': 'assistant', 'content': 'Valid response'}) + '\n')
        result = auto_save.parse_transcript(path)
        assert result is not None

    def test_real_claude_code_format_parsed(self, tmp_path):
        """Parse the nested transcript format used by real Claude Code hooks."""
        messages = [
            {
                'type': 'user',
                'message': {'role': 'user', 'content': 'Help me build something'}
            },
            {
                'type': 'assistant',
                'message': {
                    'role': 'assistant',
                    'content': [
                        {'type': 'text', 'text': 'I will help you build it.'}
                    ]
                }
            },
        ]
        path = str(tmp_path / 'transcript.jsonl')
        write_jsonl_transcript(messages, path)
        result = auto_save.parse_transcript(path)
        assert result is not None
        assert 'Help me build something' in result['title']

    def test_decision_keywords_extracted(self, tmp_path):
        messages = [
            {'role': 'user', 'content': 'What database should I use?'},
            {'role': 'assistant', 'content': 'I decided to use SQLite. We agreed on this approach.'}
        ]
        path = str(tmp_path / 'transcript.jsonl')
        write_jsonl_transcript(messages, path)
        result = auto_save.parse_transcript(path)
        assert result is not None
        # At least one decision should be extracted
        assert len(result['decisions']) >= 1

    def test_file_path_artifact_detected(self, tmp_path):
        messages = [
            {'role': 'user', 'content': 'Create a file'},
            {'role': 'assistant', 'content': 'Created the file at /tmp/output/report.py for you.'}
        ]
        path = str(tmp_path / 'transcript.jsonl')
        write_jsonl_transcript(messages, path)
        result = auto_save.parse_transcript(path)
        assert result is not None
        # Should detect /tmp/output/report.py as an artifact
        assert any('report.py' in a for a in result['artifacts'])

    def test_summary_capped_at_2000_chars(self, tmp_path):
        long_msg = 'X' * 1500
        messages = [
            {'role': 'user', 'content': long_msg},
            {'role': 'assistant', 'content': long_msg},
            {'role': 'user', 'content': long_msg},
            {'role': 'assistant', 'content': long_msg},
        ]
        path = str(tmp_path / 'transcript.jsonl')
        write_jsonl_transcript(messages, path)
        result = auto_save.parse_transcript(path)
        assert result is not None
        assert len(result['summary']) <= 2003  # 2000 + '...'


# ============================================================
# save_to_db tests
# ============================================================

class TestSaveToDb:
    def _parsed(self):
        return {
            'title': 'Test Session',
            'summary': 'This is a summary.',
            'decisions': ['Decided to use SQLite'],
            'artifacts': ['/tmp/test.py'],
            'tools_used': ['Read', 'skill:pptx'],
            'message_count': 4,
        }

    def test_new_session_inserted(self, tmp_path):
        db_path = str(tmp_path / 'test.db')
        result = auto_save.save_to_db(db_path, 'test-session-id-001', self._parsed())
        assert result is True

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT * FROM sessions WHERE id = 'test-session-id-001'").fetchone()
        conn.close()
        assert row is not None

    def test_duplicate_session_id_updates_not_duplicates(self, tmp_path):
        db_path = str(tmp_path / 'test.db')
        session_id = 'duplicate-session-id-999'

        auto_save.save_to_db(db_path, session_id, self._parsed())
        # Second save with same id (simulate hook firing twice)
        parsed2 = self._parsed()
        parsed2['summary'] = 'Updated summary content'
        auto_save.save_to_db(db_path, session_id, parsed2)

        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT COUNT(*) FROM sessions WHERE id = ?", (session_id,)).fetchone()
        conn.close()
        assert rows[0] == 1  # Only one row, not two

    def test_skills_saved_to_session_skills_table(self, tmp_path):
        db_path = str(tmp_path / 'test.db')
        auto_save.save_to_db(db_path, 'skill-test-id', self._parsed())

        conn = sqlite3.connect(db_path)
        skills = conn.execute(
            "SELECT skill_name FROM session_skills WHERE session_id = 'skill-test-id'"
        ).fetchall()
        conn.close()
        skill_names = {r[0] for r in skills}
        assert 'Read' in skill_names
        assert 'skill:pptx' in skill_names

    def test_db_directory_created_if_missing(self, tmp_path):
        nested_path = str(tmp_path / 'a' / 'b' / 'c' / 'sessions.db')
        result = auto_save.save_to_db(nested_path, 'dir-create-test', self._parsed())
        assert result is True
        assert os.path.exists(nested_path)
