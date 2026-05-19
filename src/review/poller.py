import time
from src.jules.client import JulesClient, JulesActivity
from src.config.env import config
from src.utils.logger import log


class ReviewPoller:
    """
    Polls Jules for session completion by watching activities.
    Uses exponential-ish backoff to avoid hammering the API.
    """

    def __init__(self, client: JulesClient) -> None:
        self.client = client

    def wait_for_completion(self, session_id: str) -> list[JulesActivity]:
        """
        Poll Jules activities until sessionCompleted is found.
        Returns the full list of activities when done.

        Raises TimeoutError if Jules doesn't finish within REVIEW_TIMEOUT_SECS.
        """
        timeout_secs = config.REVIEW_TIMEOUT_SECS
        poll_interval = config.POLL_INTERVAL_SECS

        start_time = time.time()
        attempt = 0

        log.info(
            f"Polling Jules session '{session_id}' "
            f"(timeout: {timeout_secs}s, interval: {poll_interval}s)..."
        )

        while True:
            elapsed = time.time() - start_time

            if elapsed >= timeout_secs:
                raise TimeoutError(
                    f"Jules review timed out after {timeout_secs}s "
                    f"for session {session_id}"
                )

            attempt += 1
            log.debug(f"Poll attempt #{attempt} | Elapsed: {elapsed:.0f}s")

            try:
                activities = self.client.get_activities(session_id)
            except Exception as e:
                log.warning(f"Failed to fetch activities (will retry): {e}")
                time.sleep(poll_interval)
                continue

            # Log latest progress
            agent_activities = [a for a in activities if a.originator == "agent"]
            if agent_activities:
                latest = agent_activities[-1]
                if latest.progress_title:
                    log.info(f"Jules progress: {latest.progress_title}")

            # Check if session is complete
            completed = next((a for a in activities if a.is_completed), None)
            if completed:
                log.info(
                    f"✅ Jules session completed after {elapsed:.0f}s "
                    f"with {len(activities)} activities"
                )
                return activities

            # Adaptive interval: slow down polling over time
            # 15s → 20s → 25s → max 30s
            adaptive_interval = min(poll_interval + (attempt * 2), 30)
            log.debug(f"Not completed yet. Next poll in {adaptive_interval}s...")
            time.sleep(adaptive_interval)
