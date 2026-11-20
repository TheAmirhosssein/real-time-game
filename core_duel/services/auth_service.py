"""Register, login, password hashing, and guest account generation."""

from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from typing import Any, Optional

from core_duel.services.database import DatabaseManager

CALLSIGN_RE = re.compile(r"^[A-Za-z0-9_]{3,16}$")
PBKDF2_ROUNDS = 120_000


class AuthError(Exception):
    pass


class AuthService:
    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    @staticmethod
    def hash_password(password: str) -> str:
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ROUNDS
        )
        return f"{salt}${digest.hex()}"

    @staticmethod
    def verify_password(password: str, stored: str) -> bool:
        try:
            salt, digest_hex = stored.split("$", 1)
        except ValueError:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ROUNDS
        )
        return secrets.compare_digest(digest.hex(), digest_hex)

    def register(
        self,
        callsign: str,
        email: str,
        password: str,
        confirm: str,
    ) -> dict[str, Any]:
        callsign = callsign.strip()
        email = email.strip()
        if not CALLSIGN_RE.match(callsign):
            raise AuthError("Callsign must be 3–16 letters, numbers, or underscores.")
        if not email:
            raise AuthError("Email / Student ID is required.")
        if len(password) < 4:
            raise AuthError("Password must be at least 4 characters.")
        if password != confirm:
            raise AuthError("Passwords do not match.")
        if self.db.get_user_by_username(callsign):
            raise AuthError("That callsign is already registered.")
        return self.db.insert_user(
            user_id=str(uuid.uuid4()),
            username=callsign,
            password_hash=self.hash_password(password),
            is_guest=False,
            email=email,
            score=1000,
        )

    def login(self, username: str, password: str) -> dict[str, Any]:
        username = username.strip()
        if not username or not password:
            raise AuthError("Enter callsign and password.")
        row = self.db.get_user_by_username(username)
        if not row or row["is_guest"]:
            raise AuthError("Unknown pilot or invalid credentials.")
        if not row["password_hash"] or not self.verify_password(password, row["password_hash"]):
            raise AuthError("Unknown pilot or invalid credentials.")
        self.db.touch_user(row["user_id"])
        return self.db.user_to_dict(row)

    def continue_as_guest(self) -> dict[str, Any]:
        for _ in range(16):
            tag = secrets.randbelow(9000) + 1000
            username = f"Guest_{tag}"
            if self.db.get_user_by_username(username) is None:
                user = self.db.insert_user(
                    user_id=str(uuid.uuid4()),
                    username=username,
                    password_hash=None,
                    is_guest=True,
                    email=None,
                    score=1000,
                )
                return user
        raise AuthError("Could not allocate a guest callsign. Try again.")

    def refresh(self, user_id: str) -> Optional[dict[str, Any]]:
        return self.db.get_user_by_id(user_id)
