import logging

import httpx
from fastapi import FastAPI, Header, Request, Response

from app import auth, config, github_api, security
from app.context_builder import build_repo_context
from app.readme_generator import generate_readme

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("auto_readme_bot")

app = FastAPI(title="Auto-README Bot")


@app.get("/")
async def health_check():
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
):
    raw_body = await request.body()

    if not security.verify_signature(raw_body, x_hub_signature_256):
        logger.warning("Rejected webhook: invalid signature")
        return Response(status_code=401, content="invalid signature")

    if x_github_event != "push":
        logger.info("Ignoring event type: %s", x_github_event)
        return {"status": "ignored", "reason": "not a push event"}

    payload = await request.json()

    repo_full_name = payload.get("repository", {}).get("full_name")
    default_branch = payload.get("repository", {}).get("default_branch")
    ref = payload.get("ref", "")
    installation_id = payload.get("installation", {}).get("id")
    head_commit = payload.get("head_commit") or {}
    sha = payload.get("after") or head_commit.get("id")

    if not all([repo_full_name, default_branch, installation_id, sha]):
        logger.info("Ignoring push: missing required fields in payload")
        return {"status": "ignored", "reason": "incomplete payload"}

    pushed_branch = ref.removeprefix("refs/heads/")
    if pushed_branch != default_branch:
        logger.info(
            "Ignoring push to %s on %s (default branch is %s)",
            pushed_branch, repo_full_name, default_branch,
        )
        return {"status": "ignored", "reason": "not the default branch"}

    if payload.get("deleted"):
        logger.info("Ignoring branch deletion on %s", repo_full_name)
        return {"status": "ignored", "reason": "branch deletion"}

    try:
        await process_push(repo_full_name, default_branch, installation_id, sha)
    except Exception:
        logger.exception("Failed processing push for %s@%s", repo_full_name, sha)

    # Always 200 back to GitHub so it doesn't retry-storm us on failure.
    return {"status": "processed"}


async def process_push(repo_full_name: str, default_branch: str, installation_id: int, sha: str):
    logger.info("Processing push: %s@%s (branch=%s)", repo_full_name, sha, default_branch)

    token = await auth.get_installation_token(installation_id)

    async with httpx.AsyncClient(timeout=30) as client:
        commit = await github_api.get_commit(client, token, repo_full_name, sha)
        if _is_bot_commit(commit):
            logger.info("Skipping %s@%s: triggered by our own bot commit", repo_full_name, sha)
            return

        ctx = await build_repo_context(client, token, repo_full_name, sha)

        try:
            new_readme = generate_readme(repo_full_name, ctx)
        except Exception:
            logger.exception("Claude API call failed for %s@%s", repo_full_name, sha)
            return

        existing_content, existing_sha = await github_api.get_existing_readme(
            client, token, repo_full_name, default_branch
        )

        if existing_content is not None and existing_content.strip() == new_readme.strip():
            logger.info("Skipping %s: README unchanged", repo_full_name)
            return

        await github_api.put_readme(
            client,
            token,
            repo_full_name,
            default_branch,
            new_readme,
            existing_sha,
            config.BOT_COMMIT_MARKER,
        )
        logger.info("Updated README.md for %s", repo_full_name)


def _is_bot_commit(commit: dict) -> bool:
    message = commit.get("commit", {}).get("message", "")
    if config.BOT_COMMIT_MARKER in message:
        return True
    author_name = (commit.get("commit", {}).get("author", {}) or {}).get("name", "")
    committer_name = (commit.get("commit", {}).get("committer", {}) or {}).get("name", "")
    login = (commit.get("author") or {}).get("login", "")
    names = {author_name, committer_name, login}
    return any(hint in name for name in names for hint in config.BOT_AUTHOR_NAME_HINTS)
