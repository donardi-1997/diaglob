export interface FloatingPosition {
  x: number;
  y: number;
}

export const COPILOT_FAB_SIZE = 56;
export const COPILOT_FAB_MARGIN = 14;

export function clampFloatingPosition(
  position: FloatingPosition,
  viewportWidth: number,
  viewportHeight: number,
): FloatingPosition {
  const maxX = Math.max(
    COPILOT_FAB_MARGIN,
    viewportWidth - COPILOT_FAB_SIZE - COPILOT_FAB_MARGIN,
  );
  const maxY = Math.max(
    COPILOT_FAB_MARGIN,
    viewportHeight - COPILOT_FAB_SIZE - COPILOT_FAB_MARGIN,
  );

  return {
    x: Math.min(Math.max(position.x, COPILOT_FAB_MARGIN), maxX),
    y: Math.min(Math.max(position.y, COPILOT_FAB_MARGIN), maxY),
  };
}

export function defaultFloatingPosition(
  viewportWidth: number,
  viewportHeight: number,
): FloatingPosition {
  return clampFloatingPosition(
    {
      x: viewportWidth - COPILOT_FAB_SIZE - 24,
      y: viewportHeight - COPILOT_FAB_SIZE - 132,
    },
    viewportWidth,
    viewportHeight,
  );
}

export function parseFloatingPosition(
  value: string | null,
): FloatingPosition | null {
  if (!value) return null;

  try {
    const parsed = JSON.parse(value) as Partial<FloatingPosition>;
    if (
      typeof parsed.x !== "number"
      || !Number.isFinite(parsed.x)
      || typeof parsed.y !== "number"
      || !Number.isFinite(parsed.y)
    ) {
      return null;
    }
    return { x: parsed.x, y: parsed.y };
  } catch {
    return null;
  }
}
