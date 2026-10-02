import assert from "node:assert/strict";
import test from "node:test";

import {
  createDefaultGraph,
  deserializeFlowGraph,
  serializeFlowGraph,
  validateFlowGraph,
  type FlowGraph,
} from "../src/components/automation-flows/flowGraphUtils.ts";

test("default visual flow is a valid DAG", () => {
  assert.deepEqual(validateFlowGraph(createDefaultGraph()), []);
});

test("condition branches are valid when true and false labels are present", () => {
  const graph: FlowGraph = {
    nodes: [
      {
        id: "trigger",
        type: "trigger",
        config: { trigger_type: "manual" },
        position: { x: 0, y: 0 },
      },
      {
        id: "condition",
        type: "condition",
        config: {
          field: "customer.order_count",
          operator: "greater_than",
          value: 1,
        },
        position: { x: 0, y: 100 },
      },
      {
        id: "yes-end",
        type: "end",
        config: {},
        position: { x: 100, y: 220 },
      },
      {
        id: "no-end",
        type: "end",
        config: {},
        position: { x: -100, y: 220 },
      },
    ],
    edges: [
      { source: "trigger", target: "condition" },
      {
        source: "condition",
        target: "yes-end",
        sourceHandle: "true",
        label: "true",
      },
      {
        source: "condition",
        target: "no-end",
        sourceHandle: "false",
        label: "false",
      },
    ],
  };

  assert.deepEqual(validateFlowGraph(graph), []);
});

test("cycle validation only fails when a cycle exists", () => {
  const graph = createDefaultGraph();
  graph.edges.push({ source: "end-1", target: "trigger-1" });

  assert.ok(validateFlowGraph(graph).includes("flowValidationCycle"));
});

test("legacy editor config is normalized to runtime schema", () => {
  const graph = deserializeFlowGraph({
    nodes: [
      {
        id: "trigger",
        type: "trigger",
        config: { trigger_type: "manual" },
        position: { x: 0, y: 0 },
      },
      {
        id: "wait",
        type: "wait",
        config: { duration: 30, duration_unit: "minutes" },
        position: { x: 0, y: 100 },
      },
      {
        id: "condition",
        type: "condition",
        config: {
          condition_field: "orders_count",
          condition_operator: "gte",
          condition_value: 2,
        },
        position: { x: 0, y: 200 },
      },
      {
        id: "message",
        type: "message",
        config: {
          message_mode: "auto",
          label: "Hola",
        },
        position: { x: 0, y: 300 },
      },
      {
        id: "end",
        type: "end",
        config: {},
        position: { x: 0, y: 400 },
      },
    ],
    edges: [],
  });

  const wait = graph.nodes.find((node) => node.id === "wait");
  assert.equal(wait?.config.value, 30);
  assert.equal(wait?.config.unit, "minutes");

  const condition = graph.nodes.find(
    (node) => node.id === "condition",
  );
  assert.equal(condition?.config.field, "customer.order_count");
  assert.equal(condition?.config.operator, "greater_or_equal");
  assert.equal(condition?.config.value, 2);

  const message = graph.nodes.find((node) => node.id === "message");
  assert.equal(message?.config.message_template, "Hola");
});

test("serialized conditional edges preserve runtime branch labels", () => {
  const graph: FlowGraph = {
    nodes: [],
    edges: [
      {
        source: "condition",
        target: "end",
        sourceHandle: "true",
      },
    ],
  };

  const serialized = serializeFlowGraph(graph) as {
    edges: Array<{ label?: string }>;
  };

  assert.equal(serialized.edges[0].label, "true");
});
