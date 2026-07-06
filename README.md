# Auto-README Bot

A GitHub App webhook server that generates and commits a README.md (including a Mermaid architecture diagram) whenever a push is made to any repository the app is installed on. The service verifies the webhook, builds a token budgeted repo context, asks OpenAI to synthesize a README, and commits the result only when it differs from the repository README.

## Features
- Runs as a GitHub App and responds to push events.
- Verifies webhook signatures with HMAC SHA256.
- Exchanges an App JWT for an installation token and uses the GitHub API for Trees and Contents.
- Builds a concise repo context (file tree + selected key files) with a tiktoken token budget.
- Generates README content (markdown) with an architecture Mermaid diagram via the OpenAI API.
- Commits README updates via the GitHub Contents API only when the generated content differs.
- Configurable ignore lists, budgets, and model via environment variables.

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Create and configure a GitHub App:
- Webhook URL: https://<your-deployed-url>/webhook
- Set a webhook secret and configure repository Contents read and write permission.
- Subscribe to Push events.
- Save the App ID and download the private key (.pem).
- Install the app on the target repositories.

3. Configure environment variables:
- Copy `.env.example` to `.env` and fill in required values, or set env vars directly.
Required env vars referenced in app/config.py and other modules:
- GITHUB_APP_ID
- GITHUB_APP_PRIVATE_KEY (PEM content) or GITHUB_APP_PRIVATE_KEY_PATH
- GITHUB_WEBHOOK_SECRET
- OPENAI_API_KEY
Optional:
- OPENAI_MODEL (defaults to `gpt-5-mini`)

Environment-driven tunables in app/config.py include BOT_COMMIT_MARKER, CONTEXT_BUDGET_TOKENS, MAX_OUTPUT_TOKENS, ignore lists, and more.

## Running locally
Start the FastAPI app with uvicorn:
```bash
uvicorn app.main:app --reload
```
Health check: GET / returns {"status":"ok"}.

## Deployment
- A Procfile and render.yaml are included for deployment to platforms like Render.
- After deploying, update the GitHub App webhook URL to point to the deployed /webhook endpoint.
- The repository includes .github/workflows/keep-alive.yml to optionally ping a RENDER_URL to keep a Render free tier instance warm.

## Usage
- Push code to any repository where the GitHub App is installed.
- The bot processes pushes to the repository default branch. It will:
  - Verify webhook signature and event type.
  - Skip pushes authored by the bot itself (checks commit message marker and author hints).
  - Build a repo context from the git tree and selected files up to a token budget.
  - Generate a README via OpenAI.
  - Compare with the existing README and commit the update if it differs.

Commit marker and bot author hints are configured in app/config.py (BOT_COMMIT_MARKER and BOT_AUTHOR_NAME_HINTS).

## Project structure
- app/main.py — FastAPI app, /webhook endpoint, and push orchestration.
- app/auth.py — Generate App JWT and exchange it for an installation token.
- app/security.py — HMAC SHA256 webhook signature verification used by the webhook handler.
- app/github_api.py — Git Trees and Contents API calls (get tree, get file content, get/put README, get commit).
- app/context_builder.py — File tree filtering, key file selection, token budget trimming using tiktoken.
- app/readme_generator.py — Builds prompts and calls the OpenAI API to create README markdown.
- app/config.py — Environment driven configuration: ignored files, budgets, model, commit marker.
- requirements.txt — Python dependencies.
- Procfile, render.yaml — deployment helpers.
- .github/workflows/keep-alive.yml — optional keep alive pinger for Render deployments.

## Architecture diagram

```mermaid
flowchart TD
  GH[GitHub Push] --> M[App Main Webhook]
  M --> S[Security Verify]
  S --> A[Auth Get Token]
  A --> G[GitHub Fetch Commit And Tree]
  G --> C[Context Builder]
  C --> O[OpenAI Readme Generator]
  O --> E[Compare Existing Readme]
  E --> P[GitHub Put Readme Commit]
```

## Token and cost considerations
- CONTEXT_BUDGET_TOKENS controls how many model tokens of file contents are sent (measured with tiktoken).
- MAX_OUTPUT_TOKENS caps model output length.
- MAX_TREE_ENTRIES_IN_PROMPT limits how many file paths from the tree are included in the prompt.
- Default model is OPENAI_MODEL `gpt-5-mini` (override via env var).

## Testing
- Push a small commit to any repo where the GitHub App is installed and check deployment logs and the repository for an updated README.md.