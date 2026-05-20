import sqlite3
import uuid
import os
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from src.config.env import config
from src.utils.logger import log


def get_connection() -> sqlite3.Connection:
    """Get a connection to the SQLite database."""
    # We open/close connections on demand to avoid thread sharing issues in FastAPI
    conn = sqlite3.connect(config.DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize the SQLite database schema."""
    log.info(f"Initializing SQLite database at: {os.path.abspath(config.DATABASE_PATH)}")
    
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS review_jobs (
        id TEXT PRIMARY KEY,
        repo_owner TEXT NOT NULL,
        repo_name TEXT NOT NULL,
        pr_number INTEGER NOT NULL,
        pr_title TEXT,
        branch_name TEXT NOT NULL,
        commit_sha TEXT NOT NULL,
        jules_session_id TEXT,
        status TEXT NOT NULL, -- pending | processing | polling | completed | failed | skipped
        review_markdown TEXT,
        error_message TEXT,
        created_at TEXT NOT NULL,
        completed_at TEXT,
        UNIQUE(repo_owner, repo_name, commit_sha)
    );
    """
    
    with get_connection() as conn:
        conn.execute(create_table_sql)
        conn.commit()
    log.info("SQLite database tables verified/created successfully.")


def get_job_by_commit(owner: str, repo: str, commit_sha: str) -> Optional[Dict[str, Any]]:
    """Fetch a review job by owner, repo, and commit SHA to support idempotency checks."""
    query = """
    SELECT * FROM review_jobs
    WHERE repo_owner = ? AND repo_name = ? AND commit_sha = ?
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, (owner, repo, commit_sha))
        row = cursor.fetchone()
        return dict(row) if row else None


def create_job(
    owner: str,
    repo: str,
    pr_number: int,
    pr_title: str,
    branch_name: str,
    commit_sha: str
) -> str:
    """Insert a new pending review job into the database and return its UUID."""
    job_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    
    insert_sql = """
    INSERT INTO review_jobs (
        id, repo_owner, repo_name, pr_number, pr_title, branch_name, commit_sha, status, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
    """
    
    with get_connection() as conn:
        conn.execute(
            insert_sql,
            (job_id, owner, repo, pr_number, pr_title, branch_name, commit_sha, created_at)
        )
        conn.commit()
    
    log.debug(f"Created SQLite database job record | job_id={job_id} | commit={commit_sha[:8]}")
    return job_id


def update_job_status(
    job_id: str,
    status: str,
    error_message: Optional[str] = None,
    jules_session_id: Optional[str] = None,
    review_markdown: Optional[str] = None
) -> None:
    """Update status, error messages, and completed timestamp of a review job."""
    completed_at = None
    if status in ("completed", "failed", "skipped"):
        completed_at = datetime.now(timezone.utc).isoformat()

    updates = ["status = ?"]
    params = [status]

    if error_message is not None:
        updates.append("error_message = ?")
        params.append(error_message)

    if jules_session_id is not None:
        updates.append("jules_session_id = ?")
        params.append(jules_session_id)

    if review_markdown is not None:
        updates.append("review_markdown = ?")
        params.append(review_markdown)

    if completed_at is not None:
        updates.append("completed_at = ?")
        params.append(completed_at)

    params.append(job_id)
    update_sql = f"UPDATE review_jobs SET {', '.join(updates)} WHERE id = ?"

    with get_connection() as conn:
        conn.execute(update_sql, tuple(params))
        conn.commit()

    log.debug(f"Updated SQLite database job record | job_id={job_id} | status={status}")


def reset_job_to_pending(job_id: str) -> None:
    """Reset a failed or skipped job back to pending status for retrying."""
    now = datetime.now(timezone.utc).isoformat()
    query = """
    UPDATE review_jobs
    SET status = 'pending',
        error_message = NULL,
        jules_session_id = NULL,
        review_markdown = NULL,
        completed_at = NULL,
        created_at = ?
    WHERE id = ?
    """
    with get_connection() as conn:
        conn.execute(query, (now, job_id))
        conn.commit()

    log.debug(f"Reset SQLite database job record to pending | job_id={job_id}")

