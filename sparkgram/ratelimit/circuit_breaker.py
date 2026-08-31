"""
Circuit Breaker and Adaptive Backoff for SparkGram.
Protects bot from cascading failures and respects Telegram FloodWait retry headers.
"""
import time
import asyncio
import logging
from enum import Enum
from typing import Optional, Callable, Any

log = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """Standard 3-State Circuit Breaker implementation."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_time_sec: float = 15.0,
        name: str = "TelegramGateway"
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_time_sec = recovery_time_sec
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self._lock = asyncio.Lock()

    async def record_success(self) -> None:
        """Records a successful operation; resets failures or closes half-open circuit."""
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                log.info(f"[{self.name}] Circuit half-open test passed -> CLOSED.")
                self.state = CircuitState.CLOSED
            self.failure_count = 0

    async def record_failure(self, retry_after: Optional[float] = None) -> None:
        """Records a failure and triggers OPEN state if threshold exceeded."""
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.monotonic()
            
            if retry_after:
                self.recovery_time_sec = float(retry_after) + 0.5
                self.state = CircuitState.OPEN
                log.warning(f"[{self.name}] FloodWait {retry_after}s received -> Circuit OPEN.")
            elif self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                log.warning(f"[{self.name}] Failure threshold {self.failure_threshold} reached -> Circuit OPEN.")

    async def can_execute(self) -> bool:
        """Checks if a request is permitted to proceed through the circuit."""
        async with self._lock:
            if self.state == CircuitState.CLOSED:
                return True
            now = time.monotonic()
            if self.state == CircuitState.OPEN:
                if (now - self.last_failure_time) >= self.recovery_time_sec:
                    log.info(f"[{self.name}] Recovery time elapsed -> Circuit HALF_OPEN.")
                    self.state = CircuitState.HALF_OPEN
                    return True
                return False
            if self.state == CircuitState.HALF_OPEN:
                return True
            return False
