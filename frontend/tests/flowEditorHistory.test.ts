import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  createFlowEditHistory,
  flowEditHistoryReducer,
} from "../src/components/automation-flows/flowEditHistory.ts";
import { insertNodeOnEdge } from "../src/components/automation-flows/flowEdgeInsertion.ts";
import {
  createDefaultGraph,
  validateFlowGraph,
  type FlowGraph,
} from "../src/components/automation-flows/flowGraphUtils.ts";

const source = (file: string) =>
  readFileSync(new URL(`../src/components/automation-flows/${file}`, import.meta.url), "utf8");

test("undo and redo track edits without mutating previous graphs", () => {
  const original = createDefaultGraph();
  const next = { ...original, nodes: original.nodes.map((node) => ({
    ...node, position: { x: node.position.x + 30, y: node.position.y },
  })) };
  let state = createFlowEditHistory(original);
  state = flowEditHistoryReducer(state, { type: "edit", graph: next });
  assert.equal(state.past.length, 1);
  assert.deepEqual(original.nodes[0].position, { x: 260, y: 60 });
  state = flowEditHistoryReducer(state, { type: "undo" });
  assert.deepEqual(state.graph, original);
  assert.equal(state.future.length, 1);
  state = flowEditHistoryReducer(state, { type: "redo" });
  assert.deepEqual(state.graph, next);
  assert.equal(state.future.length, 0);
});

test("a node drag creates a single undo step and clears redo only after movement", () => {
  let state = createFlowEditHistory(createDefaultGraph());
  state = flowEditHistoryReducer(state, { type: "gesture-start" });
  for (let i = 0; i < 18; i += 1) {
    const graph = {
      ...state.graph,
      nodes: state.graph.nodes.map((node) => node.id === "trigger-1"
        ? { ...node, position: { x: 260 + i + 1, y: 60 } } : node),
    };
    state = flowEditHistoryReducer(state, { type: "edit", graph });
  }
  assert.equal(state.past.length, 0);
  state = flowEditHistoryReducer(state, { type: "gesture-end" });
  assert.equal(state.past.length, 1);
  state = flowEditHistoryReducer(state, { type: "undo" });
  assert.equal(state.graph.nodes[0].position.x, 260);
  assert.equal(state.future.length, 1);
  state = flowEditHistoryReducer(state, { type: "gesture-start" });
  state = flowEditHistoryReducer(state, { type: "gesture-end" });
  assert.equal(state.future.length, 1, "no-op gestures must not discard redo");
});

test("new edits clear redo; switching flows resets the entire history", () => {
  let state = createFlowEditHistory(createDefaultGraph());
  const changed = insertNodeOnEdge(state.graph, 0, "wait").graph;
  state = flowEditHistoryReducer(state, { type: "edit", graph: changed });
  state = flowEditHistoryReducer(state, { type: "undo" });
  const other = insertNodeOnEdge(state.graph, 0, "message").graph;
  state = flowEditHistoryReducer(state, { type: "edit", graph: other });
  assert.equal(state.future.length, 0);
  const replacement = createDefaultGraph();
  state = flowEditHistoryReducer(state, { type: "reset", graph: replacement });
  assert.equal(state.past.length, 0);
  assert.equal(state.future.length, 0);
  assert.strictEqual(state.graph, replacement);
});

test("duplicate state snapshots do not create unnecessary undo steps", () => {
  const graph = createDefaultGraph();
  const state = createFlowEditHistory(graph);
  const equivalent: FlowGraph = {
    nodes: graph.nodes.map((node) => ({ ...node })),
    edges: graph.edges.map((edge) => ({ ...edge })),
  };
  assert.strictEqual(flowEditHistoryReducer(state, { type: "edit", graph: equivalent }), state);
});

test("undo stack remains bounded while the editor is used repeatedly", () => {
  let state = createFlowEditHistory(createDefaultGraph());
  for (let i = 0; i < 65; i += 1) {
    const graph = { ...state.graph, nodes: state.graph.nodes.map((node) =>
      ({ ...node, position: { x: node.position.x + 1, y: node.position.y } })) };
    state = flowEditHistoryReducer(state, { type: "edit", graph });
  }
  assert.equal(state.past.length, 40);
});

test("inserting a sequential node splits one edge while preserving a condition branch", () => {
  const graph: FlowGraph = {
    nodes: [
      { id: "trigger", type: "trigger", position: { x: 0, y: 0 }, config: { trigger_type: "manual" } },
      { id: "decision", type: "condition", position: { x: 0, y: 100 },
        config: { field: "customer.order_count", operator: "greater_than", value: 1 } },
      { id: "yes", type: "end", position: { x: 100, y: 300 }, config: {} },
      { id: "no", type: "end", position: { x: -100, y: 300 }, config: {} },
    ],
    edges: [
      { source: "trigger", target: "decision" },
      { source: "decision", target: "yes", sourceHandle: "true", label: "true" },
      { source: "decision", target: "no", sourceHandle: "false", label: "false" },
    ],
  };
  assert.deepEqual(validateFlowGraph(graph), []);
  const result = insertNodeOnEdge(graph, 1, "wait");
  assert.ok(result.insertedNodeId);
  assert.equal(graph.nodes.length, 4);
  assert.equal(graph.edges.length, 3);
  assert.equal(result.graph.nodes.length, 5);
  assert.equal(result.graph.edges.length, 4);
  assert.deepEqual(result.graph.edges[1], {
    source: "decision", target: result.insertedNodeId, sourceHandle: "true",
    label: "true", targetHandle: undefined,
  });
  assert.deepEqual(result.graph.edges[2], { source: result.insertedNodeId!, target: "yes" });
  assert.deepEqual(result.graph.edges[3], graph.edges[2]);
  assert.deepEqual(validateFlowGraph(result.graph), []);
});

test("invalid insertions leave the original draft unmodified", () => {
  const graph = createDefaultGraph();
  for (const index of [-1, 4]) {
    const result = insertNodeOnEdge(graph, index, "wait");
    assert.strictEqual(result.graph, graph);
    assert.equal(result.insertedNodeId, null);
  }
});

test("editor wires persisted versions as local edits and keeps publication separate", () => {
  const list = source("FlowList.tsx");
  const builder = source("FlowBuilder.tsx");
  const canvas = source("FlowCanvas.tsx");
  const history = source("FlowVersionHistory.tsx");
  assert.match(list, /flowEditHistoryReducer/);
  assert.match(list, /resetGraph\(loadedGraph\)/);
  assert.match(list, /setGraph\(deserializeFlowGraph\(version\.graph\)\)/);
  assert.match(list, /setSavedGraphSignature\(signature\)/);
  assert.match(list, /onGestureStart=\{\(\) => dispatchGraph/);
  assert.match(builder, /insertNodeOnEdge\(graphRef\.current, selectedEdgeIndex, type\)/);
  assert.match(canvas, /onEdgeClick=/);
  assert.match(history, /listFlowVersions\(storeId, flowId\)/);
  assert.doesNotMatch(history, /publishFlowVersion|activateFlow|createFlowVersion/);
});
