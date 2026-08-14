type PlannerLayoutClassOptions = {
  isNewChat: boolean;
  isPlanning: boolean;
  isProcessing: boolean;
};

type PlannerChatClassOptions = {
  isCollapsed: boolean;
  isCompact: boolean;
  isProcessing: boolean;
};

export type FloatingChatRect = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export function getPlannerLayoutClasses({
  isNewChat,
  isPlanning,
  isProcessing,
}: PlannerLayoutClassOptions): string {
  const classes = ["plannerLayout"];
  if (isNewChat) classes.push("is-new-chat");
  if (isPlanning) classes.push("is-planning");
  if (isProcessing) classes.push("is-processing");
  return classes.join(" ");
}

export function getPlannerChatClasses({
  isCollapsed,
  isCompact,
  isProcessing,
}: PlannerChatClassOptions): string {
  const classes = ["plannerChat", "plannerChatSurface", "panel"];
  if (isCollapsed) classes.push("is-collapsed");
  if (isProcessing) classes.push("is-processing");
  if (isCompact) classes.push("plannerChat--compact");
  return classes.join(" ");
}

export function preserveFloatingChatRect(
  existingRect: FloatingChatRect | null,
  fallbackRect: FloatingChatRect | null,
  isProcessingOrPlanning: boolean
): FloatingChatRect | null {
  if (existingRect != null) {
    return existingRect;
  }
  if (isProcessingOrPlanning && fallbackRect != null) {
    return fallbackRect;
  }
  return fallbackRect;
}

export function getDOMFloatingChatRect(element: { getBoundingClientRect: () => DOMRect } | null): FloatingChatRect | null {
  if (!element) return null;
  const bounds = element.getBoundingClientRect();
  if (!bounds || bounds.width <= 0 || bounds.height <= 0) return null;
  return {
    x: bounds.left,
    y: bounds.top,
    width: bounds.width,
    height: bounds.height,
  };
}
