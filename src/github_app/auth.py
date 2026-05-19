import time
import requests
import jwt
from src.config.env import config
from src.utils.logger import log


def generate_app_jwt() -> str:
    """
    Generate a short-lived JWT signed with the GitHub App private key.
    This JWT is used to authenticate as the GitHub App itself (not as a user).
    Valid for 10 minutes — GitHub's max allowed.
    """
    payload = {
        "iat": int(time.time()) - 60,   # issued 60s ago (handles clock drift)
        "exp": int(time.time()) + 600,  # expires in 10 minutes
        "iss": config.GITHUB_APP_ID,
    }

    token = jwt.encode(
        payload,
        config.GITHUB_APP_PRIVATE_KEY,
        algorithm="RS256",
    )

    # PyJWT >= 2.0 returns str directly
    return token if isinstance(token, str) else token.decode("utf-8")


def get_installation_token(installation_id: int) -> str:
    """
    Exchange the GitHub App JWT for an installation access token.

    Each repo that installs your GitHub App gets a unique installation_id.
    This token lets you act on behalf of that specific installation (repo).
    Token is valid for 1 hour — GitHub rotates them automatically.
    """
    app_jwt = generate_app_jwt()

    log.debug(f"Requesting installation token for installation {installation_id}...")

    response = requests.post(
        f"https://api.github.com/app/installations/{installation_id}/access_tokens",
        headers={
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=30,
    )

    if response.status_code != 201:
        raise RuntimeError(
            f"Failed to get installation token for installation {installation_id}: "
            f"{response.status_code} {response.text}"
        )

    token = response.json()["token"]
    log.debug(f"✅ Got installation token for installation {installation_id}")
    return token
