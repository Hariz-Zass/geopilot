from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
import math

import httpx


DEFAULT_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
ALTERNATE_OVERPASS_URL = "https://overpass.kumi.systems/api/interpreter"
DEFAULT_TIMEOUT_SECONDS = 30.0

MIN_BUFFER_METERS = 50.0
MAX_BUFFER_METERS = 5000.0

MIN_FEATURE_LIMIT = 1
MAX_FEATURE_LIMIT = 5000


class SiteContextAcquisitionError(Exception):
    """Fail-closed site-context provider error."""


def _overpass_http_error_message(
    exc: httpx.HTTPError,
) -> str:
    if isinstance(exc, httpx.TimeoutException):
        classification = "timeout"
    elif isinstance(exc, httpx.ConnectError):
        classification = "connection error"
    elif isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code

        if status_code == 429:
            classification = "HTTP 429"
        elif 400 <= status_code < 500:
            classification = "HTTP 4XX"
        elif 500 <= status_code < 600:
            classification = "HTTP 5XX"
        else:
            classification = "HTTP error"
    else:
        classification = "HTTP error"

    return (
        "OpenStreetMap Overpass provider unavailable "
        f"({classification})."
    )


def _is_retryable_overpass_error(
    exc: httpx.HTTPError,
) -> bool:
    if isinstance(
        exc,
        (httpx.TimeoutException, httpx.ConnectError),
    ):
        return True

    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        return status_code == 429 or 500 <= status_code < 600

    return False


@dataclass(frozen=True)
class SiteContextFeature:
    provider: str
    source_feature_id: str
    geometry: dict[str, Any]
    properties: dict[str, Any]


@dataclass(frozen=True)
class SiteContextAcquisitionResult:
    provider: str
    source_uri: str
    query_bbox: tuple[float, float, float, float]
    buffer_meters: float
    raw_element_count: int
    features: tuple[SiteContextFeature, ...]
    truncated: bool


class SiteContextProvider(Protocol):
    name: str

    def acquire(
        self,
        *,
        site_geometry: dict[str, Any],
        buffer_meters: float = 1000.0,
        max_features: int = 1000,
    ) -> SiteContextAcquisitionResult:
        ...


def _geometry_points(
    geometry: dict[str, Any],
) -> list[tuple[float, float]]:
    if not isinstance(geometry, dict):
        raise SiteContextAcquisitionError(
            "Site geometry must be a GeoJSON object."
        )

    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")

    if geometry_type not in {"Polygon", "MultiPolygon"}:
        raise SiteContextAcquisitionError(
            "Site context acquisition requires a Polygon "
            "or MultiPolygon site geometry."
        )

    points: list[tuple[float, float]] = []

    def walk(value: Any) -> None:
        if (
            isinstance(value, (list, tuple))
            and len(value) >= 2
            and isinstance(value[0], (int, float))
            and isinstance(value[1], (int, float))
        ):
            lon = float(value[0])
            lat = float(value[1])

            if not math.isfinite(lon) or not math.isfinite(lat):
                raise SiteContextAcquisitionError(
                    "Site geometry contains non-finite coordinates."
                )

            if lon < -180 or lon > 180 or lat < -90 or lat > 90:
                raise SiteContextAcquisitionError(
                    "Site geometry coordinates are outside WGS84 bounds."
                )

            points.append((lon, lat))
            return

        if isinstance(value, (list, tuple)):
            for item in value:
                walk(item)

    walk(coordinates)

    if not points:
        raise SiteContextAcquisitionError(
            "Site geometry contains no usable coordinates."
        )

    return points


def site_context_bbox(
    site_geometry: dict[str, Any],
    *,
    buffer_meters: float,
) -> tuple[float, float, float, float]:
    try:
        buffer_value = float(buffer_meters)
    except (TypeError, ValueError) as exc:
        raise SiteContextAcquisitionError(
            "Context buffer must be numeric."
        ) from exc

    if not MIN_BUFFER_METERS <= buffer_value <= MAX_BUFFER_METERS:
        raise SiteContextAcquisitionError(
            f"Context buffer must be between "
            f"{MIN_BUFFER_METERS:g} and {MAX_BUFFER_METERS:g} metres."
        )

    points = _geometry_points(site_geometry)

    lons = [item[0] for item in points]
    lats = [item[1] for item in points]

    west = min(lons)
    south = min(lats)
    east = max(lons)
    north = max(lats)

    centre_lat = (south + north) / 2.0

    lat_delta = buffer_value / 111_320.0

    lon_scale = max(
        math.cos(math.radians(centre_lat)),
        0.01,
    )

    lon_delta = buffer_value / (111_320.0 * lon_scale)

    west = max(-180.0, west - lon_delta)
    east = min(180.0, east + lon_delta)
    south = max(-90.0, south - lat_delta)
    north = min(90.0, north + lat_delta)

    if west >= east or south >= north:
        raise SiteContextAcquisitionError(
            "Derived site-context bounding box is invalid."
        )

    return west, south, east, north


def _overpass_query(
    bbox: tuple[float, float, float, float],
) -> str:
    west, south, east, north = bbox

    box = (
        f"{south:.8f},{west:.8f},"
        f"{north:.8f},{east:.8f}"
    )

    return f"""
[out:json][timeout:25];
(
  nwr["highway"]({box});
  nwr["building"]({box});
  nwr["amenity"]({box});
  nwr["shop"]({box});
  nwr["office"]({box});
  nwr["healthcare"]({box});
  nwr["leisure"]({box});
  nwr["tourism"]({box});
  nwr["public_transport"]({box});
  nwr["railway"]({box});
  nwr["waterway"]({box});
  nwr["natural"]({box});
  nwr["landuse"]({box});
);
out tags center geom;
""".strip()


def _element_geometry(
    element: dict[str, Any],
) -> dict[str, Any] | None:
    element_type = element.get("type")

    if element_type == "node":
        lat = element.get("lat")
        lon = element.get("lon")

        if isinstance(lat, (int, float)) and isinstance(
            lon,
            (int, float),
        ):
            return {
                "type": "Point",
                "coordinates": [
                    float(lon),
                    float(lat),
                ],
            }

        return None

    raw_geometry = element.get("geometry")

    if isinstance(raw_geometry, list):
        coordinates: list[list[float]] = []

        for point in raw_geometry:
            if not isinstance(point, dict):
                continue

            lat = point.get("lat")
            lon = point.get("lon")

            if not isinstance(lat, (int, float)):
                continue

            if not isinstance(lon, (int, float)):
                continue

            coordinates.append(
                [float(lon), float(lat)]
            )

        if len(coordinates) >= 2:
            if (
                len(coordinates) >= 4
                and coordinates[0] == coordinates[-1]
            ):
                return {
                    "type": "Polygon",
                    "coordinates": [coordinates],
                }

            return {
                "type": "LineString",
                "coordinates": coordinates,
            }

    centre = element.get("center")

    if isinstance(centre, dict):
        lat = centre.get("lat")
        lon = centre.get("lon")

        if isinstance(lat, (int, float)) and isinstance(
            lon,
            (int, float),
        ):
            return {
                "type": "Point",
                "coordinates": [
                    float(lon),
                    float(lat),
                ],
            }

    return None


def _primary_category(
    tags: dict[str, Any],
) -> tuple[str | None, str | None]:
    priority = (
        "amenity",
        "highway",
        "public_transport",
        "railway",
        "healthcare",
        "shop",
        "office",
        "leisure",
        "tourism",
        "waterway",
        "natural",
        "landuse",
        "building",
    )

    for key in priority:
        value = tags.get(key)

        if value not in (None, ""):
            return key, str(value)

    return None, None


def _normalize_element(
    element: dict[str, Any],
) -> SiteContextFeature | None:
    element_type = element.get("type")
    element_id = element.get("id")

    if element_type not in {"node", "way", "relation"}:
        return None

    if element_id is None:
        return None

    geometry = _element_geometry(element)

    if geometry is None:
        return None

    raw_tags = element.get("tags")

    tags = (
        dict(raw_tags)
        if isinstance(raw_tags, dict)
        else {}
    )

    category, category_value = _primary_category(tags)

    properties: dict[str, Any] = {
        "osm_element_type": element_type,
        "osm_id": element_id,
        "tags": tags,
    }

    if category is not None:
        properties["category"] = category
        properties["category_value"] = category_value

    name = tags.get("name")

    if name not in (None, ""):
        properties["name"] = str(name)

    return SiteContextFeature(
        provider="openstreetmap_overpass",
        source_feature_id=f"{element_type}/{element_id}",
        geometry=geometry,
        properties=properties,
    )


class OpenStreetMapOverpassProvider:
    name = "openstreetmap_overpass"

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        endpoint: str = DEFAULT_OVERPASS_URL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ):
        if not isinstance(endpoint, str) or not endpoint.startswith(
            "https://"
        ):
            raise SiteContextAcquisitionError(
                "Overpass endpoint must use HTTPS."
            )

        if timeout_seconds <= 0 or timeout_seconds > 120:
            raise SiteContextAcquisitionError(
                "Overpass timeout must be between 0 and 120 seconds."
            )

        self._client = client
        self._endpoint = endpoint
        self._timeout_seconds = float(timeout_seconds)
        self._endpoint_candidates = (
            endpoint,
            ALTERNATE_OVERPASS_URL,
        )

    def acquire(
        self,
        *,
        site_geometry: dict[str, Any],
        buffer_meters: float = 1000.0,
        max_features: int = 1000,
    ) -> SiteContextAcquisitionResult:
        if not isinstance(max_features, int):
            raise SiteContextAcquisitionError(
                "Feature limit must be an integer."
            )

        if not MIN_FEATURE_LIMIT <= max_features <= MAX_FEATURE_LIMIT:
            raise SiteContextAcquisitionError(
                f"Feature limit must be between "
                f"{MIN_FEATURE_LIMIT} and {MAX_FEATURE_LIMIT}."
            )

        bbox = site_context_bbox(
            site_geometry,
            buffer_meters=buffer_meters,
        )

        query = _overpass_query(bbox)

        own_client = self._client is None

        client = self._client or httpx.Client(
            timeout=httpx.Timeout(
                self._timeout_seconds
            ),
            follow_redirects=False,
            headers={
                "User-Agent": (
                    "GeoPilotAI/1.0 "
                    "(site-context-acquisition)"
                )
            },
        )

        try:
            response = None
            response_endpoint = self._endpoint

            for attempt, endpoint in enumerate(
                self._endpoint_candidates
            ):
                try:
                    response = client.post(
                        endpoint,
                        content=query.encode("utf-8"),
                        headers={
                            "Content-Type": (
                                "application/x-www-form-urlencoded"
                            )
                        },
                    )

                    response.raise_for_status()
                    response_endpoint = endpoint
                    break

                except httpx.HTTPError as exc:
                    if (
                        attempt == 0
                        and _is_retryable_overpass_error(exc)
                    ):
                        continue

                    raise SiteContextAcquisitionError(
                        _overpass_http_error_message(exc)
                    ) from exc

            if response is None:
                raise SiteContextAcquisitionError(
                    "OpenStreetMap Overpass provider unavailable."
                )

            try:
                payload = response.json()
            except ValueError as exc:
                raise SiteContextAcquisitionError(
                    "OpenStreetMap Overpass returned invalid JSON."
                ) from exc

            if not isinstance(payload, dict):
                raise SiteContextAcquisitionError(
                    "OpenStreetMap Overpass returned an invalid payload."
                )

            elements = payload.get("elements")

            if not isinstance(elements, list):
                raise SiteContextAcquisitionError(
                    "OpenStreetMap Overpass response did not contain elements."
                )

            normalized: list[SiteContextFeature] = []

            for element in elements:
                if not isinstance(element, dict):
                    continue

                feature = _normalize_element(element)

                if feature is None:
                    continue

                normalized.append(feature)

                if len(normalized) >= max_features:
                    break

            return SiteContextAcquisitionResult(
                provider=self.name,
                source_uri=response_endpoint,
                query_bbox=bbox,
                buffer_meters=float(buffer_meters),
                raw_element_count=len(elements),
                features=tuple(normalized),
                truncated=(
                    len(normalized) >= max_features
                    and len(elements) > len(normalized)
                ),
            )

        finally:
            if own_client:
                client.close()
