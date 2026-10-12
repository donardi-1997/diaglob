/**
 * Monotonic guard for asynchronous UI requests.
 * A response may update state only if no newer request or scope change
 * has invalidated its generation.
 */
export function createLatestRequestGuard() {
  let generation = 0;

  return {
    issue(): number {
      generation += 1;
      return generation;
    },
    isCurrent(requestGeneration: number): boolean {
      return requestGeneration === generation;
    },
    invalidate(): void {
      generation += 1;
    },
  };
}
