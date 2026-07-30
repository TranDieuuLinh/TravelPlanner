const HUE_COUNT = 360;
const SATURATIONS = [58, 64, 70];
const LIGHTNESSES = [36, 41, 46];
const COLOR_COUNT = HUE_COUNT * SATURATIONS.length * LIGHTNESSES.length;
const COLOR_PROBE_STEP = 137;

function hashDateKey(value: string): number {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function colorFromIndex(index: number): string {
  const hue = index % HUE_COUNT;
  const saturationIndex = Math.floor(index / HUE_COUNT) % SATURATIONS.length;
  const lightnessIndex =
    Math.floor(index / (HUE_COUNT * SATURATIONS.length)) %
    LIGHTNESSES.length;

  return `hsl(${hue}, ${SATURATIONS[saturationIndex]}%, ${LIGHTNESSES[lightnessIndex]}%)`;
}

/**
 * Produces stable, date-seeded colors and resolves the unlikely hash collision
 * so two dates visible in the same itinerary never share an exact color.
 */
export function createDayColorMap(dateKeys: string[]): Map<string, string> {
  const uniqueDateKeys = [...new Set(dateKeys)].sort();
  const usedColorIndexes = new Set<number>();
  const colors = new Map<string, string>();

  uniqueDateKeys.forEach((dateKey) => {
    let colorIndex = hashDateKey(dateKey) % COLOR_COUNT;
    while (usedColorIndexes.has(colorIndex)) {
      colorIndex = (colorIndex + COLOR_PROBE_STEP) % COLOR_COUNT;
    }
    usedColorIndexes.add(colorIndex);
    colors.set(dateKey, colorFromIndex(colorIndex));
  });

  return colors;
}
