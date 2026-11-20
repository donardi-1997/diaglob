import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { connectFlowNodes } from "../src/components/automation-flows/flowConnectionRules.ts";
import {
  createDefaultGraph,
  defaultConfigForNode,
  type FlowGraph,
  type FlowNodeType,
} from "../src/components/automation-flows/flowGraphUtils.ts";

function node(id: string, type: FlowNodeType): FlowGraph["nodes"][number] {
  return {
    id,
    type,
    config: defaultConfigForNode(type),
    position: { x: 0, y: 0 },
  };
}

test("reconnecting a regular output replaces its old edge, without mutating the draft", () => {
  const original = createDefaultGraph();
  const graph: FlowGraph = {
    ...original,
    nodes: [...original.nodes, node("message-a", "message")],
  };

  const replacement = connectFlowNodes(graph, {
    source: "trigger-1",
    target: "message-a",
    sourceHandle: null,
  });
  assert.equal(replacement.error, null);
  assert.deepEqual(replacement.graph.edges, [
    { source: "trigger-1", target: "message-a" },
  ]);
  assert.deepEqual(original.edges, [{ source: "trigger-1", target: "end-1" }]);
  assert.deepEqual(graph.edges, original.edges);

  const next = connectFlowNodes(replacement.graph, {
    source: "message-a",
    target: "end-1",
  });
  assert.equal(next.error, null);
  assert.equal(next.graph.edges.length, 2);
});

test("duplicate connections are no-ops and do not dirty the editor", () => {
  const graph = createDefaultGraph();
  const result = connectFlowNodes(graph, { source: "trigger-1", target: "end-1" });
  assert.equal(result.error, null);
  assert.strictEqual(result.graph, graph);
});

test("invalid endpoints and handles are rejected without losing existing edges", () => {
  const graph: FlowGraph = {
    nodes: [
      node("trigger", "trigger"),
      node("condition", "condition"),
      node("call", "call"),
      node("wait", "wait"),
      node("end", "end"),
    ],
    edges: [{ source: "trigger", target: "end" }],
  };

  const rejected = [
    [{ source: "missing", target: "end" }, "missing-node"],
    [{ source: "trigger", target: "trigger" }, "self-loop"],
    [{ source: "wait", target: "trigger" }, "trigger-target"],
    [{ source: "end", target: "wait" }, "end-source"],
    [{ source: "wait", target: "end", sourceHandle: "true" }, "invalid-handle"],
    [{ source: "condition", target: "end" }, "invalid-handle"],
    [{ source: "condition", target: "end", sourceHandle: "confirmed" }, "invalid-handle"],
    [{ source: "call", target: "end", sourceHandle: "true" }, "invalid-handle"],
    [{ source: "trigger", target: "end", targetHandle: "other" }, "invalid-handle"],
  ] as const;

  for (const [input, reason] of rejected) {
    const result = connectFlowNodes(graph, input);
    assert.equal(result.error, reason);
    assert.strictEqual(result.graph, graph);
  }
});

test("a cycle is rejected without replacing the existing branch", () => {
  const graph: FlowGraph = {
    nodes: [
      node("trigger", "trigger"), node("a", "wait"),
      node("b", "wait"), node("end", "end"),
    ],
    edges: [
      { source: "trigger", target: "a" },
      { source: "a", target: "b" },
      { source: "b", target: "end" },
    ],
  };
  const rejected = connectFlowNodes(graph, { source: "b", target: "a" });
  assert.equal(rejected.error, "cycle");
  assert.strictEqual(rejected.graph, graph);
  assert.deepEqual(graph.edges[2], { source: "b", target: "end" });
});

test("condition outputs replace only the selected true/false branch", () => {
  const graph: FlowGraph = {
    nodes: [
      node("trigger", "trigger"), node("condition", "condition"),
      node("yes", "end"), node("no", "end"), node("new-yes", "end"),
    ],
    edges: [
      { source: "trigger", target: "condition" },
      { source: "condition", target: "yes", sourceHandle: "true", label: "true" },
      { source: "condition", target: "no", sourceHandle: "false", label: "false" },
    ],
  };
  const result = connectFlowNodes(graph, {
    source: "condition", target: "new-yes", sourceHandle: "true",
  });
  assert.equal(result.error, null);
  assert.equal(result.graph.edges.length, 3);
  assert.ok(result.graph.edges.some((edge) =>
    edge.source === "condition" && edge.target === "no" && edge.label === "false"
  ));
  assert.ok(result.graph.edges.some((edge) =>
    edge.source === "condition" && edge.target === "new-yes" && edge.label === "true"
  ));
  assert.ok(!result.graph.edges.some((edge) => edge.target === "yes"));
});

test("voice-call outcomes retain all other exits when one is reconnected", () => {
  const outcomes = ["confirmed", "rejected", "no_answer", "failed"];
  const graph: FlowGraph = {
    nodes: [node("call", "call"), ...outcomes.map((id) => node(id, "end")), node("new", "end")],
    edges: outcomes.map((outcome) => ({
      source: "call",
      target: outcome,
      sourceHandle: outcome,
      label: outcome,
    })),
  };
  const result = connectFlowNodes(graph, {
    source: "call", target: "new", sourceHandle: "failed",
  });
  assert.equal(result.error, null);
  assert.equal(result.graph.edges.length, 4);
  assert.ok(result.graph.edges.some((edge) =>
    edge.target === "new" && edge.label === "failed"
  ));
  for (const outcome of outcomes.slice(0, 3)) {
    assert.ok(result.graph.edges.some((edge) =>
      edge.target === outcome && edge.label === outcome
    ));
  }
});

test("editor wires safe connections and respects read-only mode in the canvas", () => {
  const source = (file: string) =>
    readFileSync(new URL(`../src/components/automation-flows/${file}`, import.meta.url), "utf8");
  const builder = source("FlowBuilder.tsx");
  const canvas = source("FlowCanvas.tsx");
  assert.match(builder, /connectFlowNodes\(graphRef\.current, connection\)/);
  assert.match(builder, /if \(!result\.error && result\.graph !== graphRef\.current\)/);
  assert.match(builder, /aria-live="polite"/);
  assert.match(builder, /node\.type === "trigger"/);
  assert.match(canvas, /nodesDraggable=\{canWrite\}/);
  assert.match(canvas, /nodesConnectable=\{canWrite\}/);
  assert.match(canvas, /deleteKeyCode=\{canWrite \?/);
});
