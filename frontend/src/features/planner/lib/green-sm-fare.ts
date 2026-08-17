export const GREEN_SM_FARE_URL =
  "https://www.greensm.com/vn-en";

const OPENING_DISTANCE_METERS = 2_000;
const OPENING_FARE = 30_500;
const RATE_TO_12_KM = 14_700;
const RATE_TO_25_KM = 13_800;
const RATE_AFTER_25_KM = 11_900;
const PLANNING_BUFFER_PERCENT = 15;

// Compatibility fallback for plans created before route-level fare was saved.
// Keep these values aligned with green-sm-car-hanoi-public-v1 in the backend.
export function estimateGreenSmHanoiFare(distanceMeters: number): number {
  const distance = Math.max(0, Math.round(distanceMeters));
  if (distance === 0) return 0;

  let fare = OPENING_FARE;
  let remaining = Math.max(0, distance - OPENING_DISTANCE_METERS);
  const firstTier = Math.min(remaining, 10_000);
  fare += (firstTier / 1_000) * RATE_TO_12_KM;
  remaining -= firstTier;

  const secondTier = Math.min(remaining, 13_000);
  fare += (secondTier / 1_000) * RATE_TO_25_KM;
  remaining -= secondTier;

  if (remaining > 0) {
    fare += (remaining / 1_000) * RATE_AFTER_25_KM;
  }

  return Math.ceil(fare * (1 + PLANNING_BUFFER_PERCENT / 100));
}
