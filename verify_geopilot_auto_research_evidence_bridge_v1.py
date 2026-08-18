import inspect
from app.services import planning_orchestrator as o

src = inspect.getsource(o.execute_planning_run)
checks = {
    "auto_research_router": "AUTO_RESEARCH_QUESTION_ROUTER_V1" in src,
    "evidence_bridge": "AUTO_RESEARCH_EVIDENCE_BRIDGE_V1" in src,
    "captures_auto_document_ids": "auto_research.document_ids" in src,
    "auto_docs_cross_empty_applicability_gate": "elif auto_research_document_ids:" in src,
    "document_search_preserved": "_document_search_evidence(" in src,
}
for key, ok in checks.items():
    print(f"{key}={'PASS' if ok else 'FAIL'}")
failed = [k for k, v in checks.items() if not v]
if failed:
    raise SystemExit("VERIFY_FAILED: " + ", ".join(failed))
print("VERIFY_ALL=PASS")
