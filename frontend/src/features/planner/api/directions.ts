import { apiFetch } from "@/shared/api/client";
import type {
  CurrentLocationRouteInput,
  DayDirectionsInput,
  TransportLeg,
} from "@/features/planner/contracts/transport";

export async function calculateCurrentLocationRoute(
  input: CurrentLocationRouteInput
): Promise<TransportLeg> {
  return apiFetch<TransportLeg>("/v1/plans/current-location-route", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function calculateDayDirections(
  input: DayDirectionsInput
): Promise<TransportLeg[]> {
  return apiFetch<TransportLeg[]>("/v1/plans/day-directions", {
    method: "POST",
    body: JSON.stringify(input),
  });
}
