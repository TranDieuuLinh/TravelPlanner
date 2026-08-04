from __future__ import annotations


def decode_polyline(
    value: str,
    *,
    precision: int,
) -> list[tuple[float, float]]:
    """Decode a Google-style encoded polyline into latitude/longitude pairs."""
    coordinates: list[tuple[float, float]] = []
    latitude = 0
    longitude = 0
    index = 0
    factor = 10**precision
    while index < len(value):
        latitude_delta, index = _decode_value(value, index)
        longitude_delta, index = _decode_value(value, index)
        latitude += latitude_delta
        longitude += longitude_delta
        coordinates.append((latitude / factor, longitude / factor))
    return coordinates


def _decode_value(value: str, index: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        if index >= len(value):
            raise ValueError("Encoded polyline ended unexpectedly.")
        chunk = ord(value[index]) - 63
        if chunk < 0:
            raise ValueError("Encoded polyline contains an invalid character.")
        index += 1
        result |= (chunk & 0x1F) << shift
        shift += 5
        if chunk < 0x20:
            break
    decoded = ~(result >> 1) if result & 1 else result >> 1
    return decoded, index
