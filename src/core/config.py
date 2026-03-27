"""Session Bridge configuration."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    db_path: str = ""
    max_free_sessions: int = 100
    default_days_back: int = 30
    default_limit: int = 10

    def __post_init__(self):
        if not self.db_path:
            self.db_path = os.environ.get(
                "LORECONVO_DB",
                str(Path.home() / ".loreconvo" / "sessions.db")
            )

    def ensure_db_dir(self):
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
