"""
Priority-Based Dispatcher Queue with Dynamic Intermediate Coalescing.
Guarantees emergency cancellation (P0) executes immediately while preventing stream queue explosions (P2).
"""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Tuple

from ..core.models import Priority

log = logging.getLogger(__name__)


@dataclass(order=True)
class PrioritizedItem:
    priority: int
    item_id: str = field(compare=False)
    payload: Any = field(compare=False)


class PriorityDispatcher:
    """Async priority queue supporting dynamic deduplication / coalescing."""

    def __init__(self):
        self._queue: asyncio.PriorityQueue[PrioritizedItem] = asyncio.PriorityQueue()
        self._pending_streams: Dict[str, PrioritizedItem] = {}
        self._lock = asyncio.Lock()

    async def put(self, priority: Priority, item_id: str, payload: Any) -> None:
        """Pushes an item into the priority queue."""
        async with self._lock:
            # If it is a streaming update (P2), coalesce by item_id
            if priority == Priority.P2_STREAM:
                if item_id in self._pending_streams:
                    # Update payload in-place
                    self._pending_streams[item_id].payload = payload
                    return
                item = PrioritizedItem(priority=int(priority), item_id=item_id, payload=payload)
                self._pending_streams[item_id] = item
                await self._queue.put(item)
            else:
                item = PrioritizedItem(priority=int(priority), item_id=item_id, payload=payload)
                await self._queue.put(item)

    async def get(self) -> Tuple[Priority, str, Any]:
        """Pulls the highest priority item from the queue."""
        item = await self._queue.get()
        async with self._lock:
            if item.priority == int(Priority.P2_STREAM) and item.item_id in self._pending_streams:
                self._pending_streams.pop(item.item_id, None)
        return Priority(item.priority), item.item_id, item.payload

    def task_done(self) -> None:
        self._queue.task_done()
