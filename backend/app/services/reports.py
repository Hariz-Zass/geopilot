from __future__ import annotations
import os,uuid
from pathlib import Path
from sqlalchemy.orm import Session
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from app.models.user import User
from app.models.report import PlanningReport,ProfessionalReview
from app.services.planning_runs import get_planning_run,save_run_state

def compose_report(session:Session,*,owner:User,project_id:uuid.UUID,site_id:uuid.UUID,run_id:uuid.UUID,title:str,root='/data/reports'):
 run=get_planning_run(session,owner=owner,project_id=project_id,site_id=site_id,run_id=run_id)
 body={'planning_run_id':str(run.id),'question':run.question,'synthesis':run.synthesis,'findings':run.findings,'evidence':run.evidence,'limitations':run.limitations,'review_state':run.review_state,'disclaimer':'GeoPilot AI is a decision-support system. This report is not statutory approval, legal certification, or planning permission.'}
 r=PlanningReport(project_id=project_id,site_id=site_id,planning_run_id=run.id,created_by_user_id=owner.id,title=title,status='draft',report_json=body); session.add(r); session.flush()
 path=Path(root)/str(project_id); path.mkdir(parents=True,exist_ok=True); file=path/f'{r.id}.pdf'; c=canvas.Canvas(str(file),pagesize=A4); width,height=A4; y=height-50; c.setFont('Helvetica-Bold',16); c.drawString(50,y,title); y-=30; c.setFont('Helvetica',9)
 for section,value in [('Question',run.question),('Synthesis',run.synthesis or 'No AI synthesis available.'),('Limitations','; '.join(run.limitations) or 'None recorded.'),('Disclaimer',body['disclaimer'])]:
  c.setFont('Helvetica-Bold',10); c.drawString(50,y,section); y-=14; c.setFont('Helvetica',9)
  text=c.beginText(50,y); text.setLeading(12)
  for line in str(value).splitlines() or ['']:
   for i in range(0,len(line),95): text.textLine(line[i:i+95]); y-=12
  c.drawText(text); y-=10
 c.save(); r.file_path=str(file); session.commit(); session.refresh(r); return r

def review_run(session:Session,*,owner:User,project_id:uuid.UUID,site_id:uuid.UUID,run_id:uuid.UUID,decision:str,notes:str):
 run=get_planning_run(session,owner=owner,project_id=project_id,site_id=site_id,run_id=run_id); pr=ProfessionalReview(project_id=project_id,planning_run_id=run.id,reviewer_user_id=owner.id,decision=decision,notes=notes); session.add(pr); run.review_state=decision; session.commit(); session.refresh(pr); return pr
