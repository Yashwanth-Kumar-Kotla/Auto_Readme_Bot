import logging

from openai import OpenAI

from app import config
from app.context_builder import RepoContext

logger = logging.getLogger("auto_readme_bot.readme_generator")

# Kept short deliberately: this is sent on every single call, so every extra
# line here is a recurring token cost across every repo/push.
SYSTEM_PROMPT = """Generate or update a README.md for a repo from the file tree and file contents given.

Output ONLY raw markdown. No preamble, no wrapping code fence around the whole doc.

Grounding rules (most important — violating these produces a wrong README, which is worse than a \
plain one):
- Every claim must trace to a specific given file or its content. If you cannot point to the \
evidence, omit the claim rather than guess or infer from a filename alone.
- Never invent commands, env vars, dependencies, endpoints, or features that aren't in the given \
files. Don't assume a common framework's default behavior applies unless the given files confirm it.
- If the given context is too thin to describe something with confidence (e.g. you see a filename \
but not its content), describe it at the confidence level the evidence supports, or skip it.

Update mode (only when "EXISTING README" and "CHANGED FILES" sections are present below):
- You are editing the existing README, not rewriting it. Keep every section that the changed files \
don't affect byte-for-byte identical.
- Only touch the sections whose accuracy is affected by the added/modified/removed files listed. \
Add new sections only if the change clearly warrants one (e.g. a new major feature).
- If a removed file was the sole evidence for a section/claim, delete that part.
- Update the Mermaid diagram only if the changed files alter the actual flow it depicts; otherwise \
leave it untouched.

Rules for the diagram (new README) or its updates (edit mode):
- Include one ```mermaid diagram showing this project's real code/data flow, derived from the \
actual structure, not generic. Draw it as ONE straight top-to-bottom pipeline: each step points only \
to the next step in sequence (A --> B --> C --> D...). Never draw an edge back into a step that \
already has incoming edges from earlier in the chain (no "returns to caller" arrows, no hub node \
that many other nodes point back into) — that always renders as an unreadable tangle. If two real \
components genuinely call back and forth repeatedly, collapse that into a single step in the \
diagram and explain the back-and-forth in prose instead. Keep it to at most 10 nodes.
- Mermaid syntax must be strict, since GitHub rejects malformed diagrams outright: node and edge \
labels must contain ONLY letters, numbers, and spaces — no parentheses, colons, slashes, quotes, \
or other punctuation. Never write labels like `A -->|fetch (multiple)| B`; write `A -->|fetch multiple| B` \
instead. Keep node IDs short alphanumeric tokens (e.g. `M`, `GAPI`) separate from their bracketed \
label text.

General:
- Include install/usage instructions inferred from the actual manifest/entry files given.
- Sections as warranted by evidence: title, description, features, installation, usage, structure, \
architecture diagram. Skip license/badges/contributors unless evidenced.
- Be concise. No filler paragraphs."""


def _build_user_prompt(repo_full_name: str, ctx: RepoContext) -> str:
    tree_block = "\n".join(ctx.file_tree)
    if ctx.tree_truncated:
        tree_block += "\n... (tree truncated for length)"
    files_block = "\n\n".join(
        f"--- {path} ---\n{content}" for path, content in ctx.key_files.items()
    )

    if ctx.mode == "incremental" and ctx.existing_readme is not None:
        changes_lines = (
            [f"Added: {p}" for p in ctx.added_paths]
            + [f"Modified: {p}" for p in ctx.modified_paths]
            + [f"Removed: {p}" for p in ctx.removed_paths]
        )
        changes_block = "\n".join(changes_lines) or "(no file-level changes detected)"
        return (
            f"Repo: {repo_full_name}\n\n"
            f"EXISTING README:\n{ctx.existing_readme}\n\n"
            f"CHANGED FILES in this push:\n{changes_block}\n\n"
            f"Contents of added/modified files:\n{files_block}\n\n"
            f"Full current file tree (for context, not all shown as content):\n{tree_block}"
        )

    return f"Repo: {repo_full_name}\n\nFile tree:\n{tree_block}\n\nKey files:\n{files_block}"


def _call_model(client: OpenAI, user_prompt: str) -> str:
    response = client.chat.completions.create(
        model=config.OPENAI_MODEL,
        max_completion_tokens=config.MAX_OUTPUT_TOKENS,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )

    text = (response.choices[0].message.content or "").strip()

    # Guard against the model wrapping the whole doc in a fence anyway.
    if text.startswith("```markdown") and text.endswith("```"):
        text = text[len("```markdown"):-3].strip()
    elif text.startswith("```") and text.endswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:-3].strip()

    return text


def generate_readme(repo_full_name: str, ctx: RepoContext) -> str:
    client = OpenAI(api_key=config.OPENAI_API_KEY)
    user_prompt = _build_user_prompt(repo_full_name, ctx)

    text = _call_model(client, user_prompt)
    if len(text) < config.MIN_README_LENGTH:
        # Reasoning models occasionally burn their whole token budget on
        # hidden reasoning and return an empty/truncated visible answer.
        # One retry is usually enough; never let a blank result through.
        logger.warning(
            "%s: generation returned %d chars, retrying once", repo_full_name, len(text)
        )
        text = _call_model(client, user_prompt)

    if len(text) < config.MIN_README_LENGTH:
        raise RuntimeError(
            f"Model output too short after retry ({len(text)} chars) — refusing to commit it"
        )

    return text
