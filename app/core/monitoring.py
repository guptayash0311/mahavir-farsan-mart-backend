import logging

logger = logging.getLogger(__name__)


def configure_monitoring(dsn: str) -> None:
    if not dsn:
        return
    import sentry_sdk

    sentry_sdk.init(dsn=dsn, traces_sample_rate=0.1)
    logger.info("error tracking enabled")
