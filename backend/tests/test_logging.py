from loguru import logger

from app.core.logging import configure_logging


def test_plain_loguru_logger_works_after_logging_configuration(capsys) -> None:
    configure_logging()

    logger.info("plain log test")
    logger.complete()

    captured = capsys.readouterr()
    assert "Logging error" not in captured.err
