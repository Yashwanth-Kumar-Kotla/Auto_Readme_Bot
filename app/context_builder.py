import logging
import os
from dataclasses import dataclass

import httpx
import tiktoken

from app import config, github_api

logger = logging.getLogger("auto_readme_bot.context_builder")

_ENCODING = tiktoken.get_encoding("o200k_base")


def count_tokens(text: str) -> int:
    return len(_ENCODING.encode(text))


@dataclass
class RepoContext:
    file_tree: list[str]
    key_files: dict[str, str]
    tree_truncated: bool = False


def _is_ignored_path(path: str) -> bool:
    parts = path.split("/")
    if any(part in config.IGNORED_DIR_NAMES for part in parts[:-1]):
        return True
    filename = parts[-1]
    if filename in config.IGNORED_FILENAMES:
        return True
    _, ext = os.path.splitext(filename)
    if ext.lower() in config.IGNORED_EXTENSIONS:
        return True
    return False


def _select_key_paths(paths: list[str]) -> list[str]:
    """Pick the paths worth fetching content for: readmes, manifests,
    entry points, and other reasonably-sized top-level source files."""
    selected = []

    def basename(p):
        return p.split("/")[-1]

    for p in paths:
        if basename(p) in config.README_FILENAMES:
            selected.append(p)
    for p in paths:
        if basename(p) in config.MANIFEST_FILENAMES or p in config.MANIFEST_FILENAMES:
            selected.append(p)
    for p in paths:
        if basename(p) in config.ENTRY_POINT_FILENAMES or p in config.ENTRY_POINT_FILENAMES:
            selected.append(p)

    # Fill remaining budget with other top-level (or shallow) source files.
    code_exts = {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rb", ".java",
        ".rs", ".c", ".cpp", ".cs", ".php", ".kt", ".swift",
    }
    shallow_source = [
        p for p in paths
        if p not in selected
        and p.count("/") <= 1
        and os.path.splitext(p)[1].lower() in code_exts
    ]
    selected.extend(sorted(shallow_source))

    # Preserve order, drop duplicates.
    seen = set()
    ordered = []
    for p in selected:
        if p not in seen:
            seen.add(p)
            ordered.append(p)
    return ordered


async def build_repo_context(
    client: httpx.AsyncClient, token: str, repo_full_name: str, sha: str
) -> RepoContext:
    raw_tree = await github_api.get_tree(client, token, repo_full_name, sha)

    all_paths = [
        entry["path"] for entry in raw_tree
        if entry.get("size", 0) <= config.MAX_FILE_SIZE_BYTES
    ]
    visible_paths = [p for p in all_paths if not _is_ignored_path(p)]

    if len(visible_paths) > config.MAX_TREE_ENTRIES:
        logger.warning(
            "Repo %s has %d visible files, truncating tree listing to %d",
            repo_full_name, len(visible_paths), config.MAX_TREE_ENTRIES,
        )
        visible_paths = visible_paths[: config.MAX_TREE_ENTRIES]

    key_paths = _select_key_paths(visible_paths)

    key_files: dict[str, str] = {}
    budget_remaining = config.CONTEXT_BUDGET_TOKENS
    for path in key_paths:
        if budget_remaining <= 0:
            break
        content = await github_api.get_file_content(client, token, repo_full_name, path, sha)
        if content is None:
            continue
        tokens = count_tokens(content)
        if tokens > budget_remaining:
            # Trim to roughly the remaining token budget rather than skipping outright.
            ratio = budget_remaining / tokens
            content = content[: max(1, int(len(content) * ratio))]
            tokens = count_tokens(content)
        key_files[path] = content
        budget_remaining -= tokens

    tree_for_prompt = visible_paths[: config.MAX_TREE_ENTRIES_IN_PROMPT]
    tree_truncated = len(visible_paths) > len(tree_for_prompt)

    return RepoContext(
        file_tree=tree_for_prompt, key_files=key_files, tree_truncated=tree_truncated
    )
