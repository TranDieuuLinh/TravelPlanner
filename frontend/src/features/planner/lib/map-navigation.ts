export type LatitudeLongitude = [number, number];

const EARTH_RADIUS_METERS = 6_371_000;

function toRadians(degrees: number): number {
  return (degrees * Math.PI) / 180;
}

export function coordinateDistanceMeters(
  from: LatitudeLongitude,
  to: LatitudeLongitude
): number {
  const fromLatitude = toRadians(from[0]);
  const toLatitude = toRadians(to[0]);
  const latitudeDelta = toLatitude - fromLatitude;
  const longitudeDelta = toRadians(to[1] - from[1]);
  const haversine =
    Math.sin(latitudeDelta / 2) ** 2 +
    Math.cos(fromLatitude) *
      Math.cos(toLatitude) *
      Math.sin(longitudeDelta / 2) ** 2;

  return (
    EARTH_RADIUS_METERS *
    2 *
    Math.atan2(Math.sqrt(haversine), Math.sqrt(Math.max(0, 1 - haversine)))
  );
}

export function coordinateBearing(
  from: LatitudeLongitude,
  to: LatitudeLongitude
): number | null {
  if (coordinateDistanceMeters(from, to) < 0.5) return null;

  const fromLatitude = toRadians(from[0]);
  const toLatitude = toRadians(to[0]);
  const longitudeDelta = toRadians(to[1] - from[1]);
  const y = Math.sin(longitudeDelta) * Math.cos(toLatitude);
  const x =
    Math.cos(fromLatitude) * Math.sin(toLatitude) -
    Math.sin(fromLatitude) *
      Math.cos(toLatitude) *
      Math.cos(longitudeDelta);

  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
}

/**
 * Finds the forward direction of a route close to the user's current position.
 * Tiny geometry segments are skipped so GPS/route noise does not rotate the map.
 */
export function routeForwardBearing(
  currentLocation: LatitudeLongitude,
  routeCoordinates: LatitudeLongitude[],
  minimumLookAheadMeters = 8
): number | null {
  if (routeCoordinates.length < 2) return null;

  let nearestIndex = 0;
  let nearestDistance = Number.POSITIVE_INFINITY;
  routeCoordinates.forEach((coordinate, index) => {
    const distance = coordinateDistanceMeters(currentLocation, coordinate);
    if (distance < nearestDistance) {
      nearestDistance = distance;
      nearestIndex = index;
    }
  });

  const routeStart = routeCoordinates[nearestIndex];
  for (let index = nearestIndex + 1; index < routeCoordinates.length; index += 1) {
    const candidate = routeCoordinates[index];
    if (coordinateDistanceMeters(routeStart, candidate) >= minimumLookAheadMeters) {
      return coordinateBearing(routeStart, candidate);
    }
  }

  return null;
}
