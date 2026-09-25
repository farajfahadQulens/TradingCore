"""

Runtime trading state and mode enumeration.

"""
from enum import Enum
import structlog

log = structlog.get_logger(__name__)


class TradingMode(str, Enum):
    OBSERVE_ONLY = "observe"
    PAPER_TRADING = "paper"
    LIVE_TRADING = "live"
    DEGRADED = "degraded"
    SHUTDOWN = "shutdown"

class TradingState:
    
    def __init__(self, mode: TradingMode = TradingMode.OBSERVE_ONLY) -> None:
        self.mode = TradingMode.OBSERVE_ONLY

    def disable_trading(self, reason: str) -> None:
        self.mode = TradingMode.DEGRADED
        log.warning("trading_disabled", reason=reason)


    def enable_trading(self) -> None:
        self.mode = TradingMode.LIVE_TRADING
        log.info("trading_enabled")

    def set_degraded(self, reason: str) -> None:
        self.mode = TradingMode.DEGRADED
        log.warning("trading_degraded", reason=reason)

    def shutdown(self) -> None:
        self.mode = TradingMode.SHUTDOWN
        log.warning("trading_shutdown")
    @property
    def is_trading_allowed(self) -> bool:
        return self.mode in (TradingMode.PAPER_TRADING, TradingMode.LIVE_TRADING)
    

trading_state = TradingState()


