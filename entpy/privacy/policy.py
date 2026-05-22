"""Privacy 规则：Allow / Deny / Skip。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Protocol

from entpy.runtime.errors import NotAllowedError
from entpy.runtime.mutation import Mutation


class Decision(Enum):
    ALLOW = "allow"
    DENY = "deny"
    SKIP = "skip"


class Allow(Exception):
    """以允许结束策略链。"""

    pass


class Deny(Exception):
    """以拒绝结束策略链。"""

    pass


class Skip(Exception):
    """继续下一条规则。"""

    pass


class QueryRule(Protocol):
    def eval_query(self, ctx: dict[str, Any], query: Any) -> None: ...


class MutationRule(Protocol):
    def eval_mutation(self, ctx: dict[str, Any], mutation: Mutation) -> None: ...


QueryPolicy = list[QueryRule]
MutationPolicy = list[MutationRule]


@dataclass
class Policy:
    query: QueryPolicy | None = None
    mutation: MutationPolicy | None = None


def always_allow() -> MutationRule:
    class _R:
        def eval_mutation(self, ctx: dict[str, Any], mutation: Mutation) -> None:
            raise Allow()

        def eval_query(self, ctx: dict[str, Any], query: Any) -> None:
            raise Allow()

    return _R()


def always_deny() -> MutationRule:
    class _R:
        def eval_mutation(self, ctx: dict[str, Any], mutation: Mutation) -> None:
            raise Deny()

        def eval_query(self, ctx: dict[str, Any], query: Any) -> None:
            raise Deny()

    return _R()


def _eval_rules(rules: list, ctx: dict[str, Any], obj: Any, method: str) -> None:
    for rule in rules:
        try:
            getattr(rule, method)(ctx, obj)
        except Allow:
            return
        except Deny as e:
            raise NotAllowedError(str(e)) from e
        except Skip:
            continue


def eval_query(ctx: dict[str, Any], policies: list[Policy], query: Any) -> None:
    for p in policies:
        if p.query:
            _eval_rules(p.query, ctx, query, "eval_query")


def eval_mutation(ctx: dict[str, Any], policies: list[Policy], mutation: Mutation) -> None:
    for p in policies:
        if p.mutation:
            _eval_rules(p.mutation, ctx, mutation, "eval_mutation")


_CTX_KEY = "_entpy_privacy_decision"


def with_decision(ctx: dict[str, Any], decision: Decision) -> dict[str, Any]:
    out = dict(ctx)
    out[_CTX_KEY] = decision
    return out


def decision_from_context(ctx: dict[str, Any]) -> Decision | None:
    d = ctx.get(_CTX_KEY)
    if isinstance(d, Decision):
        return d
    return None


def rule(fn: Callable[[dict[str, Any], Mutation], None]) -> MutationRule:
    class _R:
        def eval_mutation(self, ctx: dict[str, Any], mutation: Mutation) -> None:
            fn(ctx, mutation)

        def eval_query(self, ctx: dict[str, Any], query: Any) -> None:
            fn(ctx, query)

    return _R()
