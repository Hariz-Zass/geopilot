from __future__ import annotations

import json

import httpx
import pytest

from app.services.site_context_acquisition import (
    ALTERNATE_OVERPASS_URL,
    DEFAULT_OVERPASS_URL,
    OpenStreetMapOverpassProvider,
    SiteContextAcquisitionError,
    site_context_bbox,
)


SITE = {
    "type": "Polygon",
    "coordinates": [
        [
            [101.5000, 3.0000],
            [101.5100, 3.0000],
            [101.5100, 3.0100],
            [101.5000, 3.0100],
            [101.5000, 3.0000],
        ]
    ],
}


def test_bbox_expands_site_geometry():
    west, south, east, north = site_context_bbox(
        SITE,
        buffer_meters=1000,
    )

    assert west < 101.5000
    assert east > 101.5100
    assert south < 3.0000
    assert north > 3.0100


def test_bbox_rejects_non_polygon():
    with pytest.raises(SiteContextAcquisitionError):
        site_context_bbox(
            {
                "type": "Point",
                "coordinates": [101.5, 3.0],
            },
            buffer_meters=1000,
        )


def test_bbox_rejects_oversized_buffer():
    with pytest.raises(SiteContextAcquisitionError):
        site_context_bbox(
            SITE,
            buffer_meters=10000,
        )


def test_provider_requires_https():
    with pytest.raises(SiteContextAcquisitionError):
        OpenStreetMapOverpassProvider(
            endpoint="http://example.test/overpass"
        )


def test_provider_normalizes_osm_elements():
    payload = {
        "elements": [
            {
                "type": "node",
                "id": 100,
                "lat": 3.005,
                "lon": 101.505,
                "tags": {
                    "amenity": "school",
                    "name": "Sekolah Contoh",
                },
            },
            {
                "type": "way",
                "id": 200,
                "tags": {
                    "highway": "primary",
                    "name": "Jalan Contoh",
                },
                "geometry": [
                    {"lat": 3.001, "lon": 101.501},
                    {"lat": 3.002, "lon": 101.502},
                ],
            },
            {
                "type": "way",
                "id": 300,
                "tags": {
                    "building": "yes",
                },
                "geometry": [
                    {"lat": 3.003, "lon": 101.503},
                    {"lat": 3.003, "lon": 101.504},
                    {"lat": 3.004, "lon": 101.504},
                    {"lat": 3.003, "lon": 101.503},
                ],
            },
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == (
            "https://overpass-api.de/api/interpreter"
        )

        body = request.content.decode("utf-8")

        assert 'nwr["highway"]' in body
        assert 'nwr["amenity"]' in body
        assert 'nwr["waterway"]' in body
        assert 'nwr["landuse"]' in body

        return httpx.Response(
            200,
            json=payload,
            request=request,
        )

    client = httpx.Client(
        transport=httpx.MockTransport(handler)
    )

    provider = OpenStreetMapOverpassProvider(
        client=client
    )

    result = provider.acquire(
        site_geometry=SITE,
        buffer_meters=1000,
        max_features=100,
    )

    assert result.provider == "openstreetmap_overpass"
    assert result.raw_element_count == 3
    assert len(result.features) == 3
    assert result.truncated is False

    school = result.features[0]

    assert school.source_feature_id == "node/100"
    assert school.geometry["type"] == "Point"
    assert school.properties["category"] == "amenity"
    assert school.properties["category_value"] == "school"
    assert school.properties["name"] == "Sekolah Contoh"

    road = result.features[1]

    assert road.source_feature_id == "way/200"
    assert road.geometry["type"] == "LineString"
    assert road.properties["category"] == "highway"

    building = result.features[2]

    assert building.geometry["type"] == "Polygon"
    assert building.properties["category"] == "building"

    client.close()


def test_provider_skips_elements_without_usable_geometry():
    payload = {
        "elements": [
            {
                "type": "relation",
                "id": 400,
                "tags": {
                    "landuse": "residential"
                },
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=payload,
            request=request,
        )

    client = httpx.Client(
        transport=httpx.MockTransport(handler)
    )

    result = OpenStreetMapOverpassProvider(
        client=client
    ).acquire(
        site_geometry=SITE,
    )

    assert result.raw_element_count == 1
    assert result.features == ()

    client.close()


def test_provider_fails_closed_on_http_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            request=request,
        )

    client = httpx.Client(
        transport=httpx.MockTransport(handler)
    )

    provider = OpenStreetMapOverpassProvider(
        client=client
    )

    with pytest.raises(
        SiteContextAcquisitionError,
        match="provider unavailable",
    ):
        provider.acquire(
            site_geometry=SITE,
        )

    client.close()


@pytest.mark.parametrize(
    ("error", "classification"),
    [
        (
            httpx.ReadTimeout("timed out"),
            "timeout",
        ),
        (
            httpx.ConnectError("connection failed"),
            "connection error",
        ),
        (
            httpx.ProtocolError("protocol failed"),
            "HTTP error",
        ),
    ],
)
def test_provider_classifies_transport_errors(error, classification):
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    client = httpx.Client(
        transport=httpx.MockTransport(handler)
    )

    with pytest.raises(
        SiteContextAcquisitionError,
        match=(
            "OpenStreetMap Overpass provider unavailable "
            rf"\({classification}\)\."
        ),
    ) as raised:
        OpenStreetMapOverpassProvider(
            client=client
        ).acquire(site_geometry=SITE)

    assert raised.value.__cause__ is error
    assert "timed out" not in str(raised.value)
    assert "connection failed" not in str(raised.value)
    assert "protocol failed" not in str(raised.value)

    client.close()


@pytest.mark.parametrize(
    ("status_code", "classification"),
    [
        (429, "HTTP 429"),
        (404, "HTTP 4XX"),
        (503, "HTTP 5XX"),
    ],
)
def test_provider_classifies_http_status_errors(
    status_code,
    classification,
):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            content=b"private response details",
            request=request,
        )

    client = httpx.Client(
        transport=httpx.MockTransport(handler)
    )

    with pytest.raises(
        SiteContextAcquisitionError,
        match=(
            "OpenStreetMap Overpass provider unavailable "
            rf"\({classification}\)\."
        ),
    ) as raised:
        OpenStreetMapOverpassProvider(
            client=client
        ).acquire(site_geometry=SITE)

    assert raised.value.__cause__.response.status_code == status_code
    assert "private response details" not in str(raised.value)

    client.close()


def test_provider_fails_closed_on_invalid_payload():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"not-json",
            request=request,
        )

    client = httpx.Client(
        transport=httpx.MockTransport(handler)
    )

    provider = OpenStreetMapOverpassProvider(
        client=client
    )

    with pytest.raises(
        SiteContextAcquisitionError,
        match="invalid JSON",
    ):
        provider.acquire(
            site_geometry=SITE,
        )

    client.close()


def test_feature_limit_is_enforced():
    payload = {
        "elements": [
            {
                "type": "node",
                "id": index,
                "lat": 3.0 + index / 10000,
                "lon": 101.5,
                "tags": {
                    "amenity": "bench",
                },
            }
            for index in range(1, 6)
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=payload,
            request=request,
        )

    client = httpx.Client(
        transport=httpx.MockTransport(handler)
    )

    result = OpenStreetMapOverpassProvider(
        client=client
    ).acquire(
        site_geometry=SITE,
        max_features=2,
    )

    assert len(result.features) == 2
    assert result.truncated is True

    client.close()


def _alternate_failover_payload():
    return {
        "elements": [
            {
                "type": "node",
                "id": 901,
                "lat": 3.005,
                "lon": 101.505,
                "tags": {
                    "amenity": "school",
                    "name": "Sekolah Failover",
                },
            }
        ]
    }


def test_failover_primary_success_does_not_call_alternate():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(
            200,
            json=_alternate_failover_payload(),
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = OpenStreetMapOverpassProvider(client=client).acquire(
        site_geometry=SITE,
    )

    assert calls == [DEFAULT_OVERPASS_URL]
    assert result.source_uri == DEFAULT_OVERPASS_URL
    client.close()


@pytest.mark.parametrize(
    "failure",
    [
        httpx.ReadTimeout("timed out"),
        httpx.ConnectError("connection failed"),
    ],
)
def test_failover_transport_failure_then_alternate_success(failure):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if len(calls) == 1:
            raise failure
        return httpx.Response(
            200,
            json=_alternate_failover_payload(),
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = OpenStreetMapOverpassProvider(client=client).acquire(
        site_geometry=SITE,
    )

    assert calls == [DEFAULT_OVERPASS_URL, ALTERNATE_OVERPASS_URL]
    assert result.source_uri == ALTERNATE_OVERPASS_URL
    assert result.features[0].source_feature_id == "node/901"
    client.close()


@pytest.mark.parametrize("status_code", [429, 503])
def test_failover_retryable_http_failure_then_alternate_success(status_code):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if len(calls) == 1:
            return httpx.Response(status_code, request=request)
        return httpx.Response(
            200,
            json=_alternate_failover_payload(),
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = OpenStreetMapOverpassProvider(client=client).acquire(
        site_geometry=SITE,
    )

    assert calls == [DEFAULT_OVERPASS_URL, ALTERNATE_OVERPASS_URL]
    assert result.source_uri == ALTERNATE_OVERPASS_URL
    client.close()


def test_failover_deterministic_http_4xx_does_not_call_alternate():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(404, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(
        SiteContextAcquisitionError,
        match="HTTP 4XX",
    ):
        OpenStreetMapOverpassProvider(client=client).acquire(
            site_geometry=SITE,
        )

    assert calls == [DEFAULT_OVERPASS_URL]
    client.close()


def test_failover_both_endpoints_fail_closed_without_fabricated_features():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(503, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(
        SiteContextAcquisitionError,
        match="HTTP 5XX",
    ):
        OpenStreetMapOverpassProvider(client=client).acquire(
            site_geometry=SITE,
        )

    assert calls == [DEFAULT_OVERPASS_URL, ALTERNATE_OVERPASS_URL]
    client.close()


def test_failover_response_body_is_not_exposed_in_error():
    secret_body = b"private provider response body"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, content=secret_body, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(SiteContextAcquisitionError) as raised:
        OpenStreetMapOverpassProvider(client=client).acquire(
            site_geometry=SITE,
        )

    assert secret_body.decode() not in str(raised.value)
    client.close()


def test_failover_preserves_source_identity_and_endpoint_traceability():
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == DEFAULT_OVERPASS_URL:
            return httpx.Response(503, request=request)
        return httpx.Response(
            200,
            json=_alternate_failover_payload(),
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = OpenStreetMapOverpassProvider(client=client).acquire(
        site_geometry=SITE,
    )

    feature = result.features[0]
    assert result.provider == "openstreetmap_overpass"
    assert result.source_uri == ALTERNATE_OVERPASS_URL
    assert feature.provider == "openstreetmap_overpass"
    assert feature.source_feature_id == "node/901"
    client.close()
