import hmac
import hashlib
from src.config.env import config
from src.utils.logger import log


def verify_webhook_signature(payload_bytes: bytes, signature_header: str) -> bool:
    """
    Verify that the webhook request came from GitHub by checking
    the HMAC-SHA256 signature in the X-Hub-Signature-256 header.

    GitHub signs every webhook payload with your webhook secret.
    If the signature doesn't match, the request is rejected.
    """
    if not signature_header:
        log.warning("Webhook received with no signature header")
        return False

    if not signature_header.startswith("sha256="):
        log.warning(f"Unexpected signature format: {signature_header[:20]}")
        return False

    # Compute expected signature
    expected_sig = "sha256=" + hmac.new(
        config.GITHUB_WEBHOOK_SECRET.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()

    # Use constant-time comparison to prevent timing attacks
    is_valid = hmac.compare_digest(expected_sig, signature_header)

    if not is_valid:
        log.warning("Webhook signature mismatch — possible spoofed request")

    return is_valid
