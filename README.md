# Auto-README Bot

A GitHub App + webhook server that automatically generates and commits a `README.md` (including a Mermaid architecture diagram) whenever you push to any repository it's installed on — zero per-repo setup required.

## How it works (high level)

- GitHub sends a `push` webhook to /webhook on this service.
- The server verifies the webhook signature, checks the event is a push to the repository's default branch and that it wasn't authored by the bot.
- The app exchanges an App JWT for an installation token and queries the GitHub API (Trees + Contents) to build a token-budgeted repo context (file tree + key files).
- The context is sent to the OpenAI API to generate a README.md (raw markdown).
- If the generated README differs from the existing README.md, the bot commits it back using the Contents API with the message `docs: auto-update README [bot]`.

## Features

- Runs as a GitHub App and responds to push events.
- Builds a concise repository context (file tree + key files) while enforcing a token budget via tiktoken.
- Generates README content with an architecture Mermaid diagram via OpenAI.
- Commits README updates via the GitHub Contents API only when changes exist.
- Configurable ignore lists, budgets and model via environment variables.

## Installation

1. Install Python dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Create and configure the GitHub App (summary):

   - Webhook URL: `https://<your-deployed-url>/webhook`
   - Generate a webhook secret → set `GITHUB_WEBHOOK_SECRET`
   - Repository permissions → Contents: Read and write
   - Events → Push
   - Save, note the **App ID**, generate and download a private key (.pem)
   - Install the app on your account (choose "All repositories")

3. Configure environment variables (copy `.env.example` to `.env` and fill):

   - GITHUB_APP_ID
   - GITHUB_APP_PRIVATE_KEY (PEM content) or GITHUB_APP_PRIVATE_KEY_PATH
   - GITHUB_WEBHOOK_SECRET
   - OPENAI_API_KEY
   - Optional: OPENAI_MODEL (defaults to `gpt-5-mini`)

Environment variables in use are defined in app/config.py (e.g. BOT_COMMIT_MARKER, CONTEXT_BUDGET_TOKENS, MAX_OUTPUT_TOKENS, ignored files/dirs, etc.).

## Running locally

Start the FastAPI app with uvicorn:

```bash
uvicorn app.main:app --reload
```

Health check: GET / returns {"status":"ok"}.

## Deploy

A `Procfile` and `render.yaml` are included for deployment to platforms like Render. After deploying, update the GitHub App's webhook URL to point at the deployed `/webhook` endpoint.

This repo also contains `.github/workflows/keep-alive.yml` which pings a provided `RENDER_URL` to keep a Render free-tier instance warm (optional).

## Usage

- Push code to any repository where the GitHub App is installed.
- The bot will process pushes to the default branch; if it generates a README different from the existing one it will commit the update with the configured bot commit message.

## Project structure

- app/main.py — FastAPI app and `/webhook` endpoint, orchestration of push processing.
- app/auth.py — Generate App JWT and exchange it for an installation token.
- app/security.py — HMAC-SHA256 webhook signature verification.
- app/github_api.py — Git Trees + Contents API calls (get tree, get file content, get/put README, get commit).
- app/context_builder.py — file-tree filtering, key-file selection, token-budgeted trimming (tiktoken).
- app/readme_generator.py — Builds prompts and calls the OpenAI API to create README markdown.
- app/config.py — Environment-driven config: ignored files, budgets, model, commit marker.
- requirements.txt — Python dependencies.

## Architecture diagram

```mermaid
flowchart TD
  subgraph Server
    M[app/main.py: /webhook handler]
    S[app/security.py: verify_signature]
    A[app/auth.py: generate_app_jwt / get_installation_token]
    GAPI[app/github_api.py]
    CB[app/context_builder.py]
    RG[app/readme_generator.py]
  end

  GH[GitHub -> push webhook] --> M
  M --> S
  S -- valid --> M
  M --> A
  A -->|installation token| M
  M -->|get_commit| GAPI
  GAPI --> M
  M -->|get_tree| GAPI
  GAPI --> CB
  CB -->|get_file_content (multiple)| GAPI
  CB --> RG
  RG --> M
  M -->|get_existing_readme| GAPI
  M -->|put_readme (if changed)| GAPI
  GAPI -->|200 OK| M
```

Notes on the diagram:
- The webhook flow starts in app/main.py, which calls app/security.py to validate the signature.
- app/auth.py is used to obtain an installation token for GitHub API calls.
- app/github_api.py performs all GitHub REST interactions (commits, trees, contents).
- app/context_builder.py uses the tree and contents to produce the prompt context.
- app/readme_generator.py calls OpenAI with the system prompt and the repo context and returns raw markdown.

## Token & cost considerations

Configurable in app/config.py:

- CONTEXT_BUDGET_TOKENS: token budget for file contents sent to the model (measured with tiktoken).
- MAX_OUTPUT_TOKENS: cap on model output length.
- MAX_TREE_ENTRIES_IN_PROMPT: how many file paths from the tree are included in the prompt.
- Model defaults to OPENAI_MODEL `gpt-5-mini` (override via env var).

These measures keep per-run token usage predictable and low.

## Testing

Push a small commit to any repo where the GitHub App is installed and check your deployment logs and the repository for an updated README.md.

---