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
    mode: str = "full"  # "full" or "incremental"
    existing_readme: str | None = None
    added_paths: list[str] = None
    modified_paths: list[str] = None
    removed_paths: list[str] = None

    def __post_init__(self):
        self.added_paths = self.added_paths or []
        self.modified_paths = self.modified_paths or []
        self.removed_paths = self.removed_paths or []


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


def _decide_mode(
    visible_paths: list[str],
    changed_paths: list[str],
    existing_readme: str | None,
) -> str:
    if existing_readme is None or not changed_paths:
        return "full"
    ratio = len(changed_paths) / max(1, len(visible_paths))
    if ratio > config.INCREMENTAL_CHANGE_RATIO_THRESHOLD:
        return "full"
    return "incremental"


async def build_repo_context(
    client: httpx.AsyncClient,
    token: str,
    repo_full_name: str,
    sha: str,
    existing_readme: str | None = None,
    added: list[str] | None = None,
    modified: list[str] | None = None,
    removed: list[str] | None = None,
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

    visible_set = set(visible_paths)
    added = [p for p in (added or []) if p in visible_set]
    modified = [p for p in (modified or []) if p in visible_set]
    removed = [p for p in (removed or []) if not _is_ignored_path(p)]
    changed_paths = added + modified

    mode = _decide_mode(visible_paths, changed_paths, existing_readme)

    if mode == "incremental":
        key_paths = changed_paths
        logger.info(
            "Repo %s: incremental mode, %d changed file(s)",
            repo_full_name, len(key_paths),
        )
    else:
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
        file_tree=tree_for_prompt,
        key_files=key_files,
        tree_truncated=tree_truncated,
        mode=mode,
        existing_readme=existing_readme if mode == "incremental" else None,
        added_paths=added,
        modified_paths=modified,
        removed_paths=removed,
    )
