from typing import Optional
from src.config.env import config
from src.utils.logger import log
from src.jules.client import JulesClient
from src.github_client.client import GitHubClient
from src.github_app.auth import get_installation_token
from src.review.prompt import build_review_prompt
from src.review.poller import ReviewPoller
from src.review.formatter import format_review_comment, format_error_comment, parse_inline_suggestions
from src.utils.db import update_job_status


def run_review(
    owner: str,
    repo: str,
    pr_number: int,
    installation_id: int,
    is_draft: bool = False,
    job_id: Optional[str] = None,
) -> None:
    """
    Full PR review pipeline — runs in a background thread or FastAPI background task.

    Flow:
      1. Get installation token for this repo
      2. Fetch PR context from GitHub
      3. Build review prompt
      4. Create Jules session
      5. Poll until Jules completes
      6. Format + post review comment on GitHub PR
    """
    label = f"{owner}/{repo}#{pr_number}"
    log.info(f"{'='*55}")
    log.info(f"🚀 Starting review: {label}")
    log.info(f"{'='*55}")

    # ── Skip draft PRs ────────────────────────────────────────────
    if is_draft and config.SKIP_DRAFT_PRS:
        log.info(f"⏭️  Skipping draft PR: {label}")
        if job_id:
            update_job_status(job_id, status="skipped")
        return

    # ── Update job status to processing ───────────────────────────
    if job_id:
        update_job_status(job_id, status="processing")

    # ── Get installation-scoped GitHub token ──────────────────────
    try:
        token = get_installation_token(installation_id)
    except Exception as e:
        log.error(f"Failed to get installation token: {e}")
        if job_id:
            update_job_status(
                job_id,
                status="failed",
                error_message=f"Failed to get installation token: {e}"
            )
        return

    gh     = GitHubClient(token)
    jules  = JulesClient()
    poller = ReviewPoller(jules)

    pr = None
    try:
        # ── Step 1: Fetch PR context ──────────────────────────────
        pr = gh.get_pr_context(owner, repo, pr_number)

        # ── Step 2: Build prompt ──────────────────────────────────
        prompt = build_review_prompt(pr)
        log.debug(f"Prompt built ({len(prompt)} chars)")

        # ── Step 3: Create Jules session ──────────────────────────
        session = jules.create_session(
            owner=owner,
            repo=repo,
            branch=pr.branch,
            prompt=prompt,
            title=f"PR Review: {pr.title[:60]}",
        )

        if job_id:
            update_job_status(job_id, status="polling", jules_session_id=session.id)

        # ── Step 4: Poll until Jules completes ────────────────────
        activities = poller.wait_for_completion(session.id)

        # ── Step 5: Format + post review ─────────────────────────
        comment = format_review_comment(pr, activities, session.id)

        # Parse inline suggestions
        inline_comments = parse_inline_suggestions(comment, pr.files_changed)
        log.info(f"Parsed {len(inline_comments)} inline suggestions out of review comment.")

        gh.post_review_comment(owner, repo, pr_number, comment, comments=inline_comments)

        if job_id:
            update_job_status(job_id, status="completed", review_markdown=comment)

        log.info(f"✅ Review complete: {pr.pr_url}")

    except TimeoutError as e:
        log.error(f"Review timed out for {label}: {e}")
        error_msg = f"Review timed out after {config.REVIEW_TIMEOUT_SECS}s. Please retry."
        _post_error(gh, owner, repo, pr_number, pr, error_msg)
        if job_id:
            update_job_status(job_id, status="failed", error_message=error_msg)

    except Exception as e:
        log.error(f"Review failed for {label}: {e}", exc_info=True)
        _post_error(gh, owner, repo, pr_number, pr, str(e))
        if job_id:
            update_job_status(job_id, status="failed", error_message=str(e))


def _post_error(
    gh: Optional[GitHubClient],
    owner: str,
    repo: str,
    pr_number: int,
    pr,
    error: str,
) -> None:
    """Silently try to post an error comment — never raises."""
    if not gh:
        return
    try:
        comment = format_error_comment(pr, error)
        gh.post_issue_comment(owner, repo, pr_number, comment)
    except Exception as ex:
        log.error(f"Also failed to post error comment: {ex}")

