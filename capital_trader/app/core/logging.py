"""

Configure structured JSON logging using structlog.

"""
import logging
import structlog
from .config import settings

def configure_logging():
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
    )
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),            
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
    )

def get_logger(name: str):
    return structlog.get_logger(name)