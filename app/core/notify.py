import logging

logger = logging.getLogger("app.notifications")


def deliver(channel: str, recipient: str, subject: str, body: str) -> None:
    logger.info(
        "notification channel=%s recipient=%s subject=%s body=%s",
        channel,
        recipient,
        subject,
        body,
    )
