import base64
import logging
from typing import Optional

import httpx

GITHUB_API_BASE = "https://api.github.com"

logger = logging.getLogger("auto_readme_bot.github_api")


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def get_tree(client: httpx.AsyncClient, token: str, repo_full_name: str, sha: str) -> list:
    """Fetch the full recursive file tree for a commit SHA."""
    url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/git/trees/{sha}"
    resp = await client.get(url, headers=_headers(token), params={"recursive": "1"})
    resp.raise_for_status()
    data = resp.json()
    if data.get("truncated"):
        logger.warning("Tree for %s@%s was truncated by GitHub API", repo_full_name, sha)
    return [entry for entry in data.get("tree", []) if entry.get("type") == "blob"]


async def get_file_content(
    client: httpx.AsyncClient, token: str, repo_full_name: str, path: str, ref: str
) -> Optional[str]:
    """Fetch a single file's decoded text content via the Contents API."""
    url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/contents/{path}"
    resp = await client.get(url, headers=_headers(token), params={"ref": ref})
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    data = resp.json()
    if data.get("encoding") != "base64":
        return None
    try:
        return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
    except Exception:
        logger.warning("Failed to decode content for %s in %s", path, repo_full_name)
        return None


async def get_existing_readme(
    client: httpx.AsyncClient, token: str, repo_full_name: str, ref: str
) -> tuple[Optional[str], Optional[str]]:
    """Return (content, sha) for README.md on the given ref, or (None, None) if absent."""
    url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/contents/README.md"
    resp = await client.get(url, headers=_headers(token), params={"ref": ref})
    if resp.status_code == 404:
        return None, None
    resp.raise_for_status()
    data = resp.json()
    content = None
    if data.get("encoding") == "base64":
        content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
    return content, data.get("sha")


async def put_readme(
    client: httpx.AsyncClient,
    token: str,
    repo_full_name: str,
    branch: str,
    new_content: str,
    existing_sha: Optional[str],
    commit_message: str,
) -> dict:
    """Create or update README.md on the given branch."""
    url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/contents/README.md"
    payload = {
        "message": commit_message,
        "content": base64.b64encode(new_content.encode("utf-8")).decode("ascii"),
        "branch": branch,
    }
    if existing_sha:
        payload["sha"] = existing_sha
    resp = await client.put(url, headers=_headers(token), json=payload)
    resp.raise_for_status()
    return resp.json()


async def get_commit(
    client: httpx.AsyncClient, token: str, repo_full_name: str, sha: str
) -> dict:
    """Fetch commit metadata, used to check who authored the triggering commit."""
    url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/commits/{sha}"
    resp = await client.get(url, headers=_headers(token))
    resp.raise_for_status()
    return resp.json()


async def get_branch_sha(
    client: httpx.AsyncClient, token: str, repo_full_name: str, branch: str
) -> Optional[str]:
    """Return the head commit SHA of a branch, or None if it doesn't exist."""
    url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/git/ref/heads/{branch}"
    resp = await client.get(url, headers=_headers(token))
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()["object"]["sha"]


async def ensure_branch_at(
    client: httpx.AsyncClient, token: str, repo_full_name: str, branch: str, sha: str
) -> None:
    """Create the branch at `sha` if it doesn't exist; force-reset it to `sha` if it does
    and has drifted. Keeps the bot branch always one commit ahead of the trigger branch."""
    existing_sha = await get_branch_sha(client, token, repo_full_name, branch)
    if existing_sha is None:
        url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/git/refs"
        resp = await client.post(
            url, headers=_headers(token),
            json={"ref": f"refs/heads/{branch}", "sha": sha},
        )
        resp.raise_for_status()
    elif existing_sha != sha:
        url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/git/refs/heads/{branch}"
        resp = await client.patch(
            url, headers=_headers(token), json={"sha": sha, "force": True}
        )
        resp.raise_for_status()


async def find_open_pull_request(
    client: httpx.AsyncClient, token: str, repo_full_name: str, branch: str, base: str
) -> Optional[dict]:
    """Return the open PR from `branch` into `base`, if one already exists."""
    owner = repo_full_name.split("/")[0]
    url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/pulls"
    params = {"head": f"{owner}:{branch}", "base": base, "state": "open"}
    resp = await client.get(url, headers=_headers(token), params=params)
    resp.raise_for_status()
    results = resp.json()
    return results[0] if results else None


async def create_pull_request(
    client: httpx.AsyncClient,
    token: str,
    repo_full_name: str,
    branch: str,
    base: str,
    title: str,
    body: str,
) -> dict:
    url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/pulls"
    resp = await client.post(
        url, headers=_headers(token),
        json={"title": title, "head": branch, "base": base, "body": body},
    )
    resp.raise_for_status()
    return resp.json()
