param(
  [Parameter(Mandatory=$true)][string]$Path
)
$ErrorActionPreference="Stop"
$text=Get-Content $Path -Raw

$text=$text.Replace("// temporal question -> Track B closed-evidence decision flow",
                    "// temporal question -> Track B grounded decision flow")

$badge='<div className="evidence-lock"><span className="pulse-dot" /> CLOSED EVIDENCE MODE<br /><small>Organizer data only · external acquisition disabled</small></div>'
$text=$text.Replace($badge,'')

$text=$text.Replace("<code>ORGANIZER_ONLY</code>","<code>GROUNDED_EVIDENCE</code>")
$text=$text.Replace(
  "Register matching organizer-only Urban and Rural T1/T2 pairs with the same Site and data stage.",
  "Register matching Urban and Rural T1/T2 pairs with the same Site and data stage."
)
$text=$text.Replace(
  "GeoPilot automatically selects organizer-only before/after pairs for both challenge contexts, runs deterministic temporal analysis, grounded AI interpretation, planner decision briefs, and strategic comparison.",
  "GeoPilot automatically selects available before/after pairs for both challenge contexts, runs deterministic temporal analysis, grounded AI interpretation, planner decision briefs, and strategic comparison."
)

Set-Content -Path $Path -Value $text -Encoding UTF8
Write-Host "PATCHED: $Path"
