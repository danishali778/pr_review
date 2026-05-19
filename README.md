# 🤖 Jules PR Reviewer (FastAPI Server + GitHub App)

> A generic, automated Pull Request review bot powered by [Jules AI](https://jules.google) (Google's AI coding agent).
> Rebuilt to work exactly like **CodeRabbit**: **Install once, use everywhere.**

When you register this GitHub App and point it to your deployed FastAPI server, anyone can install it on their repositories. Whenever a PR is opened or updated on any installed repo, this bot automatically:
1. Receives the GitHub webhook event on your central server.
2. Exchanges the app credentials for an installation access token.
3. Automatically starts a Jules AI session context for that PR's branch.
4. Formats and posts the review comments directly under the PR!

---

## 🏗️ Architecture

```
PR Opened on Repo ──► Webhook (HMAC-Signed) ──► FastAPI Server ──► Jules API
                                                                     │
                                                                     ▼
                                                             GitHub PR Comment ◄──
```

| File / Folder | Purpose |
|---|---|
| `server.py` | FastAPI server that accepts and validates GitHub Webhooks |
| `src/github_app/auth.py` | Handles App authentication via JWT & installation token exchange |
| `src/github_app/webhook.py` | Validates HMAC-SHA256 signatures of incoming webhooks |
| `src/github_client/client.py` | Token-agnostic GitHub API client wrapper |
| `src/review/orchestrator.py` | Background worker that orchestrates the PR context, prompt construction, Jules session, polling, and posting reviews |
| `src/review/prompt.py` | Prompt construction specifically structured for high-quality code reviews |
| `src/jules/client.py` | Jules REST API Wrapper (`googleapis.com`) |
| `railway.json` / `Procfile` | Configuration for zero-downtime deployment on Railway |

---

## 🚀 Setup Guide

To get this running, please check out the step-by-step setup guides:

1. **[GitHub App Setup Guide](./docs/github_app_setup.md)**: Steps to register your app, configure webhook subscriptions, and generate private key `.pem` certificates.
2. **Local Development Setup**: Follow instructions below to test locally using ngrok.

---

## 🛠️ Local Development

### 1. Configure `.env`
Copy the `.env.example` file to `.env` and fill out your variables:
```bash
cp .env.example .env
```
Ensure you have:
* `GITHUB_APP_ID`: From your GitHub App setting page.
* `GITHUB_APP_PRIVATE_KEY`: Your downloaded PEM key. (Newline chars inside the PEM block should be formatted as `\n` if written on a single line).
* `GITHUB_WEBHOOK_SECRET`: Secure string you generated.
* `JULES_API_KEY`: Obtained from [Jules settings](https://jules.google.com/settings#api).

### 2. Expose Port via Ngrok (or Similar Proxy)
GitHub needs a public URL to send webhooks to. Run:
```bash
ngrok http 8000
```
Update your GitHub App configuration with the ngrok URL (e.g. `https://xxxx.ngrok-free.app/webhook`).

### 3. Run FastAPI Server
Activate your virtual environment and start the development server:
```bash
source .venv/bin/activate
uvicorn server:app --reload --port 8000
```

---

## 📦 Production Deployment (Railway / Render)

This project is pre-configured for **Railway** deployment out of the box using NIXPACKS:

1. Connect your GitHub repository containing this codebase to Railway.
2. Define the required environment variables in the Railway dashboard (`GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY`, `GITHUB_WEBHOOK_SECRET`, `JULES_API_KEY`).
3. Deploy! Railway will automatically detect `Procfile` and spin up your FastAPI container.

---

## ⚙️ Configuration Parameters

You can customize the review behavior inside `.env` or your production container's variables:

| Variable | Default | Description |
|---|---|---|
| `REVIEW_TIMEOUT_SECS` | `600` | Maximum time to poll Jules before timing out (10 minutes) |
| `POLL_INTERVAL_SECS` | `15` | Polling rate to check for completed Jules reviews |
| `MAX_RETRIES` | `3` | Number of times to retry failed requests on Jules API |
| `SKIP_DRAFT_PRS` | `true` | When set to `true`, ignores reviews on Draft Pull Requests |

---

## 📄 License
MIT
