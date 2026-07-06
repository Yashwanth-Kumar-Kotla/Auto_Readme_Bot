# Auto-README Bot

A GitHub App + webhook server that automatically generates and commits a README.md (including a Mermaid architecture diagram) whenever you push to any repository the App is installed on — zero per-repo setup required.

## Description

On each push to a repository's default branch the App:
- Verifies the webhook HMAC signature.
- Fetches the repository tree and a small selection of "key" files (no local git clone).
- Builds a token-budgeted context and asks OpenAI to generate a README.md that reflects the repo structure.
- Commits README.md back via the GitHub Contents API if it changed.

Designed to keep per-run OpenAI usage predictable (token budgets, tree caps, small system prompt).

## Features

- FastAPI webhook endpoint (/webhook) for GitHub push events.
- GitHub App authentication (App JWT -> installation token).
- Tree + file fetching via Git Trees & Contents APIs (no clones).
- Token-aware context trimming using tiktoken.
- OpenAI-driven README generation with a Mermaid architecture diagram.
- Safe no-op guards: skip when commit was made by the bot or README is unchanged.

## Installation

1. Create a virtual environment (optional) and install deps:

```bash
pip install -r requirements.txt
```

2. Copy environment template and set required vars:

- Copy `.env.example` -> `.env`
- Set:
  - GITHUB_APP_ID
  - GITHUB_APP_PRIVATE_KEY (PEM content) or GITHUB_APP_PRIVATE_KEY_PATH
  - GITHUB_WEBHOOK_SECRET
  - OPENAI_API_KEY
  - (Optional) OPENAI_MODEL — defaults to `gpt-5-mini`

Env vars used are defined in app/config.py.

## Run locally

Start the FastAPI app:

```bash
uvicorn app.main:app --reload
```

Health check: GET / returns {"status":"ok"}  
Webhook endpoint: POST /webhook

## Deploy

- A `Procfile` and `render.yaml` are included for simple deployment to platforms like Render or Railway.
- When deployed, set the same environment variables in your platform's dashboard.
- Configure your GitHub App's Webhook URL to point to: https://<your-deployed-url>/webhook

## Keep-alive (Render free tier)

This repo contains `.github/workflows/keep-alive.yml` which pings a `RENDER_URL` periodically. To use it:
1. Add a GitHub Actions repository secret named `RENDER_URL` with your deployed URL (no trailing slash).
2. The workflow will keep your Render service warm.

## Usage

1. Create a GitHub App (GitHub → Developer settings → GitHub Apps):
   - Webhook URL: https://<your-deployed-url>/webhook
   - Webhook secret → GITHUB_WEBHOOK_SECRET
   - Permissions: Contents: Read & write
   - Subscribe to: Push events
2. Install the App on your account/org, choosing "All repositories".
3. Push to a repo's default branch. The App will process the push and may update README.md.

## Project structure

- app/main.py — FastAPI app, /webhook endpoint, push-event orchestration
- app/auth.py — GitHub App JWT signing + installation token exchange
- app/security.py — HMAC-SHA256 webhook signature verification
- app/github_api.py — Git Trees & Contents API calls (fetch + commit)
- app/context_builder.py — file tree filtering, key-file selection, tiktoken-based trimming
- app/readme_generator.py — OpenAI prompt construction + API call
- app/config.py — env vars and filtering/token-budget config

## Important configuration knobs (app/config.py)

- CONTEXT_BUDGET_TOKENS — token budget for file contents sent to the model
- MAX_OUTPUT_TOKENS — cap for OpenAI output
- MAX_TREE_ENTRIES_IN_PROMPT — file-tree lines included in prompt
- IGNORED_DIR_NAMES / IGNORED_EXTENSIONS / IGNORED_FILENAMES — filters for what to skip
- BOT_COMMIT_MARKER, BOT_AUTHOR_NAME_HINTS — used to detect and skip self-triggered commits

## Architecture diagram

```mermaid
flowchart TD
  A[git push to repo] --> B[GitHub sends push webhook]
  B --> C[/webhook (app/main.py)]
  C --> D{security.verify_signature<br/>app/security.py}
  D -- invalid --> Z[401]
  D -- valid --> E{event == "push" and default branch?}
  E -- no --> Y[200 ignored]
  E -- yes --> F[auth.get_installation_token<br/>app/auth.py]
  F --> G[github_api.get_commit<br/>app/github_api.py]
  G --> H{_is_bot_commit? (app/main.py)}
  H -- bot commit --> Y
  H -- not bot --> I[context_builder.build_repo_context<br/>app/context_builder.py]
  I --> J[github_api.get_tree & get_file_content<br/>app/github_api.py]
  J --> I
  I --> K[readme_generator.generate_readme<br/>app/readme_generator.py]
  K --> L[OpenAI API (openai client)]
  L --> K
  K --> M[github_api.get_existing_readme<br/>app/github_api.py]
  M --> N{diff vs existing README}
  N -- unchanged --> Y
  N -- changed --> O[github_api.put_readme -> commit README.md<br/>app/github_api.py]
  O --> P[200 processed / logs]
  Y --> P
  Z --> P
```

Keep README generation rules and token budgets adjustable in app/config.py.

## Files of note

- requirements.txt — runtime dependencies (fastapi, uvicorn, httpx, PyJWT, cryptography, openai, tiktoken, python-dotenv)
- Procfile, render.yaml — example deploy configs
- .github/workflows/keep-alive.yml — optional Action to keep Render free tier awake

## Testing

Install the App on a test repository and push a small commit to its default branch. Check your deployed service logs for processing and the repository for README.md updates.