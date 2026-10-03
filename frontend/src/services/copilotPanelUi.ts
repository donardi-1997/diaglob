export const COPILOT_PANEL_DEFAULT_WIDTH = 460;
export const COPILOT_PANEL_MIN_WIDTH = 360;
export const COPILOT_PANEL_MAX_WIDTH = 820;

export function clampCopilotPanelWidth(
  width: number,
  viewportWidth: number,
) {
  const viewportMax = Math.max(
    COPILOT_PANEL_MIN_WIDTH,
    viewportWidth - 24,
  );
  return Math.round(
    Math.min(
      Math.max(width, COPILOT_PANEL_MIN_WIDTH),
      Math.min(COPILOT_PANEL_MAX_WIDTH, viewportMax),
    ),
  );
}

export function nextTypewriterLength(
  current: number,
  total: number,
) {
  if (current >= total) return total;
  const remaining = total - current;
  const chunk = remaining > 600 ? 4 : remaining > 240 ? 3 : 2;
  return Math.min(total, current + chunk);
}
