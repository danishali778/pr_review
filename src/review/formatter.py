from datetime import datetime, timezone
from src.jules.client import JulesActivity
from src.github_client.client import PRContext


def extract_review_text(activities: list) -> str:
    """Extract meaningful review text from Jules's activity list."""
    review_parts = []

    skip_keywords = ["npm install", "Installing", "Setup the environment", "bash command"]

    for activity in activities:
        if activity.originator != "agent":
            continue
        if not activity.progress_title and not activity.progress_description:
            continue

        title = activity.progress_title or ""
        if any(kw.lower() in title.lower() for kw in skip_keywords):
            continue

        if activity.progress_description:
            review_parts.append(activity.progress_description)
        elif activity.progress_title:
            review_parts.append(activity.progress_title)

    return "\n\n".join(review_parts) if review_parts else ""


def format_review_comment(
    pr: PRContext,
    activities: list,
    session_id: str,
) -> str:
    """Format Jules's activity output into a polished GitHub PR comment."""
    review_text = extract_review_text(activities)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    files_list = ", ".join(f"`{f}`" for f in pr.files_changed[:10])
    if len(pr.files_changed) > 10:
        files_list += f" _(and {len(pr.files_changed) - 10} more)_"

    # Use review text directly if it has our structured format markers
    if review_text and any(
        marker in review_text
        for marker in ["## 📋", "## 🔴", "## 🟡", "## 🟢", "## ✅", "## 📊",
                       "Critical", "Summary", "Score"]
    ):
        body = review_text
    else:
        body = f"""## 📋 Summary
{review_text or "_Jules completed the review but did not produce structured output._"}"""

    return f"""## 🤖 Jules AI Code Review

> **PR:** [{pr.title}]({pr.pr_url})
> **Author:** @{pr.author} | **Branch:** `{pr.branch}` → `{pr.base_branch}`
> **Files reviewed:** {files_list}

---

{body}

---

<details>
<summary>ℹ️ About this review</summary>

This review was generated automatically by **Jules AI** via the Jules PR Reviewer.
- 🔗 Jules Session: `{session_id}`
- 🕒 Generated at: {timestamp}
- 📖 [Jules API Docs](https://developers.google.com/jules/api/reference/rest)

_Jules is an AI agent — please verify suggestions before applying them._
</details>""".strip()


def format_error_comment(pr, error: str) -> str:
    """Format a fallback comment when Jules review fails."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    pr_info = f" for [{pr.title}]({pr.pr_url})" if pr else ""

    return f"""## 🤖 Jules AI Code Review

⚠️ **The automated review could not be completed{pr_info}.**

**Reason:** `{error}`

Please re-open the PR or push a new commit to trigger a retry.

---
<sub>Jules PR Reviewer | {timestamp}</sub>""".strip()
