"""Graph validation and utilities for V2.2 Flow Builder."""
from __future__ import annotations

from typing import Any

NODE_TYPES = {"trigger", "wait", "message", "condition", "end"}
MAX_NODES = 50
MAX_MESSAGE_NODES = 10
MAX_WAIT_DAYS = 365

TRIGGER_TYPES = {"manual", "customer_segment", "customer_created", "order_created", "failed_order"}

CONDITION_FIELDS = {
    "customer.segment", "customer.health", "customer.priority",
    "customer.needs_attention", "customer.needs_followup",
    "customer.order_count", "customer.country",
    "has_successful_order_since_flow_start",
}

CONDITION_OPERATORS = {
    "equals", "not_equals",
    "greater_than", "greater_or_equal",
    "less_than", "less_or_equal",
    "in", "not_in",
    "is_true", "is_false",
}

MESSAGE_MODES = {"free_form", "template", "auto"}

WAIT_UNITS = {"minutes", "hours", "days"}


def validate_graph(graph: dict[str, Any]) -> list[str]:
    """Validate a flow graph. Returns list of error strings (empty = valid)."""
    errors: list[str] = []
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    if not nodes:
        errors.append("Flow must have at least one node")
        return errors

    node_ids = [n.get("id") for n in nodes]
    node_types = {n.get("id"): n.get("type") for n in nodes}
    node_map = {n.get("id"): n for n in nodes}

    if len(node_ids) != len(set(node_ids)):
        errors.append("Duplicate node IDs found")
        return errors

    if len(nodes) > MAX_NODES:
        errors.append(f"Flow exceeds maximum of {MAX_NODES} nodes")

    triggers = [n for n in nodes if n.get("type") == "trigger"]
    if len(triggers) == 0:
        errors.append("Flow must have exactly one trigger node")
    elif len(triggers) > 1:
        errors.append("Flow must have exactly one trigger node (found multiple)")

    ends = [n for n in nodes if n.get("type") == "end"]
    if not ends:
        errors.append("Flow must have at least one end node")

    message_nodes = [n for n in nodes if n.get("type") == "message"]
    if len(message_nodes) > MAX_MESSAGE_NODES:
        errors.append(f"Flow exceeds maximum of {MAX_MESSAGE_NODES} message nodes")

    for node in nodes:
        nid = node.get("id")
        ntype = node.get("type")
        config = node.get("config", {})

        if ntype not in NODE_TYPES:
            errors.append(f"Node {nid}: unknown type '{ntype}'")
            continue

        if ntype == "trigger":
            tt = config.get("trigger_type", "")
            if tt not in TRIGGER_TYPES:
                errors.append(f"Node {nid}: invalid trigger_type '{tt}'")

        elif ntype == "wait":
            unit = config.get("unit", "")
            value = config.get("value")
            if unit not in WAIT_UNITS:
                errors.append(f"Node {nid}: invalid wait unit '{unit}'")
            if not isinstance(value, (int, float)) or value < 1:
                errors.append(f"Node {nid}: wait value must be >= 1")
            if unit == "days" and isinstance(value, (int, float)) and value > MAX_WAIT_DAYS:
                errors.append(f"Node {nid}: wait exceeds maximum of {MAX_WAIT_DAYS} days")

        elif ntype == "message":
            mode = config.get("message_mode", "")
            if mode not in MESSAGE_MODES:
                errors.append(f"Node {nid}: invalid message_mode '{mode}'")
            if not config.get("message_template"):
                errors.append(f"Node {nid}: message_template is required")

        elif ntype == "condition":
            field = config.get("field", "")
            operator = config.get("operator", "")
            if field not in CONDITION_FIELDS:
                errors.append(f"Node {nid}: invalid condition field '{field}'")
            if operator not in CONDITION_OPERATORS:
                errors.append(f"Node {nid}: invalid condition operator '{operator}'")
            if operator in {"in", "not_in"}:
                if not isinstance(config.get("value"), list):
                    errors.append(f"Node {nid}: 'in'/'not_in' operators require a list value")

    edge_by_source: dict[str, list[dict]] = {}
    for edge in edges:
        src = edge.get("source")
        edge_by_source.setdefault(src, []).append(edge)

    for node in nodes:
        nid = node.get("id")
        ntype = node.get("type")
        if ntype == "end":
            continue
        out_edges = edge_by_source.get(nid, [])
        if ntype == "condition":
            labels = {e.get("label") for e in out_edges}
            if "true" not in labels and "false" not in labels:
                errors.append(f"Node {nid}: condition must have true/false branches")
            if len([e for e in out_edges if e.get("label") == "true"]) > 1:
                errors.append(f"Node {nid}: duplicate true branch")
            if len([e for e in out_edges if e.get("label") == "false"]) > 1:
                errors.append(f"Node {nid}: duplicate false branch")
        elif ntype == "trigger":
            if len(out_edges) == 0:
                errors.append(f"Node {nid}: trigger must have an outgoing edge")
        else:
            if len(out_edges) == 0:
                errors.append(f"Node {nid}: non-end node must have an outgoing edge")

    for edge in edges:
        src = edge.get("source")
        tgt = edge.get("target")
        if src not in node_ids:
            errors.append(f"Edge references unknown source node '{src}'")
        if tgt not in node_ids:
            errors.append(f"Edge references unknown target node '{tgt}'")
        if src == tgt:
            errors.append(f"Self-loop detected on node '{src}'")

    if not _is_dag(nodes, edges):
        errors.append("Flow contains a cycle (only DAGs allowed)")

    reachable = _reachable_from_trigger(nodes, edges)
    orphan_ids = set(node_ids) - reachable
    if orphan_ids:
        errors.append(f"Orphan nodes not reachable from trigger: {', '.join(sorted(orphan_ids))}")

    return errors


def _is_dag(nodes: list[dict], edges: list[dict]) -> bool:
    """Check that the graph is a DAG using Kahn's algorithm."""
    node_ids = {n.get("id") for n in nodes}
    in_degree: dict[str, int] = {nid: 0 for nid in node_ids}
    adj: dict[str, list[str]] = {nid: [] for nid in node_ids}
    for edge in edges:
        src, tgt = edge.get("source"), edge.get("target")
        if src in node_ids and tgt in node_ids:
            adj[src].append(tgt)
            in_degree[tgt] = in_degree.get(tgt, 0) + 1
    queue = [nid for nid, d in in_degree.items() if d == 0]
    visited = 0
    while queue:
        nid = queue.pop(0)
        visited += 1
        for nxt in adj.get(nid, []):
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                queue.append(nxt)
    return visited == len(node_ids)


def _reachable_from_trigger(nodes: list[dict], edges: list[dict]) -> set[str]:
    """Find all nodes reachable from the trigger node via BFS."""
    triggers = [n.get("id") for n in nodes if n.get("type") == "trigger"]
    if not triggers:
        return set()
    adj: dict[str, list[str]] = {}
    for edge in edges:
        adj.setdefault(edge.get("source", ""), []).append(edge.get("target", ""))
    visited: set[str] = set()
    queue = list(triggers)
    while queue:
        nid = queue.pop(0)
        if nid in visited:
            continue
        visited.add(nid)
        queue.extend(adj.get(nid, []))
    return visited


def get_entry_node(graph: dict[str, Any]) -> dict | None:
    """Get the trigger (entry) node from a graph."""
    for node in graph.get("nodes", []):
        if node.get("type") == "trigger":
            return node
    return None


def get_next_node(graph: dict[str, Any], current_node_id: str, outcome: str | None = None) -> dict | None:
    """Get the next node after current_node_id, optionally following a branch label."""
    edges = graph.get("edges", [])
    for edge in edges:
        if edge.get("source") == current_node_id:
            if outcome is not None:
                if edge.get("label") == outcome:
                    return _find_node(graph, edge.get("target"))
            else:
                return _find_node(graph, edge.get("target"))
    return None


def _find_node(graph: dict[str, Any], node_id: str) -> dict | None:
    for node in graph.get("nodes", []):
        if node.get("id") == node_id:
            return node
    return None
