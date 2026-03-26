"""Session Bridge data models. Dataclasses with direct attribute access."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class Session:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    surface: str = ""  # 'cowork', 'code', 'chat'
    project: Optional[str] = None
    start_date: str = field(default_factory=lambda: datetime.now().isoformat())
    end_date: Optional[str] = None
    summary: str = ""
    decisions: List[str] = field(default_factory=list)
    artifacts: List[str] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    skills_used: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Project:
    name: str = ""
    description: str = ""
    expected_skills: List[str] = field(default_factory=list)
    default_persona: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class PersonaTag:
    persona_name: str = ""
    session_id: str = ""
    relevance_note: Optional[str] = None


@dataclass
class SessionLink:
    from_session_id: str = ""
    to_session_id: str = ""
    link_type: str = "continues"  # 'continues', 'related', 'supersedes'


@dataclass
class SkillUsage:
    session_id: str = ""
    skill_name: str = ""
    skill_source: Optional[str] = None  # 'local', 'plugin:engineering', etc.
    invocation_count: int = 1


@dataclass
class SearchResult:
    session: Session
    relevance_excerpt: str = ""
    match_score: float = 0.0
