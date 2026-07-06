import hashlib
import hmac

from app import config


def verify_signature(payload_body: bytes, signature_header: str | None) -> bool:
    """Validate the X-Hub-Signature-256 header against the webhook secret."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    if not config.GITHUB_WEBHOOK_SECRET:
        return False
    expected = hmac.new(
        config.GITHUB_WEBHOOK_SECRET.encode("utf-8"), payload_body, hashlib.sha256
    ).hexdigest()
    received = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, received)
