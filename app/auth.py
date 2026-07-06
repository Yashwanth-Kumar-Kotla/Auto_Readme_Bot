import time
import logging

import jwt
import httpx

from app import config

logger = logging.getLogger("auto_readme_bot.auth")

GITHUB_API_BASE = "https://api.github.com"


def _load_private_key() -> str:
    if config.GITHUB_APP_PRIVATE_KEY:
        # Support env vars where literal "\n" was used instead of real newlines.
        return config.GITHUB_APP_PRIVATE_KEY.replace("\\n", "\n")
    if config.GITHUB_APP_PRIVATE_KEY_PATH:
        with open(config.GITHUB_APP_PRIVATE_KEY_PATH, "r") as f:
            return f.read()
    raise RuntimeError(
        "No GitHub App private key configured. Set GITHUB_APP_PRIVATE_KEY "
        "or GITHUB_APP_PRIVATE_KEY_PATH."
    )


def generate_app_jwt() -> str:
    """Generate a short-lived JWT authenticating as the GitHub App itself."""
    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + (9 * 60),
        "iss": config.GITHUB_APP_ID,
    }
    private_key = _load_private_key()
    return jwt.encode(payload, private_key, algorithm="RS256")


async def get_installation_token(installation_id: int) -> str:
    """Exchange the App JWT for a short-lived installation access token."""
    app_jwt = generate_app_jwt()
    url = f"{GITHUB_API_BASE}/app/installations/{installation_id}/access_tokens"
    headers = {
        "Authorization": f"Bearer {app_jwt}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, headers=headers)
    resp.raise_for_status()
    return resp.json()["token"]
