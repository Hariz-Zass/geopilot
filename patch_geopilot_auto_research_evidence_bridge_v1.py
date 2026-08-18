from pathlib import Path

path = Path("/app/app/services/planning_orchestrator.py")
text = path.read_text(encoding="utf-8")

if "AUTO_RESEARCH_QUESTION_ROUTER_V1" not in text:
    raise SystemExit("BLOCKED: Auto Research Question Router V1 marker not found.")

old = '''        auto_research = auto_research_planning_documents(
            session,
            owner=owner,
            project_id=project_id,
            question=run.question,
        )
        tool_limitations.extend(auto_research.limitations)
'''
new = '''        auto_research = auto_research_planning_documents(
            session,
            owner=owner,
            project_id=project_id,
            question=run.question,
        )
        tool_limitations.extend(auto_research.limitations)
        # AUTO_RESEARCH_EVIDENCE_BRIDGE_V1
        auto_research_document_ids = list(auto_research.document_ids)
'''

if "AUTO_RESEARCH_EVIDENCE_BRIDGE_V1" not in text:
    if old not in text:
        raise SystemExit("BLOCKED: existing auto-research call block not found exactly.")
    text = text.replace(old, new, 1)

old_gate = '''            if resolved_document_ids:
                applicable_document_ids = (
                    resolved_document_ids
                )
            else:
                applicable_document_ids = []
'''
new_gate = '''            if resolved_document_ids:
                applicable_document_ids = list(
                    dict.fromkeys(
                        [
                            *resolved_document_ids,
                            *auto_research_document_ids,
                        ]
                    )
                )
            elif auto_research_document_ids:
                # Research candidates may be searched, but this does not prove
                # that the document is legally/site-spatially applicable.
                applicable_document_ids = list(
                    auto_research_document_ids
                )
            else:
                applicable_document_ids = []
'''

if "elif auto_research_document_ids:" not in text:
    if old_gate not in text:
        raise SystemExit("BLOCKED: applicability document gate not found exactly.")
    text = text.replace(old_gate, new_gate, 1)

path.write_text(text, encoding="utf-8")
print("PATCHED:", path)
