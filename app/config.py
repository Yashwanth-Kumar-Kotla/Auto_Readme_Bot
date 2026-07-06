import os

GITHUB_APP_ID = os.environ.get("GITHUB_APP_ID", "")
GITHUB_APP_PRIVATE_KEY = os.environ.get("GITHUB_APP_PRIVATE_KEY", "")
GITHUB_APP_PRIVATE_KEY_PATH = os.environ.get("GITHUB_APP_PRIVATE_KEY_PATH", "")
GITHUB_WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# gpt-5-mini: cheapest current model with strong enough reasoning/writing
# quality for README generation. Override via env var if you'd rather use
# gpt-5-nano (even cheaper, lower quality) or a full-size model.
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5-mini")

BOT_COMMIT_MARKER = "docs: auto-update README [bot]"
BOT_AUTHOR_NAME_HINTS = ("auto-readme-bot", "github-actions[bot]")

# Token budget (not bytes) for file contents sent to the model, measured
# with tiktoken so it maps directly to what we're billed for.
CONTEXT_BUDGET_TOKENS = 6_000
MAX_OUTPUT_TOKENS = 3_000

# If a push's changed files are no more than this fraction of the repo's
# visible file count, treat it as an incremental update: send the model the
# diff + existing README instead of the whole repo. Above this ratio (or on
# the first-ever run, with no README yet) it's a full regeneration.
INCREMENTAL_CHANGE_RATIO_THRESHOLD = 0.4

IGNORED_DIR_NAMES = {
    "node_modules", ".git", "venv", ".venv", "env", "__pycache__",
    "dist", "build", ".next", ".nuxt", "target", "vendor",
    ".idea", ".vscode", "coverage", ".pytest_cache", ".mypy_cache",
    "site-packages", ".terraform", ".gradle", "out",
}

IGNORED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp", ".bmp",
    ".pdf", ".zip", ".tar", ".gz", ".7z", ".rar",
    ".lock", ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".mov", ".mp3",
    ".wav", ".exe", ".dll", ".so", ".dylib", ".class", ".jar", ".pyc",
    ".bin", ".dat", ".db", ".sqlite", ".sqlite3",
}

IGNORED_FILENAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "Pipfile.lock", "Cargo.lock", "composer.lock",
}

MANIFEST_FILENAMES = {
    "package.json", "requirements.txt", "pyproject.toml", "Pipfile",
    "Gemfile", "Cargo.toml", "go.mod", "pom.xml", "build.gradle",
    "composer.json", "setup.py", "tsconfig.json",
}

ENTRY_POINT_FILENAMES = {
    "main.py", "app.py", "index.js", "index.ts", "server.js",
    "server.ts", "manage.py", "wsgi.py", "asgi.py", "cmd/main.go",
    "main.go", "Program.cs", "App.java", "Main.java",
}

README_FILENAMES = {"README.md", "README.rst", "README.txt", "README"}

MAX_FILE_SIZE_BYTES = 20_000
MAX_TREE_ENTRIES = 5000
# Cap on how many tree paths actually go into the prompt (separate from the
# cap above, which bounds internal processing). Keeps large monorepos cheap.
MAX_TREE_ENTRIES_IN_PROMPT = 300
