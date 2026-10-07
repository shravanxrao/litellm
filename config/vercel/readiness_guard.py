from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException
from litellm.integrations.custom_logger import CustomLogger
from redis.asyncio import Redis

if TYPE_CHECKING:
    from litellm.caching.caching import DualCache
    from litellm.proxy._types import UserAPIKeyAuth
    from litellm.types.utils import CallTypesLiteral


class BudgetReadinessGuard(CustomLogger):
    def __init__(self) -> None:
        self.redis_url = os.environ.get("REDIS_URL", "").strip()
        self.client: Redis | None = None

    async def async_pre_call_hook(
        self,
        user_api_key_dict: UserAPIKeyAuth,
        cache: DualCache,
        data: dict[str, Any],
        call_type: CallTypesLiteral,
    ) -> dict[str, Any]:
        if not self.redis_url:
            raise HTTPException(
                status_code=503,
                detail="Paid inference is paused until Redis budget coordination is configured and redeployed.",
            )
        try:
            if self.client is None:
                self.client = Redis.from_url(
                    self.redis_url,
                    socket_timeout=2,
                    socket_connect_timeout=2,
                )
            if not await self.client.ping():
                raise RuntimeError("Redis coordination unavailable")
        except Exception:
            raise HTTPException(
                status_code=503,
                detail="Paid inference is paused because budget coordination is unavailable.",
            ) from None
        if data.get("background") is True or call_type in {"acreate_batch", "create_batch"}:
            raise HTTPException(
                status_code=503,
                detail="Asynchronous inference is paused until durable background accounting is configured.",
            )
        return data


budget_readiness_guard = BudgetReadinessGuard()
