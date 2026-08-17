from app.db.readiness import _evaluate_rows


def _row(extension: str, version: str) -> dict[str, object]:
    return {
        "database_name": "geopilot",
        "database_user": "geopilot",
        "server_version_num": 160010,
        "server_version": "16.10",
        "extname": extension,
        "extversion": version,
    }


def test_database_ready_with_postgis_and_vector() -> None:
    result = _evaluate_rows([_row("postgis", "3.5.3"), _row("vector", "0.8.1")])
    assert result.ready is True
    assert result.missing_extensions == ()
    assert result.extensions == {"postgis": "3.5.3", "vector": "0.8.1"}


def test_database_not_ready_when_vector_is_missing() -> None:
    result = _evaluate_rows([_row("postgis", "3.5.3")])
    assert result.ready is False
    assert result.missing_extensions == ("vector",)
    assert "vector" in (result.error or "")


def test_database_not_ready_on_unsupported_postgres() -> None:
    row = _row("postgis", "3.5.3")
    row["server_version_num"] = 150014
    vector = dict(row)
    vector["extname"] = "vector"
    vector["extversion"] = "0.8.1"
    result = _evaluate_rows([row, vector])
    assert result.ready is False
    assert result.error == "PostgreSQL 16 or newer is required"


def test_empty_capability_result_fails_closed() -> None:
    result = _evaluate_rows([])
    assert result.ready is False
    assert result.missing_extensions == ("postgis", "vector")
