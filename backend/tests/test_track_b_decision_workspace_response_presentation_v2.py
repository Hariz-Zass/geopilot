from types import SimpleNamespace
import uuid

from app.api.v1.track_b import _planning_run_to_track_b_decision


def test_separates_synthesis_and_evidence_summary():
    run = SimpleNamespace(
        status="completed",
        synthesis="## Grounded answer\nUse this as the planning answer.",
        provider_metadata={"provider": "openai", "model": "test"},
        evidence=[
            {
                "tool_name": "documents.search",
                "payload": {
                    "document_title": "GPP Pembangunan Di Kawasan Bukit dan Tanah Tinggi",
                    "citation_label": "GPP Bukit dan Tanah Tinggi, p. 19",
                    "authority": "PLANMalaysia",
                    "page_number": 19,
                },
            }
        ],
        limitations=[],
    )
    result = _planning_run_to_track_b_decision(
        analysis_id=uuid.uuid4(),
        question="Apakah kategori ketinggian?",
        run=run,
    )
    assert result["planning_implication"] == run.synthesis
    assert result["evidence_summary"] != run.synthesis
    assert "Validated evidence used" in result["evidence_summary"]
    assert "GPP Pembangunan Di Kawasan Bukit dan Tanah Tinggi" in result["evidence_summary"]
    assert "p. 19" in result["evidence_summary"]


def test_deduplicates_same_evidence_line():
    item = {
        "tool_name": "documents.search",
        "payload": {
            "document_title": "Official RT",
            "citation_label": "Official RT, p. 12",
            "authority": "PLANMalaysia",
            "page_number": 12,
        },
    }
    run = SimpleNamespace(
        status="completed",
        synthesis="Answer",
        provider_metadata={},
        evidence=[item, item],
        limitations=[],
    )
    result = _planning_run_to_track_b_decision(
        analysis_id=uuid.uuid4(),
        question="Q",
        run=run,
    )
    assert result["evidence_summary"].count("**Official RT**") == 1


def test_no_evidence_does_not_duplicate_answer():
    run = SimpleNamespace(
        status="completed",
        synthesis="Unique answer",
        provider_metadata={},
        evidence=[],
        limitations=[],
    )
    result = _planning_run_to_track_b_decision(
        analysis_id=uuid.uuid4(),
        question="Q",
        run=run,
    )
    assert result["evidence_summary"] != result["planning_implication"]