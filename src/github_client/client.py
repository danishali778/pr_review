from typing import Optional
from dataclasses import dataclass
from github import Github, PullRequest
from src.utils.logger import log


@dataclass
class PRContext:
    """All the information we need about a PR to review it."""
    owner: str
    repo: str
    pr_number: int
    title: str
    description: str
    branch: str
    base_branch: str
    commit_sha: str
    author: str
    is_draft: bool
    files_changed: list
    diff_url: str
    pr_url: str


class GitHubClient:
    """
    GitHub API wrapper.
    Accepts any token — works with both:
      - GitHub App installation tokens (get_installation_token())
      - Personal Access Tokens (for local CLI testing)
    """

    def __init__(self, token: str) -> None:
        self._gh = Github(token)

    def get_pr_context(self, owner: str, repo: str, pr_number: int) -> PRContext:
        """Fetch all context needed about a pull request."""
        log.info(f"Fetching PR context for {owner}/{repo}#{pr_number}...")

        repository = self._gh.get_repo(f"{owner}/{repo}")
        pr: PullRequest = repository.get_pull(pr_number)
        files_changed = [f.filename for f in pr.get_files()]

        context = PRContext(
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            title=pr.title,
            description=pr.body or "(no description provided)",
            branch=pr.head.ref,
            base_branch=pr.base.ref,
            commit_sha=pr.head.sha,
            author=pr.user.login,
            is_draft=pr.draft,
            files_changed=files_changed,
            diff_url=pr.diff_url,
            pr_url=pr.html_url,
        )

        log.info(
            f"PR fetched: '{pr.title}' by @{pr.user.login} "
            f"({len(files_changed)} file(s) changed)"
        )
        return context

    def post_review_comment(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        review_body: str,
        comments: Optional[list[dict]] = None,
    ) -> str:
        """Post a structured review comment on a PR (shows in Reviews section) with optional inline comments."""
        log.info(f"Posting review on {owner}/{repo}#{pr_number}...")

        repository = self._gh.get_repo(f"{owner}/{repo}")
        pr: PullRequest = repository.get_pull(pr_number)

        kwargs = {
            "body": review_body,
            "event": "COMMENT"
        }
        if comments:
            kwargs["comments"] = comments

        pr.create_review(**kwargs)

        log.info(f"✅ Review posted with {len(comments) if comments else 0} inline comments: {pr.html_url}")
        return pr.html_url

    def post_issue_comment(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        body: str,
    ) -> None:
        """Post a plain comment (used for error/fallback messages)."""
        repository = self._gh.get_repo(f"{owner}/{repo}")
        pr: PullRequest = repository.get_pull(pr_number)
        pr.create_issue_comment(body)
        log.info(f"Posted issue comment on {owner}/{repo}#{pr_number}")
