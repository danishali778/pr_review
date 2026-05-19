"""
Jules PR Reviewer — Webhook Server

A FastAPI server that receives GitHub webhook events and triggers
Jules AI code reviews on any Pull Request from any connected repo.

How it works:
  1. You register a GitHub App and point its webhook URL here
  2. Anyone installs your GitHub App on their repo (one click)
  3. When they open a PR, GitHub sends a webhook POST to /webhook
  4. This server validates the request, then starts a Jules review
     in a background thread (returns 200 immediately to GitHub)
  5. Jules reviews the PR and the bot posts the result as a comment

Run locally:
    uvicorn server:app --reload --port 8000

Run in production:
    uvicorn server:app --host 0.0.0.0 --port $PORT
"""

import json
import threading
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse

from src.config.env import config
from src.github_app.webhook import verify_webhook_signature
from src.review.orchestrator import run_review
from src.utils.logger import log

# ── App Setup ─────────────────────────────────────────────────────
app = FastAPI(
    title="Jules PR Reviewer",
    description="AI-powered PR review bot using Jules API",
    version="2.0.0",
)

# ── Routes ────────────────────────────────────────────────────────

@app.get("/")
def root():
    """Basic info endpoint."""
    return {
        "service": "Jules PR Reviewer",
        "version": "2.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    """Health check — used by Railway/Render to verify the server is alive."""
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None),
    x_github_event: Optional[str] = Header(None),
    x_github_delivery: Optional[str] = Header(None),
):
    """
    Receives all GitHub webhook events for any repo that has your GitHub App installed.

    GitHub expects a 200 response within 10 seconds — so we:
      1. Validate the signature
      2. Parse the event
      3. Kick off the review in a BACKGROUND THREAD
      4. Return 200 immediately
    """
    payload_bytes = await request.body()
    delivery_id = x_github_delivery or "unknown"

    log.info(f"Webhook received | event={x_github_event} | delivery={delivery_id}")

    # ── 1. Validate HMAC Signature ────────────────────────────────
    if not verify_webhook_signature(payload_bytes, x_hub_signature_256 or ""):
        log.warning(f"Rejected webhook with invalid signature | delivery={delivery_id}")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # ── 2. Only handle pull_request events ───────────────────────
    if x_github_event != "pull_request":
        log.debug(f"Ignoring non-PR event: {x_github_event}")
        return JSONResponse({"status": "ignored", "reason": f"event '{x_github_event}' not handled"})

    try:
        payload = json.loads(payload_bytes)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    action = payload.get("action", "")

    # ── 3. Only handle relevant PR actions ───────────────────────
    if action not in ("opened", "synchronize", "reopened"):
        log.debug(f"Ignoring PR action: {action}")
        return JSONResponse({"status": "ignored", "reason": f"action '{action}' not handled"})

    # ── 4. Extract PR + repo info from payload ───────────────────
    pr_data   = payload.get("pull_request", {})
    repo_data = payload.get("repository", {})
    install   = payload.get("installation", {})

    owner          = repo_data.get("owner", {}).get("login", "")
    repo           = repo_data.get("name", "")
    pr_number      = pr_data.get("number", 0)
    is_draft       = pr_data.get("draft", False)
    installation_id = install.get("id", 0)

    if not all([owner, repo, pr_number, installation_id]):
        log.error("Webhook payload missing required fields")
        raise HTTPException(status_code=400, detail="Missing required payload fields")

    log.info(
        f"📬 PR event received: {owner}/{repo}#{pr_number} "
        f"| action={action} | draft={is_draft} | install={installation_id}"
    )

    # ── 5. Start review in background thread (non-blocking) ──────
    thread = threading.Thread(
        target=run_review,
        kwargs={
            "owner":           owner,
            "repo":            repo,
            "pr_number":       pr_number,
            "installation_id": installation_id,
            "is_draft":        is_draft,
        },
        name=f"review-{owner}-{repo}-{pr_number}",
        daemon=True,  # Thread dies if server dies
    )
    thread.start()

    log.info(f"🚀 Review thread started for {owner}/{repo}#{pr_number}")

    # ── 6. Return 200 immediately to GitHub ──────────────────────
    return JSONResponse({
        "status": "accepted",
        "message": f"Review started for {owner}/{repo}#{pr_number}",
    })
