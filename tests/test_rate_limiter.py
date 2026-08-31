"""
Unit Tests for Rate Limiter, Priority Dispatcher, and Circuit Breaker.
"""
import pytest
import asyncio
from sparkgram.ratelimit.token_bucket import TokenBucket, HierarchicalRateLimiter
from sparkgram.ratelimit.priority_queue import PriorityDispatcher
from sparkgram.ratelimit.circuit_breaker import CircuitBreaker, CircuitState
from sparkgram.core.models import Priority


@pytest.mark.asyncio
async def test_token_bucket_acquire():
    bucket = TokenBucket(capacity=2.0, refill_rate=1.0)
    assert await bucket.acquire(1.0) is True
    assert await bucket.acquire(1.0) is True
    # Out of tokens
    assert await bucket.acquire(1.0) is False


@pytest.mark.asyncio
async def test_hierarchical_rate_limiter():
    limiter = HierarchicalRateLimiter(global_rate=10.0, chat_rate=2.0)
    assert await limiter.acquire(chat_id=123) is True


@pytest.mark.asyncio
async def test_priority_dispatcher_ordering():
    dispatcher = PriorityDispatcher()
    
    # Put P3, P1, P0 in reverse order
    await dispatcher.put(Priority.P3_BACKGROUND, "item3", "bg_task")
    await dispatcher.put(Priority.P1_COMMAND, "item1", "cmd_task")
    await dispatcher.put(Priority.P0_CANCEL, "item0", "cancel_task")

    p0, id0, payload0 = await dispatcher.get()
    assert p0 == Priority.P0_CANCEL
    assert payload0 == "cancel_task"

    p1, id1, payload1 = await dispatcher.get()
    assert p1 == Priority.P1_COMMAND
    assert payload1 == "cmd_task"

    p3, id3, payload3 = await dispatcher.get()
    assert p3 == Priority.P3_BACKGROUND
    assert payload3 == "bg_task"


@pytest.mark.asyncio
async def test_priority_dispatcher_stream_coalescing():
    dispatcher = PriorityDispatcher()

    # Put multiple streaming updates for the same chat message
    await dispatcher.put(Priority.P2_STREAM, "chat_1_msg_10", "Step 1 (20%)")
    await dispatcher.put(Priority.P2_STREAM, "chat_1_msg_10", "Step 2 (50%)")
    await dispatcher.put(Priority.P2_STREAM, "chat_1_msg_10", "Step 3 (100%)")

    # Only the latest payload should be retrieved
    p, item_id, payload = await dispatcher.get()
    assert p == Priority.P2_STREAM
    assert item_id == "chat_1_msg_10"
    assert payload == "Step 3 (100%)"


@pytest.mark.asyncio
async def test_circuit_breaker_transitions():
    cb = CircuitBreaker(failure_threshold=2, recovery_time_sec=0.2)
    assert cb.state == CircuitState.CLOSED
    assert await cb.can_execute() is True

    # 1 failure
    await cb.record_failure()
    assert cb.state == CircuitState.CLOSED

    # 2 failures -> OPEN
    await cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert await cb.can_execute() is False

    # Wait for recovery time -> HALF_OPEN
    await asyncio.sleep(0.3)
    assert await cb.can_execute() is True
    assert cb.state == CircuitState.HALF_OPEN

    # Success closes circuit
    await cb.record_success()
    assert cb.state == CircuitState.CLOSED
