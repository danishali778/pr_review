import os
import sys
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


def get_env_str_optional(key: str) -> Optional[str]:
    v = os.getenv(key)
    if v is None or v.strip() == "":
        return None
    return v.strip()


def get_env_str_with_default(key: str, default: str) -> str:
    v = os.getenv(key)
    if v is None or v.strip() == "":
        return default
    return v.strip()


def get_env_int(key: str, default: int) -> int:
    v = os.getenv(key)
    if v is None or v.strip() == "":
        return default
    try:
        return int(v.strip())
    except ValueError:
        raise ValueError(f"Environment variable '{key}' must be a valid integer, got '{v}'")


def get_env_bool(key: str, default: bool) -> bool:
    v = os.getenv(key)
    if v is None or v.strip() == "":
        return default
    return v.strip().lower() not in ("false", "0", "no", "n")


class Settings:
    def __init__(self) -> None:
        # ── GitHub App ────────────────────────────────────────────────
        self.GITHUB_APP_ID: Optional[str] = get_env_str_optional("GITHUB_APP_ID")
        
        raw_private_key = get_env_str_optional("GITHUB_APP_PRIVATE_KEY")
        self.GITHUB_APP_PRIVATE_KEY: Optional[str] = self.normalize_private_key(raw_private_key)
        
        self.GITHUB_WEBHOOK_SECRET: Optional[str] = get_env_str_optional("GITHUB_WEBHOOK_SECRET")

        # ── GitHub PAT / Actions ──────────────────────────────────────
        self.GITHUB_TOKEN: Optional[str] = get_env_str_optional("GITHUB_TOKEN")

        # ── Jules API ─────────────────────────────────────────────────
        jules_key = get_env_str_optional("JULES_API_KEY")
        if not jules_key:
            raise ValueError("JULES_API_KEY is a required field. Please set JULES_API_KEY in your environment or .env file.")
        if jules_key == "your_jules_api_key_here":
            raise ValueError("JULES_API_KEY is still a placeholder. Set a real key.")
        self.JULES_API_KEY: str = jules_key
        
        self.JULES_BASE_URL: str = get_env_str_with_default("JULES_BASE_URL", "https://jules.googleapis.com/v1alpha")

        # ── Server ────────────────────────────────────────────────────
        self.PORT: int = get_env_int("PORT", 8000)
        self.DATABASE_PATH: str = get_env_str_with_default("DATABASE_PATH", "jules_reviewer.db")

        # ── Review config ─────────────────────────────────────────────
        self.REVIEW_TIMEOUT_SECS: int = get_env_int("REVIEW_TIMEOUT_SECS", 600)
        self.POLL_INTERVAL_SECS: int = get_env_int("POLL_INTERVAL_SECS", 15)
        self.MAX_RETRIES: int = get_env_int("MAX_RETRIES", 3)
        self.SKIP_DRAFT_PRS: bool = get_env_bool("SKIP_DRAFT_PRS", True)

    @staticmethod
    def normalize_private_key(v: Optional[str]) -> Optional[str]:
        """Handle \n escaped newlines when PEM is stored as a single-line env var."""
        if v and "\\n" in v:
            v = v.replace("\\n", "\n")
        return v


def load_config() -> Settings:
    try:
        return Settings()
    except Exception as e:
        print(f"\n❌ Configuration error:\n   {e}")
        print("\n👉 Copy .env.example to .env and fill in your values.\n")
        sys.exit(1)


config = load_config()
