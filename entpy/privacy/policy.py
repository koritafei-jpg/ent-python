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
    deny_by_default: bool = False


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


def _eval_rules(
    rules: list,
    ctx: dict[str, Any],
    obj: Any,
    method: str,
    *,
    deny_by_default: bool = False,
) -> bool:
    """求值规则链；显式 ``Allow`` 时返回 ``True``。"""
    for rule in rules:
        handler = getattr(rule, method, None)
        if handler is None:
            continue
        try:
            handler(ctx, obj)
        except Allow:
            return True
        except Deny as e:
            raise NotAllowedError(str(e) or "operation denied by policy") from e
        except Skip:
            continue
    if deny_by_default:
        raise NotAllowedError("operation denied by default policy")
    return False


def eval_query(ctx: dict[str, Any], policies: list[Policy], query: Any) -> None:
    for p in policies:
        if p.query and _eval_rules(
            p.query,
            ctx,
            query,
            "eval_query",
            deny_by_default=p.deny_by_default,
        ):
            return


def eval_mutation(ctx: dict[str, Any], policies: list[Policy], mutation: Mutation) -> None:
    for p in policies:
        if p.mutation and _eval_rules(
            p.mutation,
            ctx,
            mutation,
            "eval_mutation",
            deny_by_default=p.deny_by_default,
        ):
            return


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


def mutation_rule(
    fn: Callable[[dict[str, Any], Mutation], None],
) -> MutationRule:
    class _R:
        def eval_mutation(self, ctx: dict[str, Any], mutation: Mutation) -> None:
            fn(ctx, mutation)

    return _R()


def query_rule(fn: Callable[[dict[str, Any], Any], None]) -> QueryRule:
    class _R:
        def eval_query(self, ctx: dict[str, Any], query: Any) -> None:
            fn(ctx, query)

    return _R()


def rule(fn: Callable[[dict[str, Any], Mutation], None]) -> MutationRule:
    """``mutation_rule`` 别名，仅用于写路径策略。"""
    return mutation_rule(fn)
