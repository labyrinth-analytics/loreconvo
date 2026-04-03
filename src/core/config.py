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
        """Return True if the user has a valid Pro license.

        Pro mode is enabled by setting the LORECONVO_PRO environment variable
        to a valid Labyrinth Analytics license key (LAB-...).

        For internal agents: set both LORECONVO_PRO=1 and LAB_DEV_MODE=1 in
        the internal .mcp.json to bypass key validation.  The public plugin
        .mcp.json files must NOT include LAB_DEV_MODE.
        """
        from .license import is_pro_licensed
        return is_pro_licensed()
