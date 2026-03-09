"""
Vhive API key authentication.

Single-user model: an API key is auto-generated on first run and stored at
~/.vhive/api_key. All HTTP and WebSocket endpoints require this key as a
Bearer token. The key can be overridden via the VHIVE_API_KEY env var.
"""

import hashlib
import hmac
import os
import secrets
from pathlib import Path

VHIVE_DIR = Path.home() / ".vhive"
KEY_FILE = VHIVE_DIR / "api_key"


def _ensure_dir() -> None:
    VHIVE_DIR.mkdir(parents=True, exist_ok=True)


def generate_api_key() -> str:
    """Generate a new API key and persist it to ~/.vhive/api_key."""
    _ensure_dir()
    key = secrets.token_urlsafe(32)
    KEY_FILE.write_text(key + "\n")
    KEY_FILE.chmod(0o600)
    return key


def load_api_key() -> str:
    """Load the API key from env var or file, generating one if needed."""
    # Env var takes precedence
    env_key = os.environ.get("VHIVE_API_KEY", "").strip()
    if env_key:
        return env_key

    # Read from file
    if KEY_FILE.exists():
        stored = KEY_FILE.read_text().strip()
        if stored:
            return stored

    # First run — generate
    return generate_api_key()


def verify_key(provided: str, expected: str) -> bool:
    """Constant-time comparison to prevent timing attacks."""
    return hmac.compare_digest(
        hashlib.sha256(provided.encode()).digest(),
        hashlib.sha256(expected.encode()).digest(),
    )


# Module-level singleton so the key is loaded once on import
API_KEY = load_api_key()
