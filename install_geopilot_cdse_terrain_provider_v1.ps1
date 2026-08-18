$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Terrain = Join-Path $Root "backend\app\services\terrain_acquisition.py"
$Tests = Join-Path $Root "backend\tests\test_terrain_acquisition.py"
$EnvExample = Join-Path $Root ".env.example"

if (!(Test-Path $Terrain) -or !(Test-Path $Tests) -or !(Test-Path $EnvExample)) {
    throw "Required GeoPilot files are missing. Run this installer from the geopilot_v7 project root."
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Backup = Join-Path $Root "artifacts\cdse_terrain_provider_v1_backup_$stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $Terrain (Join-Path $Backup "terrain_acquisition.py")
Copy-Item $Tests (Join-Path $Backup "test_terrain_acquisition.py")
Copy-Item $EnvExample (Join-Path $Backup ".env.example")
Write-Host "BACKUP: $Backup"

$terrainText = Get-Content -Raw -Encoding UTF8 $Terrain
if ($terrainText -match 'CDSE_TOKEN_URL = "https://identity\.dataspace\.copernicus\.eu') {
    Write-Host "CDSE Terrain Provider V1 already appears installed. No source patch applied."
} else {
    $old = @'
class CopernicusDemProvider:
    """
    Provider adapter boundary.

    V1 deliberately fails closed until CDSE credentials are configured.
    It does not silently scrape public endpoints or infer credentials.
    The next gate will bind this adapter to the official CDSE DEM process API.
    """

    name = "copernicus_cdse"

    def acquire(
        self,
        *,
        site_geometry: dict,
        target_crs: str,
    ) -> AcquiredTerrainArtifact:
        settings = get_settings()
        if not settings.terrain_cdse_client_id or not settings.terrain_cdse_client_secret:
            raise TerrainAcquisitionError(
                "Automatic Copernicus DEM acquisition is not configured. "
                "CDSE OAuth client credentials are required."
            )
        raise TerrainAcquisitionError(
            "Copernicus provider credentials are configured, but network acquisition "
            "is intentionally disabled until the provider acceptance gate is installed."
        )
'@

    $new = @'
CDSE_TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
CDSE_PROCESS_URL = "https://sh.dataspace.copernicus.eu/process/v1"
CDSE_DEM_COLLECTION = "COPERNICUS_30"
CDSE_DEM_RESOLUTION_DEGREES = 0.0003
CDSE_HTTP_TIMEOUT_SECONDS = 60.0
CDSE_MAX_DEM_BYTES = 256 * 1024 * 1024

_CDSE_DEM_EVALSCRIPT = """//VERSION=3
function setup() {
  return {
    input: ["DEM"],
    output: {
      id: "default",
      bands: 1,
      sampleType: SampleType.FLOAT32
    }
  }
}
function evaluatePixel(sample) {
  return [sample.DEM]
}
"""


def _geometry_bbox(site_geometry: dict) -> list[float]:
    try:
        geom_type = site_geometry.get("type")
        coordinates = site_geometry.get("coordinates")
        if geom_type not in {"Polygon", "MultiPolygon"} or not coordinates:
            raise ValueError("unsupported geometry")

        points: list[tuple[float, float]] = []

        def walk(value: object) -> None:
            if (
                isinstance(value, (list, tuple))
                and len(value) >= 2
                and isinstance(value[0], (int, float))
                and isinstance(value[1], (int, float))
            ):
                points.append((float(value[0]), float(value[1])))
                return
            if isinstance(value, (list, tuple)):
                for item in value:
                    walk(item)

        walk(coordinates)
        if not points:
            raise ValueError("empty geometry")

        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        bbox = [min(xs), min(ys), max(xs), max(ys)]
        if bbox[0] >= bbox[2] or bbox[1] >= bbox[3]:
            raise ValueError("degenerate bounds")
        if bbox[0] < -180 or bbox[2] > 180 or bbox[1] < -90 or bbox[3] > 90:
            raise ValueError("bounds are not CRS84 longitude/latitude")
        return bbox
    except (AttributeError, TypeError, ValueError) as exc:
        raise TerrainAcquisitionError(
            "Site geometry must be a valid Polygon/MultiPolygon in CRS84/WGS84 for CDSE DEM acquisition."
        ) from exc


class CopernicusDemProvider:
    """Official CDSE Sentinel Hub Process API adapter for Copernicus DEM GLO-30."""

    name = "copernicus_cdse"

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        token_url: str = CDSE_TOKEN_URL,
        process_url: str = CDSE_PROCESS_URL,
    ):
        self._client = client
        self._token_url = token_url
        self._process_url = process_url

    def _request_token(self, client: httpx.Client, *, client_id: str, client_secret: str) -> str:
        try:
            response = client.post(
                self._token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except httpx.HTTPError as exc:
            raise TerrainAcquisitionError("CDSE OAuth token endpoint could not be reached.") from exc

        if response.status_code < 200 or response.status_code >= 300:
            raise TerrainAcquisitionError(
                f"CDSE OAuth authentication failed with HTTP {response.status_code}."
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise TerrainAcquisitionError("CDSE OAuth returned an invalid token response.") from exc

        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token.strip():
            raise TerrainAcquisitionError("CDSE OAuth response did not contain an access token.")
        return token

    def _process_payload(self, bbox: list[float]) -> dict:
        return {
            "input": {
                "bounds": {
                    "properties": {
                        "crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"
                    },
                    "bbox": bbox,
                },
                "data": [
                    {
                        "type": "dem",
                        "dataFilter": {"demInstance": CDSE_DEM_COLLECTION},
                        "processing": {
                            "upsampling": "BILINEAR",
                            "downsampling": "BILINEAR",
                        },
                    }
                ],
            },
            "output": {
                "resx": CDSE_DEM_RESOLUTION_DEGREES,
                "resy": CDSE_DEM_RESOLUTION_DEGREES,
                "responses": [
                    {
                        "identifier": "default",
                        "format": {"type": "image/tiff"},
                    }
                ],
            },
            "evalscript": _CDSE_DEM_EVALSCRIPT,
        }

    def acquire(
        self,
        *,
        site_geometry: dict,
        target_crs: str,
    ) -> AcquiredTerrainArtifact:
        settings = get_settings()
        client_id = settings.terrain_cdse_client_id
        client_secret = settings.terrain_cdse_client_secret
        if not client_id or not client_secret:
            raise TerrainAcquisitionError(
                "Automatic Copernicus DEM acquisition is not configured. "
                "CDSE OAuth client credentials are required."
            )

        bbox = _geometry_bbox(site_geometry)
        owns_client = self._client is None
        client = self._client or httpx.Client(
            timeout=httpx.Timeout(CDSE_HTTP_TIMEOUT_SECONDS),
            follow_redirects=False,
        )

        try:
            token = self._request_token(
                client,
                client_id=client_id,
                client_secret=client_secret,
            )
            try:
                response = client.post(
                    self._process_url,
                    json=self._process_payload(bbox),
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "image/tiff",
                    },
                )
            except httpx.HTTPError as exc:
                raise TerrainAcquisitionError("CDSE DEM Process API could not be reached.") from exc

            if response.status_code < 200 or response.status_code >= 300:
                raise TerrainAcquisitionError(
                    f"CDSE DEM Process API failed with HTTP {response.status_code}."
                )

            content_type = response.headers.get("content-type", "").lower()
            data = response.content
            if len(data) == 0:
                raise TerrainAcquisitionError("CDSE DEM Process API returned an empty response.")
            if len(data) > CDSE_MAX_DEM_BYTES:
                raise TerrainAcquisitionError("CDSE DEM response exceeded the configured safety limit.")
            if "json" in content_type or "html" in content_type:
                raise TerrainAcquisitionError("CDSE DEM Process API returned a non-raster payload.")

            try:
                with MemoryFile(data) as mem:
                    with mem.open() as ds:
                        if ds.driver != "GTiff" or ds.count < 1 or ds.crs is None:
                            raise TerrainAcquisitionError("CDSE DEM response is not a valid georeferenced GeoTIFF.")
                        original_crs = ds.crs.to_string()
                        width = ds.width
                        height = ds.height
                        dtype = ds.dtypes[0]
            except TerrainAcquisitionError:
                raise
            except Exception as exc:
                raise TerrainAcquisitionError("CDSE DEM response could not be opened as GeoTIFF.") from exc

            bbox_ref = ",".join(f"{x:.6f}" for x in bbox)
            return AcquiredTerrainArtifact(
                data=data,
                provider=self.name,
                collection="copernicus-dem-glo-30",
                scene_id=f"cdse-dem-glo30-{hashlib.sha256(bbox_ref.encode('utf-8')).hexdigest()[:16]}",
                acquisition_datetime=None,
                source_reference=self._process_url,
                original_crs=original_crs,
                metadata={
                    "dataset": "Copernicus DEM GLO-30",
                    "dem_instance": CDSE_DEM_COLLECTION,
                    "requested_bbox_crs": "CRS84",
                    "requested_bbox": bbox,
                    "requested_resolution_degrees": CDSE_DEM_RESOLUTION_DEGREES,
                    "returned_width": width,
                    "returned_height": height,
                    "returned_dtype": dtype,
                    "normalization_target_crs": target_crs,
                },
            )
        finally:
            if owns_client:
                client.close()
'@

    if (-not $terrainText.Contains($old)) {
        throw "Expected CopernicusDemProvider placeholder was not found exactly. No source file was modified."
    }
    $terrainText = $terrainText.Replace($old, $new)
    Set-Content -Path $Terrain -Value $terrainText -Encoding UTF8
    Write-Host "PATCHED: backend\app\services\terrain_acquisition.py"

    $testsText = Get-Content -Raw -Encoding UTF8 $Tests
    $testsAppend = @'


def test_cdse_provider_uses_official_oauth_and_process_contract(monkeypatch):
    import json
    import httpx

    from app.core.config import get_settings
    from app.services.terrain_acquisition import CopernicusDemProvider

    get_settings.cache_clear()
    monkeypatch.setenv("TERRAIN_CDSE_CLIENT_ID", "test-client")
    monkeypatch.setenv("TERRAIN_CDSE_CLIENT_SECRET", "test-secret")
    get_settings.cache_clear()

    dem_bytes = _fake_dem_bytes()
    seen = {"token": None, "process": None}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/protocol/openid-connect/token"):
            body = request.content.decode("utf-8")
            seen["token"] = body
            assert "grant_type=client_credentials" in body
            assert "client_id=test-client" in body
            assert "client_secret=test-secret" in body
            return httpx.Response(200, json={"access_token": "unit-test-token", "expires_in": 300})

        if request.url.path == "/process/v1":
            assert request.headers.get("authorization") == "Bearer unit-test-token"
            payload = json.loads(request.content.decode("utf-8"))
            seen["process"] = payload
            assert payload["input"]["data"][0]["type"] == "dem"
            assert payload["input"]["data"][0]["dataFilter"]["demInstance"] == "COPERNICUS_30"
            assert payload["output"]["responses"][0]["format"]["type"] == "image/tiff"
            return httpx.Response(200, content=dem_bytes, headers={"content-type": "image/tiff"})

        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        artifact = CopernicusDemProvider(client=client).acquire(
            site_geometry={
                "type": "Polygon",
                "coordinates": [[[101.60, 3.00], [101.61, 3.00], [101.61, 3.01], [101.60, 3.01], [101.60, 3.00]]],
            },
            target_crs="EPSG:32647",
        )

    assert artifact.provider == "copernicus_cdse"
    assert artifact.collection == "copernicus-dem-glo-30"
    assert artifact.metadata["dem_instance"] == "COPERNICUS_30"
    assert seen["token"] is not None
    assert seen["process"] is not None
    get_settings.cache_clear()


def test_cdse_provider_rejects_failed_oauth(monkeypatch):
    import httpx
    import pytest

    from app.core.config import get_settings
    from app.services.terrain_acquisition import CopernicusDemProvider, TerrainAcquisitionError

    get_settings.cache_clear()
    monkeypatch.setenv("TERRAIN_CDSE_CLIENT_ID", "bad-client")
    monkeypatch.setenv("TERRAIN_CDSE_CLIENT_SECRET", "bad-secret")
    get_settings.cache_clear()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid_client"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(TerrainAcquisitionError, match="HTTP 401"):
            CopernicusDemProvider(client=client).acquire(
                site_geometry={
                    "type": "Polygon",
                    "coordinates": [[[101.60, 3.00], [101.61, 3.00], [101.61, 3.01], [101.60, 3.01], [101.60, 3.00]]],
                },
                target_crs="EPSG:32647",
            )
    get_settings.cache_clear()


def _fake_dem_bytes() -> bytes:
    from rasterio.transform import from_origin

    profile = {
        "driver": "GTiff",
        "height": 4,
        "width": 4,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": from_origin(101.60, 3.01, 0.0025, 0.0025),
    }
    with MemoryFile() as mem:
        with mem.open(**profile) as ds:
            ds.write(np.arange(16, dtype="float32").reshape(1, 4, 4))
        return mem.read()
'@
    if ($testsText -notmatch 'test_cdse_provider_uses_official_oauth_and_process_contract') {
        Add-Content -Path $Tests -Value $testsAppend -Encoding UTF8
        Write-Host "PATCHED: backend\tests\test_terrain_acquisition.py"
    }

    $envText = Get-Content -Raw -Encoding UTF8 $EnvExample
    if ($envText -notmatch 'TERRAIN_AUTO_ACQUISITION_ENABLED=') {
        $envAppend = @'

# Automatic terrain acquisition (CDSE Copernicus DEM GLO-30)
# Real OAuth credentials belong only in the local .env, never in source control.
TERRAIN_AUTO_ACQUISITION_ENABLED=false
TERRAIN_AUTO_PROVIDER=copernicus_cdse
TERRAIN_AUTO_TARGET_CRS=EPSG:32647
TERRAIN_CDSE_CLIENT_ID=
TERRAIN_CDSE_CLIENT_SECRET=
'@
        Add-Content -Path $EnvExample -Value $envAppend -Encoding UTF8
        Write-Host "PATCHED: .env.example (placeholders only)"
    }
}

Write-Host ""
Write-Host "Running syntax check..."
docker compose exec -T backend python -m py_compile app/services/terrain_acquisition.py
if ($LASTEXITCODE -ne 0) { throw "Python syntax check failed." }

Write-Host "Running focused terrain tests..."
docker compose exec -T backend pytest -q tests/test_terrain_acquisition.py
if ($LASTEXITCODE -ne 0) { throw "Focused terrain tests failed." }

Write-Host ""
Write-Host "Runtime configuration presence (values hidden):"
docker compose exec -T backend python -c "from app.core.config import get_settings; s=get_settings(); print('CLIENT_ID configured:', bool(s.terrain_cdse_client_id)); print('CLIENT_SECRET configured:', bool(s.terrain_cdse_client_secret)); print('AUTO_ACQUISITION_ENABLED:', s.terrain_auto_acquisition_enabled); print('PROVIDER:', s.terrain_auto_provider)"
if ($LASTEXITCODE -ne 0) { throw "Runtime configuration check failed." }

Write-Host ""
Write-Host "============================================================"
Write-Host "CDSE TERRAIN PROVIDER SOURCE INSTALL V1 PASS"
Write-Host "Official OAuth + Process API contract installed."
Write-Host "Copernicus DEM GLO-30 configured at ~0.0003 degree request resolution."
Write-Host "Manual DEM precedence path was not modified."
Write-Host "No DB migration. No frontend change. .env untouched."
Write-Host "LIVE network acceptance has NOT been run by this installer."
Write-Host "============================================================"
