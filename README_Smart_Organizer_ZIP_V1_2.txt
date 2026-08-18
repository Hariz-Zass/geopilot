GeoPilot Smart Organizer ZIP V1.2

Purpose:
Allow one organizer ZIP to be uploaded to Smart Organizer Intake and inspect
supported files inside it individually before any import.

Run from GeoPilot project root:
  .\install_geopilot_smart_organizer_zip_v1_2.bat

Safety:
- no migration
- no Smart Intake DB writes
- ZIP members are inspected in memory; they are not extracted to disk
- unsafe ../ archive paths are blocked
- nested ZIP depth is limited
- manual ingestion remains unchanged

After PASS:
Use the existing Smart Organizer Intake UI and select the organizer ZIP itself.
Send ChatGPT a screenshot of the resulting report.
