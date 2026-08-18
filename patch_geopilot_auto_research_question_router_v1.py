from pathlib import Path

path = Path("/app/app/services/planning_orchestrator.py")
text = path.read_text(encoding="utf-8")

import_line = (
    "from app.services.planning_document_auto_research "
    "import auto_research_planning_documents"
)

if import_line not in text:
    anchor = "from app.services.planning_runs import ("
    if anchor not in text:
        raise SystemExit("IMPORT_ANCHOR_NOT_FOUND")
    text = text.replace(anchor, import_line + "\n" + anchor, 1)

marker = '    if "documents.search" in tools:\n'
if marker not in text:
    raise SystemExit("DOCUMENT_SEARCH_BLOCK_NOT_FOUND")

if "AUTO_RESEARCH_QUESTION_ROUTER_V1" not in text:
    injected = (
        '    if "documents.search" in tools:\n'
        '        # AUTO_RESEARCH_QUESTION_ROUTER_V1\n'
        '        auto_research = auto_research_planning_documents(\n'
        '            session,\n'
        '            owner=owner,\n'
        '            project_id=project_id,\n'
        '            question=run.question,\n'
        '        )\n'
        '        tool_limitations.extend(auto_research.limitations)\n'
    )
    text = text.replace(marker, injected, 1)

path.write_text(text, encoding="utf-8")
print("PATCHED:", path)
