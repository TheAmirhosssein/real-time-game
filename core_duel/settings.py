"""Runtime configuration. Load DATABASE_URL from the environment or .env."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://coreduel:coreduel@localhost:5432/coreduel",
)
