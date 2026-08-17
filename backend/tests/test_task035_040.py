import uuid,pytest
from app.services.planning_tools import get_tool,ToolRegistryError
from app.schemas.tool_evidence import ToolEvidence,EvidenceSourceRef
from app.services.grounded_synthesis import validate_synthesis,GroundingError
from app.services.planning_orchestrator import _plan

def ev(): return [ToolEvidence(project_id=uuid.uuid4(),tool_name='gis.site_area',deterministic=True,status='measured',payload={'area_hectares':12.5},sources=[EvidenceSourceRef(kind='user_input',id='site:x')])]
def test_tool_registry_rejects_unknown_tool():
 with pytest.raises(ToolRegistryError): get_tool('shell.exec')
def test_density_ambiguity_requires_clarification(): assert _plan('What is the density?')[0]=='clarification_required'
def test_grounding_rejects_invented_number():
 with pytest.raises(GroundingError): validate_synthesis('The site is 99 hectares.',ev())
def test_grounding_allows_evidence_number(): assert validate_synthesis('The measured area is 12.5 hectares.',ev())
def test_grounding_rejects_approval_language():
 with pytest.raises(GroundingError): validate_synthesis('Planning permission is granted.',ev())

def test_grounding_allows_rounded_evidence_number():
    evidence = [
        ToolEvidence(
            project_id=uuid.uuid4(),
            tool_name="gis.site_applicability",
            deterministic=True,
            status="measured",
            payload={"site_overlap_percent": 98.93591040458347},
            sources=[EvidenceSourceRef(kind="user_input", id="site:x")],
        )
    ]
    assert validate_synthesis(
        "The site overlap is 98.94 percent.",
        evidence,
    )


def test_grounding_rejects_unrelated_rounded_number():
    evidence = [
        ToolEvidence(
            project_id=uuid.uuid4(),
            tool_name="gis.site_applicability",
            deterministic=True,
            status="measured",
            payload={"site_overlap_percent": 98.93591040458347},
            sources=[EvidenceSourceRef(kind="user_input", id="site:x")],
        )
    ]
    with pytest.raises(GroundingError):
        validate_synthesis(
            "The site overlap is 75 percent.",
            evidence,
        )

def test_spatial_grounding_accepts_deterministic_classification():
    from app.services.planning_orchestrator import (
        _validate_spatial_classification_answer,
    )

    evidence = [
        ToolEvidence(
            project_id=uuid.uuid4(),
            tool_name="gis.site_applicability",
            deterministic=True,
            status="measured",
            payload={
                "applicability_role": "zoning",
                "properties": {
                    "landuse_type": "Institusi dan Kemudahan Masyarakat",
                    "landuse_code": "INSTITUSI",
                    "bp_code": "BP7",
                },
                "site_overlap_percent": 98.93591040458347,
            },
            sources=[
                EvidenceSourceRef(
                    kind="user_input",
                    id="site:x",
                )
            ],
        )
    ]

    _validate_spatial_classification_answer(
        "What zoning applies to this site?",
        (
            "The site intersects Institusi dan Kemudahan "
            "Masyarakat (INSTITUSI) within BP7."
        ),
        evidence,
    )


def test_spatial_grounding_rejects_missing_classification():
    from app.services.planning_orchestrator import (
        _validate_spatial_classification_answer,
    )

    evidence = [
        ToolEvidence(
            project_id=uuid.uuid4(),
            tool_name="gis.site_applicability",
            deterministic=True,
            status="measured",
            payload={
                "applicability_role": "zoning",
                "properties": {
                    "landuse_type": "Institusi dan Kemudahan Masyarakat",
                    "landuse_code": "INSTITUSI",
                    "bp_code": "BP7",
                },
            },
            sources=[
                EvidenceSourceRef(
                    kind="user_input",
                    id="site:x",
                )
            ],
        )
    ]

    with pytest.raises(GroundingError):
        _validate_spatial_classification_answer(
            "What zoning applies to this site?",
            "The zoning for BP7 cannot be determined.",
            evidence,
        )


def test_spatial_grounding_rejects_wrong_planning_block():
    from app.services.planning_orchestrator import (
        _validate_spatial_classification_answer,
    )

    evidence = [
        ToolEvidence(
            project_id=uuid.uuid4(),
            tool_name="gis.site_applicability",
            deterministic=True,
            status="measured",
            payload={
                "applicability_role": "zoning",
                "properties": {
                    "landuse_type": "Institusi dan Kemudahan Masyarakat",
                    "landuse_code": "INSTITUSI",
                    "bp_code": "BP7",
                },
            },
            sources=[
                EvidenceSourceRef(
                    kind="user_input",
                    id="site:x",
                )
            ],
        )
    ]

    with pytest.raises(GroundingError):
        _validate_spatial_classification_answer(
            "What zoning applies to this site?",
            (
                "The site is Institusi dan Kemudahan "
                "Masyarakat (INSTITUSI) within BP3."
            ),
            evidence,
        )


def test_document_applicability_resolves_matching_planning_documents():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool

    from app.db.base import Base
    from app.models.planning_document import PlanningDocument
    from app.services.planning_orchestrator import (
        _applicable_document_ids,
    )

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(engine)

    project_id = uuid.uuid4()

    with Session(engine) as session:
        allowed_1 = PlanningDocument(
            project_id=project_id,
            title="Rancangan Tempatan Subang Jaya 2035 Jilid 1",
            document_class="RT",
            authority="PLANMalaysia",
            jurisdiction="Majlis Bandaraya Subang Jaya, Selangor",
            geographic_applicability={},
        )

        allowed_2 = PlanningDocument(
            project_id=project_id,
            title="Rancangan Tempatan Subang Jaya 2035 Jilid 2",
            document_class="RT",
            authority="PLANMalaysia",
            jurisdiction="Majlis Bandaraya Subang Jaya, Selangor",
            geographic_applicability={},
        )

        blocked = PlanningDocument(
            project_id=project_id,
            title="RT Daerah Perak Tengah Jilid 2",
            document_class="RT",
            authority="PLANMalaysia",
            jurisdiction="Daerah Perak Tengah, Perak",
            geographic_applicability={},
        )

        session.add_all(
            [allowed_1, allowed_2, blocked]
        )
        session.commit()

        evidence = [
            ToolEvidence(
                project_id=project_id,
                tool_name="gis.site_applicability",
                deterministic=True,
                status="measured",
                payload={
                    "layer_provenance": {
                        "planning_document": (
                            "Rancangan Tempatan Subang Jaya 2035"
                        )
                    }
                },
                sources=[
                    EvidenceSourceRef(
                        kind="gis_feature",
                        id=uuid.uuid4(),
                    )
                ],
            )
        ]

        ids, limitations = _applicable_document_ids(
            session,
            project_id=project_id,
            spatial_evidence=evidence,
        )

        assert limitations == []
        assert set(ids) == {
            allowed_1.id,
            allowed_2.id,
        }
        assert blocked.id not in ids

    Base.metadata.drop_all(engine)
    engine.dispose()


def test_document_applicability_fails_closed_without_document_identity():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool

    from app.db.base import Base
    from app.services.planning_orchestrator import (
        _applicable_document_ids,
    )

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(engine)

    project_id = uuid.uuid4()

    with Session(engine) as session:
        evidence = [
            ToolEvidence(
                project_id=project_id,
                tool_name="gis.site_applicability",
                deterministic=True,
                status="measured",
                payload={
                    "layer_provenance": {
                        "applicability_role": "zoning"
                    }
                },
                sources=[
                    EvidenceSourceRef(
                        kind="gis_feature",
                        id=uuid.uuid4(),
                    )
                ],
            )
        ]

        ids, limitations = _applicable_document_ids(
            session,
            project_id=project_id,
            spatial_evidence=evidence,
        )

        assert ids == []
        assert limitations
        assert "planning_document" in limitations[0]

    Base.metadata.drop_all(engine)
    engine.dispose()


def test_document_applicability_prefers_immutable_id():
    from unittest.mock import MagicMock
    from app.services.planning_orchestrator import _applicable_document_ids

    project_id = uuid.uuid4()
    exact_document_id = uuid.uuid4()

    evidence = [
        ToolEvidence(
            project_id=project_id,
            tool_name="gis.site_applicability",
            deterministic=True,
            status="measured",
            payload={
                "layer_provenance": {
                    "planning_document_id": str(exact_document_id),
                    "planning_document": "Legacy Broad Title",
                }
            },
            sources=[
                EvidenceSourceRef(
                    kind="user_input",
                    id="site:x",
                )
            ],
        )
    ]

    session = MagicMock()
    session.scalars.return_value = [exact_document_id]

    ids, limitations = _applicable_document_ids(
        session,
        project_id=project_id,
        spatial_evidence=evidence,
    )

    assert ids == [exact_document_id]
    assert limitations == []


def test_document_applicability_invalid_or_missing_id_fails_closed():
    from unittest.mock import MagicMock
    from app.services.planning_orchestrator import _applicable_document_ids

    project_id = uuid.uuid4()
    missing_document_id = uuid.uuid4()

    evidence = [
        ToolEvidence(
            project_id=project_id,
            tool_name="gis.site_applicability",
            deterministic=True,
            status="measured",
            payload={
                "layer_provenance": {
                    "planning_document_id": str(missing_document_id),
                    "planning_document": "Legacy Broad Title",
                }
            },
            sources=[
                EvidenceSourceRef(
                    kind="user_input",
                    id="site:x",
                )
            ],
        )
    ]

    session = MagicMock()
    session.scalars.return_value = []

    ids, limitations = _applicable_document_ids(
        session,
        project_id=project_id,
        spatial_evidence=evidence,
    )

    assert ids == []
    assert limitations
    assert "planning_document_id" in limitations[0]


def test_document_applicability_legacy_title_fallback():
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from app.services.planning_orchestrator import _applicable_document_ids

    project_id = uuid.uuid4()
    document_id = uuid.uuid4()

    evidence = [
        ToolEvidence(
            project_id=project_id,
            tool_name="gis.site_applicability",
            deterministic=True,
            status="measured",
            payload={
                "layer_provenance": {
                    "planning_document": (
                        "Rancangan Tempatan Subang Jaya 2035"
                    )
                }
            },
            sources=[
                EvidenceSourceRef(
                    kind="user_input",
                    id="site:x",
                )
            ],
        )
    ]

    document = SimpleNamespace(
        id=document_id,
        title="Rancangan Tempatan Subang Jaya 2035 Jilid 2",
    )

    session = MagicMock()
    session.scalars.return_value = [document]

    ids, limitations = _applicable_document_ids(
        session,
        project_id=project_id,
        spatial_evidence=evidence,
    )

    assert ids == [document_id]
    assert limitations == []

