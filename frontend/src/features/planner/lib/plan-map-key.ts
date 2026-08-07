export function planItemMapKey(input: {
  day: number;
  itemId?: string | null;
  itemIndex: number;
  name: string;
}): string {
  const stableIdentity = input.itemId?.trim();
  if (stableIdentity) {
    return `plan-${input.day}-item-${stableIdentity}`;
  }

  return `plan-${input.day}-position-${input.itemIndex}-${input.name}`;
}
