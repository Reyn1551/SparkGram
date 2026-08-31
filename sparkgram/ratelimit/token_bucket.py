"""
Hierarchical 2-Tier Token Bucket Rate Limiter for SparkGram.
Prevents Telegram API FloodWait (429 Too Many Requests) at both global and per-chat levels.
"""
import time
import asyncio
import logging
from typing import Dict

log = logging.getLogger(__name__)


class TokenBucket:
    """Standard in-memory Token Bucket implementation."""

    def __init__(self, capacity: float, refill_rate: float):
        self.capacity = float(capacity)
        self.refill_rate = float(refill_rate)
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> bool:
        """Attempts to consume tokens without waiting."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            self.last_refill = now

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    async def wait_and_acquire(self, tokens: float = 1.0, timeout: float = 30.0) -> bool:
        """Waits asynchronously until enough tokens are available."""
        start_wait = time.monotonic()
        while True:
            if await self.acquire(tokens):
                return True
            if (time.monotonic() - start_wait) > timeout:
                log.warning(f"Token bucket acquisition timed out after {timeout}s")
                return False
            await asyncio.sleep(0.05)


class HierarchicalRateLimiter:
    """
    2-Tier Rate Limiter:
    - Tier 1: Global Telegram Gate (default 28.0 req/s, capacity 28)
    - Tier 2: Per-Chat Rate Gate (default 1.0 req/s for private chat, capacity 1)
    """

    def __init__(self, global_rate: float = 28.0, chat_rate: float = 1.0):
        self.global_bucket = TokenBucket(capacity=global_rate, refill_rate=global_rate)
        self.chat_buckets: Dict[int, TokenBucket] = {}
        self.chat_rate = chat_rate
        self._lock = asyncio.Lock()

    async def _get_chat_bucket(self, chat_id: int) -> TokenBucket:
        async with self._lock:
            if chat_id not in self.chat_buckets:
                self.chat_buckets[chat_id] = TokenBucket(capacity=1.0, refill_rate=self.chat_rate)
            return self.chat_buckets[chat_id]

    async def acquire(self, chat_id: int, timeout: float = 30.0) -> bool:
        """Acquires permission from both global and per-chat buckets."""
        chat_bucket = await self._get_chat_bucket(chat_id)
        
        ok_global = await self.global_bucket.wait_and_acquire(1.0, timeout=timeout)
        if not ok_global:
            return False
            
        ok_chat = await chat_bucket.wait_and_acquire(1.0, timeout=timeout)
        return ok_chat


# Global rate limiter instance
rate_limiter = HierarchicalRateLimiter(global_rate=28.0, chat_rate=1.0)
