# 🤖 Jules PR Reviewer — Architecture & Planning Document

> A CodeRabbit-alternative powered by the Jules API that automatically reviews GitHub Pull Requests and posts structured AI feedback as PR comments.

---

## 📌 Table of Contents

1. [Project Overview](#1-project-overview)
2. [High-Level Architecture](#2-high-level-architecture)
3. [System Components](#3-system-components)
4. [Data Flow Diagrams](#4-data-flow-diagrams)
5. [Tech Stack](#5-tech-stack)
6. [Jules API Integration Design](#6-jules-api-integration-design)
7. [GitHub Integration Design](#7-github-integration-design)
8. [Database Schema](#8-database-schema)
9. [File & Project Structure](#9-file--project-structure)
10. [Security Design](#10-security-design)
11. [Configuration & Environment](#11-configuration--environment)
12. [Deployment Strategy](#12-deployment-strategy)
13. [Phased Implementation Roadmap](#13-phased-implementation-roadmap)
14. [Open Questions & Decisions](#14-open-questions--decisions)

---

## 1. Project Overview

### Goal
Build an automated PR review bot that:
- Listens for Pull Request events on GitHub
- Submits the PR to Jules (Google's AI coding agent) for intelligent review
- Posts Jules's structured review back as a GitHub PR comment/review

### Key Differentiators vs. CodeRabbit
| Feature | CodeRabbit | Jules PR Reviewer |
|---|---|---|
| AI Engine | Proprietary | Jules (Google) |
| Repo Context | Full | Full (Jules natively reads repo) |
| Code Execution | No | Yes (Jules can run tests) |
| Self-hosted | No | Yes |
| Cost | Subscription | Jules API (alpha, free?) |
| Open Source | No | Yes (your build) |

### Core User Story
> As a developer, when I open or update a Pull Request on GitHub, I want an AI agent (Jules) to automatically review my code and post a detailed, structured review comment — without me having to do anything manually.

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        GITHUB                                    │
│                                                                  │
│   Developer opens PR  ──►  Webhook Event fires                  │
└─────────────────────────────┬───────────────────────────────────┘
                              │  POST /webhook  (HMAC-signed)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   WEBHOOK SERVER (Your App)                      │
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐  │
│  │  Webhook     │    │  Background  │    │  Session Manager │  │
│  │  Handler     │───►│  (FastAPI)   │──►│  (Jules API)    │  │
│  │              │    │  Tasks Queue │    │                  │  │
│  └──────────────┘    └──────────────┘    └──────────────────┘  │
│          │                                        │             │
│          │                                        ▼             │
│          │                            ┌──────────────────────┐ │
│          │                            │  Activity Poller     │ │
│          │                            │  (polls Jules until  │ │
│          │                            │   review is done)    │ │
│          │                            └──────────┬───────────┘ │
│          │                                       │             │
│          │                                       ▼             │
│          ▼                               ┌──────────────────────┐  │
│  ┌──────────────┐                        │  Comment Formatter   │  │
│  │  SQLite DB   │                        │  + GitHub Poster     │  │
│  └──────────────┘                        └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                        JULES API                                 │
│                    (jules.googleapis.com)                        │
│                                                                  │
│   POST /sessions  →  Jules reads repo, reviews code             │
│   GET  /sessions/{id}/activities  →  Poll for completion        │
└─────────────────────────────────────────────────────────────────┘
                               │
                               │  Review output
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                        GITHUB API                                │
│                                                                  │
│   POST /repos/{owner}/{repo}/pulls/{pr}/reviews                 │
│   →  Structured review comment posted on PR                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. System Components

### 3.1 Webhook Handler
**Responsibility:** Receive and validate incoming GitHub webhook events.

- Validates HMAC-SHA256 signature from GitHub
- Parses `pull_request` events (`opened`, `synchronize`, `reopened`)
- Filters ignored branches/repos based on config
- Pushes a review job to the queue
- Returns `200 OK` immediately (async processing)

### 3.2 Job Queue
**Responsibility:** Decouple webhook receipt from slow Jules API calls.

- Uses **BullMQ** (Redis-backed) or **pg-boss** (Postgres-backed)
- Prevents timeouts on GitHub webhook delivery (30s limit)
- Supports retries on Jules API failures
- Tracks job state: `pending → processing → complete → failed`

### 3.3 Session Manager (Jules API Client)
**Responsibility:** Create and manage Jules review sessions.

- Constructs review prompt from PR metadata (title, description, branch, files changed)
- POSTs to `jules.googleapis.com/v1alpha/sessions`
- Tracks `session_id` mapped to the PR
- Handles Jules API auth (`X-Goog-Api-Key` header)

### 3.4 Activity Poller
**Responsibility:** Poll Jules until the review session completes.

- Polls `GET /sessions/{id}/activities` every N seconds
- Detects `sessionCompleted` activity type
- Extracts review content from activity artifacts
- Implements exponential backoff on errors
- Has a max-timeout ceiling (e.g., 10 minutes)

### 3.5 Comment Formatter
**Responsibility:** Transform Jules's raw activity output into a clean, structured GitHub comment.

- Parses Jules activity list
- Extracts key review findings, suggestions, and code changes
- Formats into Markdown with sections:
  - Summary
  - Issues Found
  - Suggestions
  - Code Quality Score
- Adds bot branding footer

### 3.6 GitHub Comment Poster
**Responsibility:** Post the formatted review back to GitHub.

- Uses GitHub REST API (`/pulls/{id}/reviews`)
- Posts as a PR Review with `COMMENT` event (non-blocking)
- Optionally posts inline file comments if Jules identifies specific line issues
- Updates the DB record with `posted_at` timestamp

### 3.7 Database
**Responsibility:** Track reviews, sessions, and audit history.

- Stores every review job with full lifecycle
- Enables dashboard and history features (Phase 2)
- Prevents duplicate reviews on the same commit

### 3.8 Config & Dashboard UI (Phase 2)
**Responsibility:** Web UI to manage the bot.

- Enable/disable repos
- Set review strictness level
- View review history per repo/PR
- Manage API keys

---

## 4. Data Flow Diagrams

### 4.1 Happy Path — PR Review Flow

```
1. Developer opens PR on GitHub
        │
        ▼
2. GitHub sends webhook POST to /webhook
        │
        ▼
3. Webhook Handler validates HMAC signature
   - Invalid → 401, drop
   - Valid → continue
        │
        ▼
4. Parse event: extract repo, PR number, branch, commit SHA
        │
        ▼
5. Check DB: has this commit already been reviewed?
   - Yes → skip (idempotency)
   - No → continue
        │
        ▼
6. Push Job to Queue: { repo, pr_number, branch, commit_sha }
   → Return 200 OK to GitHub immediately
        │
        ▼
7. Worker picks up job from Queue
        │
        ▼
8. Build Jules prompt:
   "Review the PR titled '{title}' on branch '{branch}'.
    Check for bugs, security issues, code quality, and suggest improvements.
    Be concise and structured."
        │
        ▼
9. POST /v1alpha/sessions to Jules API
   → Get back session_id
        │
        ▼
10. Save session_id + PR metadata to DB
        │
        ▼
11. Poll GET /sessions/{id}/activities every 15s
        │
        ├── Not done yet → wait and retry
        │
        └── sessionCompleted activity found
                │
                ▼
12. Extract review text from activities
        │
        ▼
13. Format review into structured Markdown comment
        │
        ▼
14. POST to GitHub PR Reviews API
        │
        ▼
15. Update DB record: status=completed, posted_at=now()
        │
        ▼
16. Done ✅ — Review visible on PR
```

### 4.2 Error Handling Flow

```
Jules API Failure
    │
    ├── Retry up to 3 times (exponential backoff)
    │
    └── All retries failed
            │
            ▼
    Post fallback comment to PR:
    "⚠️ Jules review could not be completed at this time."
            │
            ▼
    Mark job as FAILED in DB
            │
            ▼
    Send alert (email/Slack) to admin
```

---

## 5. Tech Stack

### Backend (FastAPI Webhook Server + CLI)

| Layer | Technology | Reason |
|---|---|---|
| **Runtime** | Python 3.10+ | Fast, clean, native standard library |
| **Framework** | **FastAPI** | High-performance, modern, async-capable framework |
| **Language** | **Python** | Dynamic, great ecosystem for LLM/AI integrations |
| **Job Queue** | **FastAPI BackgroundTasks** | Lightweight, built-in queueing, ideal for SQLite tracking |
| **HTTP Client** | **requests** / **httpx** | Simplicity in making web API requests |
| **Database** | **SQLite** + SQLAlchemy | Zero-config SQL engine, fully portable, zero external dependencies |
| **Testing** | **pytest** | Robust, standard Python unit testing framework |

### Infrastructure

| Component | Technology |
|---|---|
| **Hosting** | Railway / Render / Fly.io / VPS |
| **Database** | SQLite (persistent volume storage) |
| **CI/CD** | GitHub Actions |
| **Monitoring** | Sentry (error tracking) + standard logging |
| **Secrets Mgmt** | `.env` file + platform environment variables |

---

## 6. Jules API Integration Design

### 6.1 Authentication
```python
from src.config.env import config

jules_headers = {
    "X-Goog-Api-Key": config.JULES_API_KEY,
    "Content-Type": "application/json",
}
```

### 6.2 Session Creation Payload
```python
payload = {
    "prompt": prompt,
    "title": title,
    "sourceContext": {
        "source": f"sources/github/{owner}/{repo}",
        "githubRepoContext": {
            "startingBranch": branch,
        },
    },
    "automationMode": "NONE",
    "requirePlanApproval": False,
}
```

### 6.3 Review Prompt Template
```
You are an expert code reviewer. Review the Pull Request on branch "{branch_name}".

## Your Task:
1. Analyze all changed files in this PR
2. Identify bugs, logic errors, and edge cases
3. Flag any security vulnerabilities (SQL injection, XSS, auth issues, etc.)
...
```

### 6.4 Activity Polling Logic
```python
import time
from src.utils.retry import retry

@retry(max_retries=3, base_delay=2.0)
def wait_for_completion(session_id: str, timeout_secs = 600, poll_interval = 15):
    start = time.time()
    while time.time() - start < timeout_secs:
        activities = client.get_activities(session_id)
        completed = any(a.is_completed for a in activities)
        if completed:
            return activities
        time.sleep(poll_interval)
    raise TimeoutError("Jules review timed out")
```

### 6.5 Source Name Convention
```
sources/github/{owner}/{repo}
```

> [!IMPORTANT]
> The Jules GitHub App must be **pre-installed** on each repo you want to review. This is a manual one-time setup step per repo.

---

## 7. GitHub Integration Design

### 7.1 GitHub App vs. Personal Access Token

| Approach | Pros | Cons |
|---|---|---|
| **GitHub App** (Standard) | Multi-tenant support, fine-grained access, scalable | More setup |
| **Personal Access Token** (CLI) | Quick local setups, perfect for lightweight GitHub Actions | Bound to a single account |

**Recommendation: The project fully supports both Multi-Tenant Webhook (App) and CLI Action Mode (PAT).**

### 7.2 Webhook Setup
- Endpoint: `POST /webhook`
- Events: `Pull requests`
- Actions: `opened`, `synchronize`, `reopened`

### 7.3 HMAC Validation
```python
import hmac
import hashlib

def verify_webhook_signature(payload_bytes: bytes, signature_header: str, secret: str) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)
```

### 7.4 Posting PR Review
```python
# Using PyGithub
pr.create_review(
    body=review_comment_markdown,
    event="COMMENT",
)
```

---

## 8. Database Schema

The database tracking layers (introduced in Phase 2) use **SQLite** with **SQLAlchemy** to store review transactions, ensuring review idempotency and preventing duplicate runs on identical commit hashes.

```sql
-- Tracks every review job
CREATE TABLE review_jobs (
  id              TEXT PRIMARY KEY,              -- UUID
  repo_owner      TEXT NOT NULL,
  repo_name       TEXT NOT NULL,
  pr_number       INTEGER NOT NULL,
  pr_title        TEXT,
  branch_name     TEXT NOT NULL,
  commit_sha      TEXT NOT NULL,
  jules_session_id TEXT,
  status          TEXT NOT NULL DEFAULT 'pending',
    -- pending | processing | polling | completed | failed | skipped
  review_markdown TEXT,
  github_comment_id BIGINT,
  error_message   TEXT,
  retry_count     INTEGER DEFAULT 0,
  created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
  completed_at    DATETIME,
  UNIQUE(repo_owner, repo_name, commit_sha)
);
```

---

## 9. File & Project Structure

```
PR_review/
├── 📁 src/
│   ├── 📁 config/
│   │   └── env.py                   # Pydantic configuration loader
│   ├── 📁 github_app/
│   │   ├── auth.py                  # JWT creation & installation token exchange
│   │   └── webhook.py               # HMAC signature validation
│   ├── 📁 github_client/
│   │   └── client.py                # PyGithub wrapper client
│   ├── 📁 jules/
│   │   └── client.py                # Jules API requests client
│   ├── 📁 review/
│   │   ├── formatter.py             # Parses & formats Markdown comments
│   │   ├── orchestrator.py          # Coordinates webhook review flow
│   │   ├── poller.py                # Polls Jules session activities
│   │   └── prompt.py                # Constructs LLM review prompt
│   └── 📁 utils/
│       ├── logger.py                # Standard logger
│       └── retry.py                 # Retry and backoff decorators
│
├── .env.example                     # Environment template
├── .env                             # Real env config
├── main.py                          # CLI action entrypoint
├── server.py                        # Webhook FastAPI entrypoint
├── Procfile                         # Production startup script
├── railway.json                     # Railway deployment configuration
└── requirements.txt                 # Python dependencies
```

---

## 10. Security Design

### 10.1 Secrets Management
| Secret | Storage | Rotation |
|---|---|---|
| `JULES_API_KEY` | Env var only | Monthly (Jules alpha policy) |
| `GITHUB_TOKEN` | Env var only | Use short-lived tokens |
| `WEBHOOK_SECRET` | Env var only | On compromise |
| Database URL | Env var only | On compromise |

> [!CAUTION]
> Never commit `.env` files. Never log API keys. Add `.env` to `.gitignore` immediately.

### 10.2 Webhook Security
- ✅ Always validate `X-Hub-Signature-256` header using `crypto.timingSafeEqual`
- ✅ Reject requests without a valid signature with `401`
- ✅ Set webhook secret min 32 characters

### 10.3 Input Validation
- Validate all incoming webhook payloads with **Zod** schemas
- Sanitize PR titles/descriptions before including in Jules prompt
- Limit prompt length to avoid Jules token limits

### 10.4 Rate Limiting
- Apply rate limiting on `/webhook` endpoint (max 100 req/min per IP)
- Track GitHub API usage to stay under 5,000 req/hour

### 10.5 Network Security
- HTTPS only (TLS 1.2+)
- Webhook endpoint accessible from GitHub IP ranges only (optional allowlist)

---

## 11. Configuration & Environment

### `.env.example`
```bash
# ── Jules API ──────────────────────────────────────────────
JULES_API_KEY=your_jules_api_key_here
JULES_BASE_URL=https://jules.googleapis.com/v1alpha

# ── GitHub ─────────────────────────────────────────────────
GITHUB_TOKEN=ghp_your_personal_access_token
GITHUB_WEBHOOK_SECRET=your_32_char_random_secret

# ── Database ───────────────────────────────────────────────
DATABASE_URL=postgresql://user:password@localhost:5432/jules_reviewer

# ── Redis (Job Queue) ──────────────────────────────────────
REDIS_URL=redis://localhost:6379

# ── App ────────────────────────────────────────────────────
PORT=3000
NODE_ENV=production
LOG_LEVEL=info

# ── Review Config ──────────────────────────────────────────
REVIEW_TIMEOUT_MS=600000        # 10 minutes max wait for Jules
POLL_INTERVAL_MS=15000          # Poll Jules every 15 seconds
MAX_RETRIES=3                   # Retry failed Jules calls 3 times
SKIP_DRAFT_PRS=true             # Don't review draft PRs
```

---

## 12. Deployment Strategy

### Option A: Railway (Recommended for MVP)

```
railway up
```
- One-click Postgres + Redis add-ons
- Auto-deploy from GitHub
- Free tier available
- Custom domain + HTTPS out of the box

### Option B: Docker + VPS (Self-hosted)

```yaml
# docker-compose.yml
version: '3.8'
services:
  app:
    build: .
    ports: ["3000:3000"]
    env_file: .env
    depends_on: [redis, postgres]

  worker:
    build: .
    command: node dist/worker.js
    env_file: .env
    depends_on: [redis, postgres]

  redis:
    image: redis:7-alpine
    volumes: [redis_data:/data]

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: jules_reviewer
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes: [pg_data:/var/lib/postgresql/data]

volumes:
  redis_data:
  pg_data:
```

### Option C: GitHub Actions (Serverless / Simplest)

For MVP simplest approach — no server needed:
```yaml
# .github/workflows/jules-review.yml
on:
  pull_request:
    types: [opened, synchronize]

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - name: Jules PR Review
        uses: ./actions/jules-review
        with:
          jules_api_key: ${{ secrets.JULES_API_KEY }}
          github_token: ${{ secrets.GITHUB_TOKEN }}
```

> [!TIP]
> **Start with GitHub Actions** (Option C) for the fastest MVP. No server or infrastructure required. Migrate to Option A or B when you need history, dashboard, and multi-repo support.

---

## 13. Phased Implementation Roadmap

### Phase 1 — MVP (Week 1-2) 🎯
**Goal:** Working bot that reviews PRs and posts comments.

- [x] Project scaffold (Python 3.10+ FastAPI)
- [x] Jules API client (`create_session`, `get_activities`)
- [x] GitHub API client (`post_review_comment`, `get_pr_context`)
- [x] Webhook handler with HMAC validation
- [x] Basic review prompt template
- [x] Activity poller with timeout + backoff
- [x] Comment formatter (Markdown output)
- [x] Post review to GitHub PR
- [x] Basic error handling + logging
- [x] Deploy to Railway

**Deliverable:** Python bot reviews PRs on any repo end-to-end.

---

### Phase 2 — Reliability & Config (Week 3-4) 🔧
**Goal:** Production-ready, configurable, resilient.

- [ ] SQLite + SQLAlchemy integration for state logging
- [ ] FastAPI BackgroundTasks for queuing (async webhook response)
- [ ] Idempotency checking (skip duplicate commit reviews based on commit SHA)
- [ ] Retry logic with background workers
- [ ] Per-repo config file (`.jules-review.yml`)
- [ ] Draft PR skipping
- [ ] Branch ignore patterns
- [ ] Sentry error tracking
- [ ] Health check endpoint (`GET /health`)

**Deliverable:** Reliable, multi-repo bot with SQLite job state tracking.

---

### Phase 3 — Intelligence Upgrade (Week 5-6) 🧠
**Goal:** Smarter, more useful reviews.

- [ ] High-fidelity final artifact output parsing (extract final completed review response instead of log descriptions)
- [ ] Inline PR file comments (specific line annotations)
- [ ] Diff-aware prompting (only review changed code)
- [ ] Language-specific review rules
- [ ] Custom prompt templates per repo
- [ ] Review severity levels (minimal / standard / strict)

**Deliverable:** High-fidelity reviews with line-level comments, smarter context.

---

### Phase 4 — Dashboard & Multi-user (Week 7-8) 🖥️
**Goal:** Self-serve web UI for managing the bot.

- [ ] Next.js dashboard UI
- [ ] GitHub OAuth login
- [ ] Repo enable/disable toggle
- [ ] Review history per repo
- [ ] Metrics: avg review time, issues found, etc.
- [ ] GitHub App registration
- [ ] Public installable GitHub App

**Deliverable:** Fully self-serve tool, installable like CodeRabbit.

---

## 14. Open Questions & Decisions

> [!NOTE]
> **Q1: Persistence Database Choice — SQLite**
> We use **SQLite** as it is built directly into Python's standard library, requires zero-configuration/external hosting, and is perfect for lightweight self-hosting on persistent volumes.
> 
> **Q2: Queue / Background Worker Choice — FastAPI BackgroundTasks**
> We use FastAPI's built-in **BackgroundTasks** backed by SQLite state tracking for lightweight, zero-dependency async webhook execution.
> 
> **Q3: Multi-tenant Webhook and CLI modes**
> The codebase supports both a webhook server (multi-tenant GitHub App) and CLI Action mode (using GITHUB_TOKEN and Personal Access Tokens).

> [!NOTE]
> **Q4: Jules Alpha Limitations**
> The Jules API is in alpha. Key risks:
> - API schema may change without notice
> - Requires Jules GitHub App installed per repo (manual step)
> - Rate limits are subject to alpha pricing/limits

---

## Appendix: Jules API Quick Reference

| Endpoint | Method | Purpose |
|---|---|---|
| `/v1alpha/sources` | GET | List connected GitHub repos |
| `/v1alpha/sessions` | POST | Start a new Jules task/session |
| `/v1alpha/sessions/{id}` | GET | Get session details |
| `/v1alpha/sessions` | GET | List all sessions |
| `/v1alpha/sessions/{id}/activities` | GET | Get Jules work log |
| `/v1alpha/sessions/{id}:sendMessage` | POST | Send follow-up to Jules |
| `/v1alpha/sessions/{id}:approvePlan` | POST | Approve Jules's plan |

---

*Document version: 1.0 — Created for Jules PR Reviewer project*
*Last updated: May 2026*
