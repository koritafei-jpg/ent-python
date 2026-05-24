"""混合 Sync/Async Hook 链在已有 event loop 下的行为。"""

from __future__ import annotations

import asyncio

import pytest

from entpy.runtime.hook import AsyncHook, Hook, chain_hooks_async
from entpy.runtime.mutation import Mutation, Op
from examples.start.models import User


@pytest.mark.asyncio
async def test_mixed_sync_then_async_hook_under_running_loop():
    calls: list[str] = []

    @Hook
    def sync_first(next_m, mutation: Mutation):
        calls.append("sync")
        return next_m.mutate(mutation)

    @AsyncHook
    async def async_second(next_m, mutation: Mutation):
        calls.append("async")
        return await next_m.mutate(mutation)

    m = Mutation(User, Op.CREATE, fields={"name": "x"})
    await chain_hooks_async([sync_first, async_second], m)
    assert calls == ["sync", "async"]


@pytest.mark.asyncio
async def test_mixed_async_then_sync_hook_under_running_loop():
    calls: list[str] = []

    @AsyncHook
    async def async_first(next_m, mutation: Mutation):
        calls.append("async")
        return await next_m.mutate(mutation)

    @Hook
    def sync_second(next_m, mutation: Mutation):
        calls.append("sync")
        return next_m.mutate(mutation)

    m = Mutation(User, Op.CREATE, fields={"name": "x"})
    await chain_hooks_async([async_first, sync_second], m)
    assert calls == ["async", "sync"]
