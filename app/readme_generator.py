import logging

from openai import OpenAI

from app import config
from app.context_builder import RepoContext

logger = logging.getLogger("auto_readme_bot.readme_generator")

# Kept short deliberately: this is sent on every single call, so every extra
# line here is a recurring token cost across every repo/push.
SYSTEM_PROMPT = """Generate a README.md for a repo from the file tree and file contents given.

Output ONLY raw markdown. No preamble, no wrapping code fence around the whole doc.

Rules:
- Base everything on the given files only. Never invent features, deps, or behavior not evidenced.
- Include install/usage instructions inferred from the actual manifest/entry files given.
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
    return f"Repo: {repo_full_name}\n\nFile tree:\n{tree_block}\n\nKey files:\n{files_block}"


def generate_readme(repo_full_name: str, ctx: RepoContext) -> str:
    client = OpenAI(api_key=config.OPENAI_API_KEY)
    user_prompt = _build_user_prompt(repo_full_name, ctx)

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
