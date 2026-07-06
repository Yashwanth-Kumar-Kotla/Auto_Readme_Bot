# Auto-README Bot

A GitHub App + webhook server that automatically generates and commits a README.md (including a Mermaid architecture diagram) whenever you push to any repository the app is installed on — zero per-repo setup required.

How it works (high level)
- GitHub sends a push webhook to /webhook on this service.
- The server verifies the webhook signature, checks the event is a push to the repository's default branch and that it wasn't authored by the bot.
- The app exchanges an App JWT for an installation token and queries the GitHub API (Trees + Contents) to build a token-budgeted repo context (file tree + key files).
- The context is sent to the OpenAI API to generate a README.md (raw markdown).
- If the generated README differs from the existing README.md, the bot commits it back using the Contents API with the message configured in app/config.py.

Features
- Runs as a GitHub App and responds to push events.
- Builds a concise repository context (file tree + key files) while enforcing a token budget via tiktoken.
- Generates README content with an architecture Mermaid diagram via OpenAI.
- Commits README updates via the GitHub Contents API only when changes exist.
- Configurable ignore lists, budgets and model via environment variables.

Installation

1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Create and configure the GitHub App (summary):
   - Webhook URL: https://<your-deployed-url>/webhook
   - Generate a webhook secret → set GITHUB_WEBHOOK_SECRET
   - Repository permissions → Contents: Read and write
   - Events → Push
   - Save, note the App ID, generate and download a private key (.pem)
   - Install the app on your account (choose repositories to install on)

3. Configure environment variables (copy `.env.example` to `.env` and fill):
   - GITHUB_APP_ID
   - GITHUB_APP_PRIVATE_KEY (PEM content) or GITHUB_APP_PRIVATE_KEY_PATH
   - GITHUB_WEBHOOK_SECRET
   - OPENAI_API_KEY
   - Optional: OPENAI_MODEL (defaults to `gpt-5-mini`)

Environment variables and other tunables are defined in app/config.py (e.g. BOT_COMMIT_MARKER, CONTEXT_BUDGET_TOKENS, MAX_OUTPUT_TOKENS, ignored files/dirs, etc).

Running locally
- Start the FastAPI app with uvicorn:
  ```bash
  uvicorn app.main:app --reload
  ```
- Health check: GET / returns {"status":"ok"}.

Deploy
- A Procfile and render.yaml are included for deployment to platforms like Render. After deploying, update the GitHub App's webhook URL to point at the deployed /webhook endpoint.
- This repo contains .github/workflows/keep-alive.yml which pings a provided RENDER_URL to keep a Render free-tier instance warm (optional).

Usage
- Push code to any repository where the GitHub App is installed.
- The bot will process pushes to the repository's default branch; if it generates a README different from the existing one it will commit the update with the configured BOT_COMMIT_MARKER.

Project structure (key files)
- app/main.py — FastAPI app and /webhook endpoint, orchestration of push processing.
- app/auth.py — Generate App JWT and exchange it for an installation token.
- app/security.py — HMAC-SHA256 webhook signature verification used by the webhook handler.
- app/github_api.py — Git Trees + Contents API calls (get tree, get file content, get/put README, get commit).
- app/context_builder.py — file-tree filtering, key-file selection, token-budgeted trimming (tiktoken).
- app/readme_generator.py — Builds prompts and calls the OpenAI API to create README markdown.
- app/config.py — Environment-driven config: ignored files, budgets, model, commit marker.
- requirements.txt — Python dependencies.
- Procfile, render.yaml — deployment helpers.

Architecture diagram

```mermaid
flowchart TD
  GH[GitHub push] --> M[app main]
  M --> S[security verify]
  S -- valid --> M
  M --> A[auth get token]
  A --> M
  M -->|get commit| GAPI[github api]
  GAPI --> M
  M -->|get tree| GAPI
  GAPI --> CB[context builder]
  CB -->|get file content multiple| GAPI
  CB --> RG[readme generator]
  RG --> M
  M -->|get existing readme| GAPI
  M -->|put readme if changed| GAPI
  GAPI -->|ok| M
```

Token & cost considerations (see app/config.py)
- CONTEXT_BUDGET_TOKENS: token budget for file contents sent to the model (measured with tiktoken).
- MAX_OUTPUT_TOKENS: cap on model output length.
- MAX_TREE_ENTRIES_IN_PROMPT: limit on how many file paths from the tree are included in the prompt.
- Model defaults to OPENAI_MODEL `gpt-5-mini` (override via env var).

Testing
- Push a small commit to any repo where the GitHub App is installed and check your deployment logs and the repository for an updated README.md.