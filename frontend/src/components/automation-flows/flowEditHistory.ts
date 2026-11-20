import {
  serializeFlowGraph,
  type FlowGraph,
} from "./flowGraphUtils.ts";

const HISTORY_LIMIT = 40;

export interface FlowEditHistory {
  graph: FlowGraph;
  past: FlowGraph[];
  future: FlowGraph[];
  gestureStart: FlowGraph | null;
}

export type FlowEditAction =
  | { type: "reset"; graph: FlowGraph }
  | { type: "edit"; graph: FlowGraph }
  | { type: "undo" }
  | { type: "redo" }
  | { type: "gesture-start" }
  | { type: "gesture-end" };

export function createFlowEditHistory(graph: FlowGraph): FlowEditHistory {
  return { graph, past: [], future: [], gestureStart: null };
}

function sameGraph(a: FlowGraph, b: FlowGraph): boolean {
  return JSON.stringify(serializeFlowGraph(a)) === JSON.stringify(serializeFlowGraph(b));
}

function appendPast(past: FlowGraph[], previous: FlowGraph): FlowGraph[] {
  return [...past, previous].slice(-HISTORY_LIMIT);
}

/**
 * Editor-local undo/redo. A drag is one transaction, not one entry per
 * movement frame. Persisted versions and active executions are untouched.
 */
export function flowEditHistoryReducer(
  state: FlowEditHistory,
  action: FlowEditAction,
): FlowEditHistory {
  switch (action.type) {
    case "reset":
      return createFlowEditHistory(action.graph);
    case "edit":
      if (sameGraph(state.graph, action.graph)) return state;
      if (state.gestureStart) return { ...state, graph: action.graph };
      return {
        graph: action.graph,
        past: appendPast(state.past, state.graph),
        future: [],
        gestureStart: null,
      };
    case "gesture-start":
      return state.gestureStart ? state : { ...state, gestureStart: state.graph };
    case "gesture-end": {
      if (!state.gestureStart) return state;
      const baseline = state.gestureStart;
      if (sameGraph(baseline, state.graph)) {
        return { ...state, gestureStart: null };
      }
      return {
        graph: state.graph,
        past: appendPast(state.past, baseline),
        future: [],
        gestureStart: null,
      };
    }
    case "undo": {
      if (state.gestureStart || !state.past.length) return state;
      const previous = state.past[state.past.length - 1];
      return {
        graph: previous,
        past: state.past.slice(0, -1),
        future: [state.graph, ...state.future],
        gestureStart: null,
      };
    }
    case "redo": {
      if (state.gestureStart || !state.future.length) return state;
      return {
        graph: state.future[0],
        past: appendPast(state.past, state.graph),
        future: state.future.slice(1),
        gestureStart: null,
      };
    }
  }
}
