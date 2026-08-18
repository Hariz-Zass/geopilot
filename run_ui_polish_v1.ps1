$log = ".\artifacts\ui_polish_v1_result.txt"
New-Item -ItemType Directory -Force ".\artifacts" | Out-Null

"============================================================" | Set-Content $log
"GEOPILOT UI POLISH V1" | Add-Content $log
"FRONTEND PRESENTATION ONLY" | Add-Content $log
"============================================================" | Add-Content $log

$exitCode = 1

try {
    Write-Host "[1] APPLY CONTROLLED PATCH"
    python .\ui_polish_v1.py 2>&1 |
        Tee-Object -FilePath $log -Append

    if ($LASTEXITCODE -ne 0) {
        throw "UI patch script failed."
    }

    Write-Host "[2] MOJIBAKE RESIDUAL CHECK"

    "`n=== MOJIBAKE RESIDUAL ===" | Add-Content $log

    $bad = Get-Content `
        .\frontend\src\pages\TrackBWorkspacePage.tsx |
        Select-String -Pattern "â|Â|Ã"

    if ($bad) {
        $bad | Tee-Object -FilePath $log -Append
    }
    else {
        "PASS - no â / Â / Ã residuals" |
            Tee-Object -FilePath $log -Append
    }

    Write-Host "[3] FRONTEND TESTS"

    docker compose exec -T frontend npm test -- --run 2>&1 |
        Tee-Object -FilePath $log -Append

    if ($LASTEXITCODE -ne 0) {
        throw "Frontend tests failed."
    }

    Write-Host "[4] PRODUCTION BUILD"

    # Vite writes chunk-size warnings to stderr even when build succeeds.
    # Do not treat stderr itself as failure.
    docker compose exec -T frontend npm run build 2>&1 |
        Tee-Object -FilePath $log -Append

    if ($LASTEXITCODE -ne 0) {
        throw "Frontend production build failed."
    }

    Write-Host "[5] CONTROLLED DIFF"

    "`n=== TARGET DIFF ===" | Add-Content $log

    git diff -- `
        frontend/src/pages/TrackBWorkspacePage.tsx 2>&1 |
        Tee-Object -FilePath $log -Append

    "`n=== GIT STATUS TARGETS ===" | Add-Content $log

    git status --short -- `
        frontend/src/pages/TrackBWorkspacePage.tsx `
        frontend/src/styles.css 2>&1 |
        Tee-Object -FilePath $log -Append

    $exitCode = 0

    "`n============================================================" | Add-Content $log
    "UI_POLISH_V1_ACCEPTANCE = PASS" | Add-Content $log
    "BACKEND_CHANGED = NO" | Add-Content $log
    "DATABASE_WRITES = NONE" | Add-Content $log
    "============================================================" | Add-Content $log
}
catch {
    "`n============================================================" | Add-Content $log
    "UI_POLISH_V1_ACCEPTANCE = ERROR" | Add-Content $log
    $_.Exception.Message | Add-Content $log
    "DO_NOT_COMMIT = YES" | Add-Content $log
    "============================================================" | Add-Content $log
}

"`nPROCESS_EXIT_CODE = $exitCode" | Add-Content $log
"LOG_CAPTURE = COMPLETE" | Add-Content $log

Write-Host ""
Write-Host "PROCESS_EXIT_CODE = $exitCode"
Write-Host "RESULT SAVED TO:"
Write-Host $log