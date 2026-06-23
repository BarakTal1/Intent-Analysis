from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv(override=True)


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str = field(default_factory=lambda: os.environ["ANTHROPIC_API_KEY"])
    model_name: str = "anthropic:claude-sonnet-4-6"
    satisfaction_threshold: float = 0.85
    skills_relevance_threshold: float = 0.5


settings = Settings()
