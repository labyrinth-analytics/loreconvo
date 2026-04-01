"""Session Bridge configuration."""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    db_path: str = ""
    max_free_sessions: int = 50
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

    @property
    def is_pro(self) -> bool:
        """Return True if the user has an active Pro license.

        Pro mode is enabled by setting the LORECONVO_PRO environment variable
        to any non-empty value. This is a simple first-pass mechanism -- a
        cryptographically-verified license key will replace it once billing
        is wired up.
        """
        return bool(os.environ.get("LORECONVO_PRO", "").strip())
