import re
from datetime import datetime, timezone
from src.jules.client import JulesActivity
from src.github_client.client import PRContext


def extract_review_text(activities: list) -> str:
    """Extract meaningful review text from Jules's activity list."""
    # ── Try High-Fidelity Extraction (agentMessage) ───────────────
    agent_messages = []
    for activity in activities:
        if activity.originator != "agent":
            continue
        raw = activity.raw or {}
        agent_messaged = raw.get("agentMessaged", {})
        if agent_messaged:
            msg = agent_messaged.get("agentMessage")
            if msg:
                agent_messages.append(msg)

    if agent_messages:
        return "\n\n".join(agent_messages)

    # ── Fallback: Stitch Progress Title/Description ───────────────
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


def parse_inline_suggestions(review_text: str, files_changed: list) -> list:
    """
    Parses line-level review suggestions from the generated review text.
    We search for patterns referencing files in the PR and line numbers.
    """
    suggestions = []
    if not review_text or not files_changed:
        return suggestions

    changed_files_set = set(files_changed)
    lines = review_text.split('\n')

    for i, line in enumerate(lines):
        # Look for a changed file path in the line
        found_file = None
        for f in changed_files_set:
            if f in line:
                found_file = f
                break

        if not found_file:
            continue

        # Find line number (e.g. :42 or line 42 or L42)
        line_match = re.search(r'(?:[:#]|\bline\b|\bL\b)\s*(\d+)', line, re.IGNORECASE)
        if not line_match and i + 1 < len(lines):
            # Check the next line in case it is on a separate line
            line_match = re.search(r'\b(?:line|L)?\s*(\d+)\b', lines[i+1], re.IGNORECASE)

        if line_match:
            try:
                line_num = int(line_match.group(1))
            except ValueError:
                continue

            # Extract the body of the suggestion
            body_lines = []
            cleaned_first_line = re.sub(rf'`?{re.escape(found_file)}`?', '', line)
            cleaned_first_line = re.sub(r'(?:[:#]|\bline\b|\bL\b)\s*\d+', '', cleaned_first_line, flags=re.IGNORECASE)
            cleaned_first_line = cleaned_first_line.strip(' :-*`#\t[]')

            if cleaned_first_line:
                body_lines.append(cleaned_first_line)

            # Look ahead for more explanation lines belonging to this suggestion
            j = i + 1
            while j < len(lines):
                next_line = lines[j].strip()
                if not next_line:
                    break
                if next_line.startswith('##'):
                    break
                if any(f in next_line for f in changed_files_set):
                    break
                body_lines.append(next_line.lstrip(' -*\t[]'))
                j += 1

            body = "\n".join(body_lines).strip()
            if body:
                suggestions.append({
                    "path": found_file,
                    "line": line_num,
                    "side": "RIGHT",
                    "body": f"🤖 **Jules AI Suggestion:**\n\n{body}"
                })

    return suggestions



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
