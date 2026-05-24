"""从节点描述符构建解析后的图。"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field

from entpy.schema.base import Schema
from entpy.schema.edge import RelType
from entpy.ir.descriptor import NodeDescriptor
from entpy.ir.loader import load_schemas


@dataclass
class ResolvedEdge:
    name: str
    rel: RelType
    inverse: bool
    owner: NodeDescriptor
    peer: NodeDescriptor
    ref: str | None
    unique: bool
    fk_columns: list[str] = dc_field(default_factory=list)
    join_table: str | None = None
    join_columns: list[str] = dc_field(default_factory=list)


@dataclass
class Graph:
    nodes: dict[str, NodeDescriptor]
    edges: list[ResolvedEdge]
    join_tables: dict[str, tuple[str, str]]

    def node(self, name: str) -> NodeDescriptor:
        return self.nodes[name]


def build_graph(schemas: list[type[Schema]]) -> Graph:
    descriptors = load_schemas(schemas)
    by_name = {d.name: d for d in descriptors}
    by_type = {d.schema_type: d for d in descriptors}
    for d in descriptors:
        for base in d.schema_type.__mro__:
            if base is object:
                break
            from entpy.schema.base import Schema as SchemaBase

            if issubclass(base, SchemaBase) and base not in by_type:
                by_type[base] = d
    resolved: list[ResolvedEdge] = []
    join_tables: dict[str, tuple[str, str]] = {}
    m2m_keys: set[str] = set()

    for node in descriptors:
        for ed in node.edges:
            peer = by_type.get(ed.typ)
            if peer is None:
                raise ValueError(f"unknown edge type {ed.typ!r} on {node.name}.{ed.name}")

            m2m = _try_m2m(node, ed, peer, m2m_keys)
            if m2m:
                jt, cols, edge_rec = m2m
                if jt is not None:
                    join_tables[jt] = cols
                if edge_rec is not None:
                    resolved.append(edge_rec)
                continue

            if ed.inverse:
                fk = ed.storage_key or _fk_name(peer, node, ed.ref or ed.name)
                rel = RelType.O2O if ed.unique else RelType.M2O
                resolved.append(
                    ResolvedEdge(
                        name=ed.name,
                        rel=rel,
                        inverse=True,
                        owner=node,
                        peer=peer,
                        ref=ed.ref,
                        unique=ed.unique,
                        fk_columns=[fk],
                    )
                )
            else:
                fk = ed.storage_key or _fk_name(node, peer, ed.name)
                rel = RelType.O2O if ed.unique else RelType.O2M
                resolved.append(
                    ResolvedEdge(
                        name=ed.name,
                        rel=rel,
                        inverse=False,
                        owner=node,
                        peer=peer,
                        ref=ed.ref,
                        unique=ed.unique,
                        fk_columns=[fk],
                    )
                )

    resolved = _add_m2m_mirror_edges(resolved)
    return Graph(nodes=by_name, edges=resolved, join_tables=join_tables)


def _add_m2m_mirror_edges(resolved: list[ResolvedEdge]) -> list[ResolvedEdge]:
    """为 M2M 关系补充对端节点的遍历边（Group.users 等）。"""
    out = list(resolved)
    seen = {(e.owner.name, e.name) for e in resolved}
    for e in resolved:
        if e.rel != RelType.M2M or not e.ref:
            continue
        mirror_name = e.ref
        key = (e.peer.name, mirror_name)
        if key in seen:
            continue
        peer_col, owner_col = e.join_columns
        out.append(
            ResolvedEdge(
                name=mirror_name,
                rel=RelType.M2M,
                inverse=False,
                owner=e.peer,
                peer=e.owner,
                ref=e.name,
                unique=False,
                join_table=e.join_table,
                join_columns=[owner_col, peer_col],
            )
        )
        seen.add(key)
    return out


def _try_m2m(
    node: NodeDescriptor,
    ed,
    peer: NodeDescriptor,
    done: set[str],
):
    """通过 Ref 或配对反向边判断多对多。"""
    ref_name = ed.ref
    if ref_name:
        inv = _find_edge(peer, ref_name)
        if inv is None:
            return None
        # O2O/O2M 唯一边（如 Car.from_("owner").ref("cars")）不是 M2M
        if ed.unique or inv.unique:
            return None
        key = f"{min(node.name, peer.name)}:{max(node.name, peer.name)}:{ref_name}"
        if key in done:
            jt = _join_table(peer, node)
            p_col = _singular(peer) + "_id"
            o_col = _singular(node) + "_id"
            mirror = ResolvedEdge(
                name=ref_name,
                rel=RelType.M2M,
                inverse=False,
                owner=peer,
                peer=node,
                ref=ed.name,
                unique=False,
                join_table=jt,
                join_columns=[p_col, o_col],
            )
            return None, None, mirror
        done.add(key)
        jt = _join_table(peer, node)
        cols = (_singular(peer) + "_id", _singular(node) + "_id")
        rec = ResolvedEdge(
            name=ed.name,
            rel=RelType.M2M,
            inverse=ed.inverse,
            owner=node,
            peer=peer,
            ref=ref_name,
            unique=False,
            join_table=jt,
            join_columns=list(cols),
        )
        return jt, cols, rec

    # 配对反向边带 ref：仅非 FK（唯一）关系时为 M2M
    for ped in peer.edges:
        if ped.inverse and ped.typ == node.schema_type and ped.ref == ed.name:
            if ped.unique:
                return None  # 例如 Car.owner 引用 cars — Car 上是 FK，非 M2M
            key = f"{min(node.name, peer.name)}:{max(node.name, peer.name)}:{ed.name}"
            if key in done:
                jt = _join_table(peer, node)
                p_col = _singular(peer) + "_id"
                o_col = _singular(node) + "_id"
                mirror = ResolvedEdge(
                    name=ed.name,
                    rel=RelType.M2M,
                    inverse=False,
                    owner=peer,
                    peer=node,
                    ref=ped.name,
                    unique=False,
                    join_table=jt,
                    join_columns=[p_col, o_col],
                )
                return None, None, mirror
            done.add(key)
            jt = _join_table(peer, node)
            cols = (_singular(peer) + "_id", _singular(node) + "_id")
            rec = ResolvedEdge(
                name=ed.name,
                rel=RelType.M2M,
                inverse=False,
                owner=node,
                peer=peer,
                ref=ped.name,
                unique=False,
                join_table=jt,
                join_columns=list(cols),
            )
            return jt, cols, rec
    return None


def _find_edge(node: NodeDescriptor, name: str):
    for ed in node.edges:
        if ed.name == name:
            return ed
    return None


def _singular(node: NodeDescriptor) -> str:
    mapping = {"User": "user", "Car": "car", "Group": "group", "Chunk": "chunk"}
    return mapping.get(node.name, node.name.lower())


def _join_table(a: NodeDescriptor, b: NodeDescriptor) -> str:
    if a.name == "Group" and b.name == "User":
        return "group_users"
    return f"{_singular(a)}_{_singular(b)}s"


def _fk_name(owner: NodeDescriptor, peer: NodeDescriptor, edge: str) -> str:
    if peer.name == "User" and edge == "cars":
        return "user_cars"
    if owner.name == "User" and edge == "cars":
        return "user_cars"
    return f"{_singular(owner)}_{edge}"
