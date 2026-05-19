import sys
from pydantic import BaseSettings, validator
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    # ── GitHub App ────────────────────────────────────────────────
    GITHUB_APP_ID: str
    GITHUB_APP_PRIVATE_KEY: str          # Full PEM content
    GITHUB_WEBHOOK_SECRET: str

    # ── Jules API ─────────────────────────────────────────────────
    JULES_API_KEY: str
    JULES_BASE_URL: str = "https://jules.googleapis.com/v1alpha"

    # ── Server ────────────────────────────────────────────────────
    PORT: int = 8000

    # ── Review config ─────────────────────────────────────────────
    REVIEW_TIMEOUT_SECS: int = 600
    POLL_INTERVAL_SECS: int = 15
    MAX_RETRIES: int = 3
    SKIP_DRAFT_PRS: bool = True

    @validator("JULES_API_KEY")
    @classmethod
    def jules_key_not_placeholder(cls, v: str) -> str:
        if v == "your_jules_api_key_here":
            raise ValueError("JULES_API_KEY is still a placeholder. Set a real key.")
        return v

    @validator("GITHUB_APP_PRIVATE_KEY")
    @classmethod
    def normalize_private_key(cls, v: str) -> str:
        """Handle \n escaped newlines when PEM is stored as a single-line env var."""
        if "\\n" in v:
            v = v.replace("\\n", "\n")
        return v

    class Config:
        env_file = ".env"


def load_config() -> Settings:
    try:
        return Settings()  # type: ignore[call-arg]
    except Exception as e:
        print(f"\n❌ Configuration error:\n   {e}")
        print("\n👉 Copy .env.example to .env and fill in your values.\n")
        sys.exit(1)


config = load_config()
