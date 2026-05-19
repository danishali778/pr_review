from src.config.env import config
from src.utils.logger import log
from src.jules.client import JulesClient
from src.github_client.client import GitHubClient
from src.github_app.auth import get_installation_token
from src.review.prompt import build_review_prompt
from src.review.poller import ReviewPoller
from src.review.formatter import format_review_comment, format_error_comment


def run_review(
    owner: str,
    repo: str,
    pr_number: int,
    installation_id: int,
    is_draft: bool = False,
) -> None:
    """
    Full PR review pipeline — runs in a background thread.

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
        return

    # ── Get installation-scoped GitHub token ──────────────────────
    try:
        token = get_installation_token(installation_id)
    except Exception as e:
        log.error(f"Failed to get installation token: {e}")
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

        # ── Step 4: Poll until Jules completes ────────────────────
        activities = poller.wait_for_completion(session.id)

        # ── Step 5: Format + post review ─────────────────────────
        comment = format_review_comment(pr, activities, session.id)
        gh.post_review_comment(owner, repo, pr_number, comment)

        log.info(f"✅ Review complete: {pr.pr_url}")

    except TimeoutError as e:
        log.error(f"Review timed out for {label}: {e}")
        _post_error(gh, owner, repo, pr_number, pr,
                    f"Review timed out after {config.REVIEW_TIMEOUT_SECS}s. Please retry.")

    except Exception as e:
        log.error(f"Review failed for {label}: {e}", exc_info=True)
        _post_error(gh, owner, repo, pr_number, pr, str(e))


def _post_error(
    gh: GitHubClient,
    owner: str,
    repo: str,
    pr_number: int,
    pr,
    error: str,
) -> None:
    """Silently try to post an error comment — never raises."""
    try:
        comment = format_error_comment(pr, error)
        gh.post_issue_comment(owner, repo, pr_number, comment)
    except Exception as ex:
        log.error(f"Also failed to post error comment: {ex}")
