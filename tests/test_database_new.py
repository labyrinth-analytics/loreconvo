"""Tests for new database features: list_all_skills, _parse_json_field, get_session_chain.

Added by Meg QA 2026-03-29. Covers:
- list_all_skills() - new method added commit 7dbd4ce
- _parse_json_field() - edge cases from legacy-format handling (commits 891d35f, 0e122e3)
- get_session_chain() - cycle detection
"""

import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from core.database import SessionDatabase
from core.models import Session
from core.config import Config


def make_db(tmp_path):
    """Create a test database in a temp directory."""
    cfg = Config.__new__(Config)
    cfg.db_path = os.path.join(str(tmp_path), 'test.db')
    cfg.db_dir = str(tmp_path)
    return SessionDatabase(cfg)


# ============================================================
# list_all_skills
# ============================================================

class TestListAllSkills:
    def test_empty_database_returns_empty_list(self, tmp_path):
        db = make_db(tmp_path)
        result = db.list_all_skills()
        assert result == []
        db.close()

    def test_single_skill_returns_one_entry(self, tmp_path):
        db = make_db(tmp_path)
        s = Session(title='t', surface='code', summary='s', skills_used=['pptx'])
        db.save_session(s)
        result = db.list_all_skills()
        assert len(result) == 1
        assert result[0]['skill_name'] == 'pptx'
        assert result[0]['session_count'] == 1
        db.close()

    def test_skill_used_in_multiple_sessions_counted_correctly(self, tmp_path):
        db = make_db(tmp_path)
        for i in range(3):
            s = Session(title=f'session {i}', surface='code', summary='x', skills_used=['pptx'])
            db.save_session(s)
        result = db.list_all_skills()
        counts = {r['skill_name']: r['session_count'] for r in result}
        assert counts['pptx'] == 3
        db.close()

    def test_sorted_by_count_descending(self, tmp_path):
        db = make_db(tmp_path)
        # pptx used 3x, xlsx used 1x
        for i in range(3):
            s = Session(title=f's{i}', surface='code', summary='x', skills_used=['pptx'])
            db.save_session(s)
        s_xlsx = Session(title='xlsx session', surface='code', summary='y', skills_used=['xlsx'])
        db.save_session(s_xlsx)
        result = db.list_all_skills()
        assert result[0]['skill_name'] == 'pptx'
        assert result[1]['skill_name'] == 'xlsx'
        db.close()

    def test_multiple_skills_in_one_session(self, tmp_path):
        db = make_db(tmp_path)
        s = Session(title='t', surface='code', summary='s', skills_used=['pptx', 'xlsx', 'docx'])
        db.save_session(s)
        result = db.list_all_skills()
        names = {r['skill_name'] for r in result}
        assert names == {'pptx', 'xlsx', 'docx'}
        for r in result:
            assert r['session_count'] == 1
        db.close()

    def test_returns_list_of_dicts_with_correct_keys(self, tmp_path):
        db = make_db(tmp_path)
        s = Session(title='t', surface='code', summary='s', skills_used=['pptx'])
        db.save_session(s)
        result = db.list_all_skills()
        assert isinstance(result, list)
        assert 'skill_name' in result[0]
        assert 'session_count' in result[0]
        db.close()


# ============================================================
# _parse_json_field
# ============================================================

class TestParseJsonField:
    def test_json_array_returns_list(self):
        result = SessionDatabase._parse_json_field('["a", "b", "c"]')
        assert result == ['a', 'b', 'c']

    def test_empty_json_array_returns_empty_list(self):
        result = SessionDatabase._parse_json_field('[]')
        assert result == []

    def test_none_returns_empty_list(self):
        result = SessionDatabase._parse_json_field(None)
        assert result == []

    def test_comma_separated_tags_parsed_as_list(self):
        result = SessionDatabase._parse_json_field('security,audit,supply-chain')
        assert result == ['security', 'audit', 'supply-chain']

    def test_single_token_no_spaces_returned_as_single_item(self):
        result = SessionDatabase._parse_json_field('singletag')
        assert result == ['singletag']

    def test_plain_text_blob_returned_as_single_item(self):
        blob = 'This is a long architecture proposal with spaces and multiple words.'
        result = SessionDatabase._parse_json_field(blob)
        assert len(result) == 1
        assert result[0] == blob

    def test_non_list_json_wrapped_in_list(self):
        # JSON object is not a list -- should wrap
        result = SessionDatabase._parse_json_field('"just a string"')
        assert result == ['just a string']

    def test_trailing_comma_in_csv_handled(self):
        result = SessionDatabase._parse_json_field('tag1,tag2,')
        assert 'tag1' in result
        assert 'tag2' in result
        # trailing empty string should not be included
        assert '' not in result

    def test_default_value_used_for_none(self):
        result = SessionDatabase._parse_json_field(None, default='[]')
        assert result == []

    def test_single_comma_separated_pair(self):
        result = SessionDatabase._parse_json_field('a,b')
        assert result == ['a', 'b']


# ============================================================
# get_session_chain (cycle safety)
# ============================================================

class TestGetSessionChain:
    def test_single_session_chain(self, tmp_path):
        db = make_db(tmp_path)
        s = Session(title='t', surface='code', summary='s')
        db.save_session(s)
        chain = db.get_session_chain(s.id)
        assert len(chain) == 1
        assert chain[0].id == s.id
        db.close()

    def test_linked_chain_returns_both_sessions(self, tmp_path):
        db = make_db(tmp_path)
        s1 = Session(title='first', surface='code', summary='s')
        s2 = Session(title='second', surface='code', summary='s')
        db.save_session(s1)
        db.save_session(s2)
        db.link_sessions(s1.id, s2.id)
        chain = db.get_session_chain(s1.id)
        chain_ids = {s.id for s in chain}
        assert s1.id in chain_ids
        assert s2.id in chain_ids
        db.close()

    def test_cycle_does_not_infinite_loop(self, tmp_path):
        db = make_db(tmp_path)
        s1 = Session(title='s1', surface='code', summary='x')
        s2 = Session(title='s2', surface='code', summary='y')
        db.save_session(s1)
        db.save_session(s2)
        # Create a cycle: s1 -> s2 -> s1
        db.link_sessions(s1.id, s2.id)
        db.link_sessions(s2.id, s1.id)
        chain = db.get_session_chain(s1.id)
        assert len(chain) == 2
        db.close()

    def test_chain_sorted_by_start_date(self, tmp_path):
        db = make_db(tmp_path)
        s1 = Session(title='first', surface='code', summary='x')
        s2 = Session(title='second', surface='code', summary='y')
        db.save_session(s1)
        db.save_session(s2)
        db.link_sessions(s1.id, s2.id)
        chain = db.get_session_chain(s2.id)
        # Should be sorted by start_date ascending
        for i in range(len(chain) - 1):
            assert chain[i].start_date <= chain[i + 1].start_date
        db.close()

    def test_nonexistent_session_returns_empty_list(self, tmp_path):
        db = make_db(tmp_path)
        chain = db.get_session_chain('nonexistent-id-12345')
        assert chain == []
        db.close()
