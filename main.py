"""
Jules PR Reviewer — Main Entrypoint

This script is called by GitHub Actions when a PR is opened or updated.
It orchestrates the full review flow:
  1. Fetch PR context from GitHub
  2. Build a review prompt
  3. Create a Jules session
  4. Poll until Jules completes the review
  5. Post the formatted review as a GitHub PR comment

Usage (called by GitHub Actions):
    python main.py --owner <owner> --repo <repo> --pr <pr_number>

Or via environment variables (set by GitHub Actions automatically):
    REPO_OWNER, REPO_NAME, PR_NUMBER
"""

import sys
import argparse
import os
from typing import Optional

from src.config.env import config
from src.utils.logger import log
from src.utils.db import init_db
from src.jules.client import JulesClient
from src.github_client.client import GitHubClient
from src.review.prompt import build_review_prompt
from src.review.poller import ReviewPoller
from src.review.formatter import format_review_comment, format_error_comment


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Jules PR Reviewer")
    parser.add_argument("--owner", default=os.getenv("REPO_OWNER"), help="GitHub repo owner")
    parser.add_argument("--repo",  default=os.getenv("REPO_NAME"),  help="GitHub repo name")
    parser.add_argument("--pr",    default=os.getenv("PR_NUMBER"),   help="PR number", type=int)
    parser.add_argument("--token", default=os.getenv("GITHUB_TOKEN"),  help="GitHub Personal Access Token or Action Token")
    return parser.parse_args()


def run(owner: str, repo: str, pr_number: int, token: Optional[str] = None) -> None:
    log.info("=" * 60)
    log.info(f"🚀 Jules PR Reviewer starting")
    log.info(f"   Repo:  {owner}/{repo}")
    log.info(f"   PR:    #{pr_number}")
    log.info("=" * 60)

    # ── Resolve GitHub Token ──────────────────────────────────────
    resolved_token = token or config.GITHUB_TOKEN
    if not resolved_token:
        log.error(
            "❌ GitHub token not provided. Please provide --token, "
            "set GITHUB_TOKEN environment variable, or define GITHUB_TOKEN in your .env file."
        )
        sys.exit(1)

    gh_client    = GitHubClient(resolved_token)
    jules_client = JulesClient()
    poller       = ReviewPoller(jules_client)

    # ── Step 1: Fetch PR context ──────────────────────────────────
    pr = gh_client.get_pr_context(owner, repo, pr_number)

    # ── Step 2: Skip draft PRs if configured ─────────────────────
    if pr.is_draft and config.SKIP_DRAFT_PRS:
        log.info("⏭️  PR is a draft — skipping review (SKIP_DRAFT_PRS=true)")
        return

    # ── Step 3: Build prompt ──────────────────────────────────────
    prompt = build_review_prompt(pr)
    log.debug(f"Prompt built ({len(prompt)} chars)")

    # ── Step 4: Create Jules session ──────────────────────────────
    session_title = f"PR Review: {pr.title[:60]}"
    session = jules_client.create_session(
        owner=owner,
        repo=repo,
        branch=pr.branch,
        prompt=prompt,
        title=session_title,
    )

    # ── Step 5: Poll until Jules completes ────────────────────────
    try:
        activities = poller.wait_for_completion(session.id)
    except TimeoutError as e:
        log.error(str(e))
        error_comment = format_error_comment(pr, f"Review timed out after {config.REVIEW_TIMEOUT_SECS}s")
        gh_client.post_issue_comment(owner, repo, pr_number, error_comment)
        sys.exit(1)

    # ── Step 6: Format & post review ─────────────────────────────
    review_comment = format_review_comment(pr, activities, session.id)
    gh_client.post_review_comment(owner, repo, pr_number, review_comment)

    log.info("=" * 60)
    log.info("✅ Review complete! Check the PR for Jules's feedback.")
    log.info(f"   PR URL: {pr.pr_url}")
    log.info("=" * 60)


def main() -> None:
    init_db()
    args = parse_args()

    if not args.owner or not args.repo or not args.pr:
        print("❌ Error: --owner, --repo, and --pr are required.")
        print("   Or set REPO_OWNER, REPO_NAME, PR_NUMBER environment variables.")
        sys.exit(1)

    try:
        run(args.owner, args.repo, int(args.pr), args.token)
    except KeyboardInterrupt:
        log.info("Interrupted by user.")
        sys.exit(0)
    except Exception as e:
        log.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
