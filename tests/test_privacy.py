"""Privacy：deny_by_default 与 query/mutation 规则拆分。"""

from __future__ import annotations

import pytest

from entpy.privacy.policy import (
    Allow,
    Deny,
    Policy,
    Skip,
    eval_mutation,
    eval_query,
    mutation_rule,
    query_rule,
    rule,
)
from entpy.runtime.errors import NotAllowedError
from entpy.runtime.mutation import Mutation, Op
from examples.start.models import User


def _skip(_ctx, _obj) -> None:
    raise Skip()


def test_deny_by_default_blocks_when_no_rule_matches():
    m = Mutation(User, Op.CREATE, fields={"name": "x"})
    policies = [Policy(mutation=[mutation_rule(_skip)], deny_by_default=True)]
    with pytest.raises(NotAllowedError, match="denied by default"):
        eval_mutation({}, policies, m)


def test_fail_open_without_deny_by_default():
    m = Mutation(User, Op.CREATE, fields={"name": "x"})
    policies = [Policy(mutation=[mutation_rule(_skip)])]
    eval_mutation({}, policies, m)


def test_mutation_rule_not_used_on_query_path():
    seen: list[str] = []

    def on_mutation(ctx, mutation):
        seen.append("mutation")

    class FakeQuery:
        pass

    policies = [Policy(query=[query_rule(lambda ctx, q: seen.append("query"))])]
    eval_query({}, policies, FakeQuery())
    assert seen == ["query"]


def test_rule_alias_is_mutation_only():
    def deny_delete(_ctx, mutation: Mutation) -> None:
        if mutation.op == Op.DELETE:
            raise Deny()
        raise Skip()

    m = Mutation(User, Op.DELETE, id="x")
    policies = [Policy(mutation=[rule(deny_delete)])]
    with pytest.raises(NotAllowedError):
        eval_mutation({}, policies, m)

    class FakeQuery:
        pass

    # rule() 无 eval_query，挂在 query 策略上会被跳过（fail-open）
    eval_query({}, [Policy(query=[rule(lambda _ctx, _m: (_ for _ in ()).throw(Deny()))])], FakeQuery())


def test_allow_in_first_policy_short_circuits_later_deny():
    def allow(_ctx, _m) -> None:
        raise Allow()

    def deny(_ctx, _m) -> None:
        raise Deny()

    m = Mutation(User, Op.CREATE, fields={})
    eval_mutation(
        {},
        [
            Policy(mutation=[mutation_rule(allow)]),
            Policy(mutation=[mutation_rule(deny)]),
        ],
        m,
    )


def test_allow_stops_chain():
    def allow(_ctx, _m) -> None:
        raise Allow()

    def deny(_ctx, _m) -> None:
        raise Deny()

    m = Mutation(User, Op.CREATE, fields={})
    policies = [
        Policy(
            mutation=[mutation_rule(allow), mutation_rule(deny)],
            deny_by_default=True,
        )
    ]
    eval_mutation({}, policies, m)
