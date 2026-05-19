from src.github_client.client import PRContext


def build_review_prompt(pr: PRContext) -> str:
    """
    Build the prompt sent to Jules for reviewing a Pull Request.
    Jules will read the actual repo files on the given branch,
    so we provide PR metadata here as context.
    """

    files_list = "\n".join(f"  - {f}" for f in pr.files_changed) if pr.files_changed else "  (no files listed)"

    prompt = f"""You are an expert, senior software engineer conducting a thorough code review.

## Pull Request Details
- **Title:** {pr.title}
- **Author:** @{pr.author}
- **Branch:** `{pr.branch}` → `{pr.base_branch}`
- **PR URL:** {pr.pr_url}

## PR Description
{pr.description}

## Files Changed
{files_list}

---

## Your Code Review Task

Please review all the changed files in this Pull Request on branch `{pr.branch}` and provide a **structured, actionable review**.

### Review Checklist:
1. **Bugs & Logic Errors** — Any code that will break or behave incorrectly
2. **Security Issues** — SQL injection, XSS, auth bypass, exposed secrets, etc.
3. **Performance** — Unnecessary loops, memory leaks, N+1 queries, etc.
4. **Code Quality** — Readability, naming, complexity, duplication
5. **Edge Cases** — Inputs not handled, null/undefined cases, empty states
6. **Best Practices** — Design patterns, error handling, logging

### Output Format (use exactly this structure):

---
## 📋 Summary
[2-3 sentence high-level summary of what this PR does and your overall impression]

## 🔴 Critical Issues
[List must-fix bugs or security problems. If none, write "None found."]

## 🟡 Warnings
[List important but non-blocking issues]

## 🟢 Suggestions
[Optional improvements and best practice recommendations]

## ✅ What's Good
[Positive observations — good patterns, clean code, good test coverage, etc.]

## 📊 Score
**Code Quality: X/10**
[One sentence justification for the score]
---

Be specific. Reference file names and line numbers where possible.
Be constructive — the goal is to help the author improve the code, not to criticize.
"""

    return prompt.strip()
