"""创建/更新时自动写入向量字段。"""

from __future__ import annotations

from entpy.runtime.hook import Hook
from entpy.runtime.mutation import Mutation, Op
from entpy.schema.base import SearchMixin
from entpy.schema.field import FieldType


def embed_on_save_hook(embedder) -> Hook:
    """持久化前根据可检索文本填充向量字段。"""

    @Hook
    def _hook(next_mutator, mutation: Mutation):
        schema = mutation.schema
        if not issubclass(schema, SearchMixin):
            return next_mutator.mutate(mutation)
        cfg = schema.search_config()
        if cfg is None or not cfg.vector_field:
            return next_mutator.mutate(mutation)
        if mutation.op not in (Op.CREATE, Op.UPDATE_ONE):
            return next_mutator.mutate(mutation)

        text_parts = []
        for name in cfg.text_fields:
            val = mutation.fields.get(name)
            if val:
                text_parts.append(str(val))
        if text_parts and cfg.vector_field not in mutation.fields:
            vec = embedder.embed_sync([" ".join(text_parts)])[0]
            mutation.fields[cfg.vector_field] = vec
        return next_mutator.mutate(mutation)

    return _hook
