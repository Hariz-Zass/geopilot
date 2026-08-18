$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$log = Join-Path $root "artifacts\final_judge_demo_acceptance.txt"
$script = Join-Path $root "final_judge_demo_acceptance.py"
New-Item -ItemType Directory -Force (Join-Path $root "artifacts") | Out-Null

"============================================================" | Set-Content $log
"GEOPILOT FINAL JUDGE DEMO ACCEPTANCE" | Add-Content $log
"TXT CAPTURE ENABLED EVEN ON ERROR" | Add-Content $log
"============================================================" | Add-Content $log

docker compose cp $script backend:/app/final_judge_demo_acceptance.py 2>&1 |
  Tee-Object -FilePath $log -Append
$copyExit=$LASTEXITCODE
if($copyExit-ne 0){
  "COPY_EXIT_CODE = $copyExit" | Add-Content $log
  "LOG_CAPTURE = COMPLETE" | Add-Content $log
  Write-Host "COPY FAILED. RESULT SAVED TO: $log"
  exit $copyExit
}

docker compose exec -T backend python -m py_compile /app/final_judge_demo_acceptance.py 2>&1 |
  Tee-Object -FilePath $log -Append
$compileExit=$LASTEXITCODE
if($compileExit-ne 0){
  "COMPILE_EXIT_CODE = $compileExit" | Add-Content $log
  "LOG_CAPTURE = COMPLETE" | Add-Content $log
  Write-Host "COMPILE FAILED. RESULT SAVED TO: $log"
  exit $compileExit
}

docker compose exec -T -w /app backend python /app/final_judge_demo_acceptance.py 2>&1 |
  Tee-Object -FilePath $log -Append
$runExit=$LASTEXITCODE

"" | Add-Content $log
"============================================================" | Add-Content $log
"PROCESS_EXIT_CODE = $runExit" | Add-Content $log
"LOG_CAPTURE = COMPLETE" | Add-Content $log
"============================================================" | Add-Content $log

Write-Host ""
Write-Host "PROCESS_EXIT_CODE = $runExit"
Write-Host "RESULT SAVED TO:"
Write-Host $log
exit $runExit
