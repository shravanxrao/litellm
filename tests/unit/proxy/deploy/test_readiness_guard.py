from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from redis.asyncio import Redis

from config.vercel.readiness_guard import BudgetReadinessGuard
from litellm.caching.caching import DualCache
from litellm.proxy._types import UserAPIKeyAuth
from litellm.types.utils import CallTypesLiteral


@pytest.fixture
def guard(monkeypatch: pytest.MonkeyPatch) -> BudgetReadinessGuard:
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
    return BudgetReadinessGuard()


@pytest.fixture
def auth() -> UserAPIKeyAuth:
    return UserAPIKeyAuth(api_key="sk-unit-test-key")


@pytest.mark.asyncio
async def test_missing_redis_rejects_inference_before_connecting(
    monkeypatch: pytest.MonkeyPatch, auth: UserAPIKeyAuth
) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
    guard = BudgetReadinessGuard()
    client = AsyncMock(spec=Redis)
    guard.client = client
    with pytest.raises(HTTPException) as error:
        await guard.async_pre_call_hook(auth, DualCache(), {"model": "gpt-6-astra"}, "acompletion")
    assert error.value.status_code == 503
    client.ping.assert_not_called()


@pytest.mark.asyncio
async def test_healthy_redis_preserves_inference_payload_and_initializes_client(
    guard: BudgetReadinessGuard, auth: UserAPIKeyAuth, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = AsyncMock(spec=Redis)
    client.ping = AsyncMock(return_value=True)
    monkeypatch.setattr(Redis, "from_url", lambda *args, **kwargs: client)
    payload = {"model": "gpt-6-astra", "messages": [{"role": "user", "content": "Hello"}], "stream": True}
    result = await guard.async_pre_call_hook(auth, DualCache(), payload, "acompletion")
    assert result is payload
    assert guard.client is client
    client.ping.assert_awaited_once()


@pytest.mark.asyncio
async def test_redis_connection_failure_rejects_inference_without_exposing_connection_details(
    guard: BudgetReadinessGuard, auth: UserAPIKeyAuth
) -> None:
    client = AsyncMock(spec=Redis)
    client.ping = AsyncMock(side_effect=ConnectionError("credential-bearing upstream diagnostic"))
    guard.client = client
    with pytest.raises(HTTPException) as error:
        await guard.async_pre_call_hook(auth, DualCache(), {}, "acompletion")
    assert error.value.status_code == 503
    assert error.value.detail == "Paid inference is paused because budget coordination is unavailable."
    assert error.value.__cause__ is None


@pytest.mark.asyncio
async def test_unsuccessful_redis_ping_rejects_inference(
    guard: BudgetReadinessGuard, auth: UserAPIKeyAuth
) -> None:
    client = AsyncMock(spec=Redis)
    client.ping = AsyncMock(return_value=False)
    guard.client = client
    with pytest.raises(HTTPException) as error:
        await guard.async_pre_call_hook(auth, DualCache(), {}, "acompletion")
    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_background_responses_remain_blocked_with_healthy_redis(
    guard: BudgetReadinessGuard, auth: UserAPIKeyAuth
) -> None:
    client = AsyncMock(spec=Redis)
    client.ping = AsyncMock(return_value=True)
    guard.client = client
    with pytest.raises(HTTPException) as error:
        await guard.async_pre_call_hook(auth, DualCache(), {"background": True}, "aresponses")
    assert error.value.status_code == 503
    assert error.value.detail == "Asynchronous inference is paused until durable background accounting is configured."


@pytest.mark.asyncio
@pytest.mark.parametrize("call_type", ["create_batch", "acreate_batch"])
async def test_batch_submission_remains_blocked_with_healthy_redis(
    guard: BudgetReadinessGuard, auth: UserAPIKeyAuth, call_type: CallTypesLiteral
) -> None:
    client = AsyncMock(spec=Redis)
    client.ping = AsyncMock(return_value=True)
    guard.client = client
    with pytest.raises(HTTPException) as error:
        await guard.async_pre_call_hook(auth, DualCache(), {}, call_type)
    assert error.value.status_code == 503
    assert error.value.detail == "Asynchronous inference is paused until durable background accounting is configured."
