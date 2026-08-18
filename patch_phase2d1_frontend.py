from pathlib import Path

root=Path(__file__).resolve().parent
trackb=root/"frontend/src/lib/api/trackB.ts"
page=root/"frontend/src/pages/TrackBWorkspacePage.tsx"
styles=root/"frontend/src/styles.css"

for p in (trackb,page,styles):
    if not p.exists():
        raise SystemExit(f"missing required file: {p}")

component_payload=(root/"SmartOrganizerControlledImport.tsx.txt").read_text(encoding="utf-8")
types_payload=(root/"phase2d1_api_types.txt").read_text(encoding="utf-8")
methods_payload=(root/"phase2d1_api_methods.txt").read_text(encoding="utf-8")
css_payload=(root/"phase2d1_styles.txt").read_text(encoding="utf-8")

component_target=root/"frontend/src/components/SmartOrganizerControlledImport.tsx"
component_target.parent.mkdir(parents=True,exist_ok=True)

api=trackb.read_text(encoding="utf-8")
pg=page.read_text(encoding="utf-8")
css=styles.read_text(encoding="utf-8")

if "SMART_ORGANIZER_PHASE2D1_FRONTEND" in api or "SMART_ORGANIZER_PHASE2D1_FRONTEND" in pg:
    raise SystemExit("Phase 2D.1 frontend marker already present; stop for audit.")

type_anchor="export type TrackBDataset = {"
if type_anchor not in api:
    raise SystemExit("trackB.ts type anchor missing")
api=api.replace(type_anchor,types_payload.strip()+"\n\n"+type_anchor,1)

method_anchor='  readiness: (projectId: string, token: string) =>'
if method_anchor not in api:
    raise SystemExit("trackB.ts readiness anchor missing")
api=api.replace(method_anchor,methods_payload.rstrip()+"\n\n"+method_anchor,1)

import_anchor='import { getSessionAccessToken } from "../lib/auth/session";'
if import_anchor not in pg:
    raise SystemExit("TrackBWorkspacePage import anchor missing")
pg=pg.replace(
    import_anchor,
    import_anchor+'\nimport { SmartOrganizerControlledImport } from "../components/SmartOrganizerControlledImport";',
    1,
)

ui_anchor='          <section className="smart-intake">'
if ui_anchor not in pg:
    raise SystemExit("TrackBWorkspacePage Smart Organizer UI anchor missing")
ui = '''          {/* SMART_ORGANIZER_PHASE2D1_FRONTEND */}
          <SmartOrganizerControlledImport
            projectId={projectId}
            token={token}
            onCommitted={load}
          />

'''
pg=pg.replace(ui_anchor,ui+ui_anchor,1)

css=css.rstrip()+"\n\n"+css_payload.strip()+"\n"

trackb.write_text(api,encoding="utf-8")
page.write_text(pg,encoding="utf-8")
styles.write_text(css,encoding="utf-8")
component_target.write_text(component_payload,encoding="utf-8")

print("phase2d1_frontend_patch=PASS")
