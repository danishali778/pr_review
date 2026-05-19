import requests
from dataclasses import dataclass
from typing import Optional
from src.config.env import config
from src.utils.logger import log
from src.utils.retry import retry


@dataclass
class JulesSession:
    id: str
    name: str
    title: str
    prompt: str


@dataclass
class JulesActivity:
    id: str
    originator: str          # "agent" or "user"
    is_completed: bool
    progress_title: str
    progress_description: str
    raw: dict


class JulesClient:
    """
    Wrapper around the Jules API.
    Docs: https://developers.google.com/jules/api/reference/rest
    """

    def __init__(self) -> None:
        self.base_url = config.JULES_BASE_URL
        self.headers = {
            "X-Goog-Api-Key": config.JULES_API_KEY,
            "Content-Type": "application/json",
        }

    def _get(self, endpoint: str, params: Optional[dict] = None) -> dict:
        url = f"{self.base_url}/{endpoint}"
        response = requests.get(url, headers=self.headers, params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    def _post(self, endpoint: str, body: dict) -> dict:
        url = f"{self.base_url}/{endpoint}"
        response = requests.post(url, headers=self.headers, json=body, timeout=30)
        response.raise_for_status()
        return response.json()

    @retry(max_retries=3, base_delay=2.0)
    def list_sources(self) -> list[dict]:
        """List all GitHub repos connected to Jules."""
        log.info("Fetching connected Jules sources...")
        data = self._get("sources")
        sources = data.get("sources", [])
        log.info(f"Found {len(sources)} connected source(s)")
        return sources

    @retry(max_retries=3, base_delay=2.0)
    def create_session(
        self,
        owner: str,
        repo: str,
        branch: str,
        prompt: str,
        title: str,
    ) -> JulesSession:
        """
        Create a new Jules session to review a PR.
        Jules will read the repository at the given branch and execute the prompt.
        """
        source = f"sources/github/{owner}/{repo}"

        log.info(f"Creating Jules session for {owner}/{repo} on branch '{branch}'...")

        payload = {
            "prompt": prompt,
            "title": title,
            "sourceContext": {
                "source": source,
                "githubRepoContext": {
                    "startingBranch": branch,
                },
            },
            "automationMode": "NONE",       # Don't auto-create a PR
            "requirePlanApproval": False,   # Auto-approve Jules's plan
        }

        data = self._post("sessions", payload)

        session = JulesSession(
            id=data["id"],
            name=data["name"],
            title=data.get("title", ""),
            prompt=data.get("prompt", ""),
        )

        log.info(f"Jules session created: {session.id}")
        return session

    @retry(max_retries=3, base_delay=2.0)
    def get_activities(self, session_id: str, page_size: int = 50) -> list[JulesActivity]:
        """
        Fetch all activities for a Jules session.
        Activities are Jules's step-by-step work log.
        """
        data = self._get(
            f"sessions/{session_id}/activities",
            params={"pageSize": page_size},
        )

        activities = []
        for item in data.get("activities", []):
            progress = item.get("progressUpdated", {})
            is_completed = "sessionCompleted" in item

            activity = JulesActivity(
                id=item["id"],
                originator=item.get("originator", ""),
                is_completed=is_completed,
                progress_title=progress.get("title", ""),
                progress_description=progress.get("description", ""),
                raw=item,
            )
            activities.append(activity)

        return activities

    @retry(max_retries=3, base_delay=2.0)
    def get_session(self, session_id: str) -> dict:
        """Get the current state of a Jules session."""
        return self._get(f"sessions/{session_id}")
