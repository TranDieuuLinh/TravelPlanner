$ErrorActionPreference = "Stop"

$workspace = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$runDirectory = Join-Path $workspace "backend\var\kg-edge-linking-v1"
$outputFile = Join-Path $runDirectory "batch-test-200.jsonl"
$logFile = Join-Path $runDirectory "background-runner.log"
$stateFile = Join-Path $runDirectory "background-runner-state.json"
$dumpDirectory = Join-Path $workspace "trung-plans"

New-Item -ItemType Directory -Force -Path $runDirectory | Out-Null
New-Item -ItemType Directory -Force -Path $dumpDirectory | Out-Null
Set-Location -LiteralPath $workspace

function Write-RunnerLog([string]$Message) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -LiteralPath $logFile -Value $line -Encoding utf8
}

function Get-ProcessedCount {
    if (-not (Test-Path -LiteralPath $outputFile)) {
        return 0
    }
    $ids = [System.Collections.Generic.HashSet[string]]::new()
    foreach ($line in [System.IO.File]::ReadLines($outputFile)) {
        try {
            $row = $line | ConvertFrom-Json
            if ($null -ne $row.placeId) {
                [void]$ids.Add([string]$row.placeId)
            }
        }
        catch {
            continue
        }
    }
    return $ids.Count
}

function Save-State(
    [string]$Status,
    [int]$BatchNumber,
    [int]$ProcessedPlaces,
    [string]$Message,
    [string]$DumpPath = ""
) {
    $state = [ordered]@{
        status = $Status
        batchNumber = $BatchNumber
        processedPlaces = $ProcessedPlaces
        message = $Message
        dumpPath = $DumpPath
        updatedAt = (Get-Date).ToString("o")
        processId = $PID
    }
    $state | ConvertTo-Json | Set-Content -LiteralPath $stateFile -Encoding utf8
}

$batchNumber = 0
$consecutiveNoProgress = 0
Write-RunnerLog "Runner started with four workers, five keys per worker, two request starts/second globally."
Save-State -Status "running" -BatchNumber 0 -ProcessedPlaces (Get-ProcessedCount) -Message "Starting"

while ($true) {
    $batchNumber += 1
    $before = Get-ProcessedCount
    Write-RunnerLog "Batch $batchNumber started; processed before=$before."

    $runOutput = & docker compose exec -T backend python /app/var/link_kg_edges_with_gemini.py run `
        --limit 100 `
        --resume `
        --workers 4 `
        --image-batch-size 4 `
        --text-batch-size 12 `
        --output /app/var/kg-edge-linking-v1/batch-test-200.jsonl 2>&1 | Out-String
    $runExitCode = $LASTEXITCODE
    Add-Content -LiteralPath $logFile -Value $runOutput -Encoding utf8

    if ($runExitCode -ne 0) {
        Write-RunnerLog "Batch $batchNumber command failed with exit code $runExitCode; retrying after 60 seconds."
        Save-State -Status "retrying" -BatchNumber $batchNumber -ProcessedPlaces (Get-ProcessedCount) -Message "Run command failed"
        Start-Sleep -Seconds 60
        continue
    }

    if ($runOutput -match '"selectedPlaces"\s*:\s*0') {
        Write-RunnerLog "No unprocessed Place remains."
        break
    }

    $applyOutput = & docker compose exec -T backend python /app/var/link_kg_edges_with_gemini.py apply `
        --output /app/var/kg-edge-linking-v1/batch-test-200.jsonl `
        --minimum-confidence 0.76 `
        --commit 2>&1 | Out-String
    $applyExitCode = $LASTEXITCODE
    Add-Content -LiteralPath $logFile -Value $applyOutput -Encoding utf8
    if ($applyExitCode -ne 0) {
        Write-RunnerLog "Apply failed with exit code $applyExitCode; stopping before database export."
        Save-State -Status "failed" -BatchNumber $batchNumber -ProcessedPlaces (Get-ProcessedCount) -Message "Apply failed"
        exit $applyExitCode
    }

    $after = Get-ProcessedCount
    $advanced = $after - $before
    Write-RunnerLog "Batch $batchNumber completed; processed after=$after; advanced=$advanced."
    Save-State -Status "running" -BatchNumber $batchNumber -ProcessedPlaces $after -Message "Last batch advanced $advanced places"

    if ($advanced -eq 0) {
        $consecutiveNoProgress += 1
        $cooldownSeconds = [Math]::Min(900, 60 * $consecutiveNoProgress)
        Write-RunnerLog "No progress, cooling down for $cooldownSeconds seconds before retry."
        Start-Sleep -Seconds $cooldownSeconds
    }
    else {
        $consecutiveNoProgress = 0
    }
}

$finalApplyOutput = & docker compose exec -T backend python /app/var/link_kg_edges_with_gemini.py apply `
    --output /app/var/kg-edge-linking-v1/batch-test-200.jsonl `
    --minimum-confidence 0.76 `
    --commit 2>&1 | Out-String
$finalApplyExitCode = $LASTEXITCODE
Add-Content -LiteralPath $logFile -Value $finalApplyOutput -Encoding utf8
if ($finalApplyExitCode -ne 0) {
    Write-RunnerLog "Final apply failed; database was not exported."
    Save-State -Status "failed" -BatchNumber $batchNumber -ProcessedPlaces (Get-ProcessedCount) -Message "Final apply failed"
    exit $finalApplyExitCode
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$dumpName = "travelplanner-full-after-kg-linking-$stamp.sql"
$containerDumpPath = "/tmp/$dumpName"
$hostDumpPath = Join-Path $dumpDirectory $dumpName

Write-RunnerLog "Creating PostgreSQL dump $dumpName."
& docker compose exec -T postgres pg_dump `
    -U travelplanner `
    -d travelplanner `
    --clean `
    --if-exists `
    --no-owner `
    --no-privileges `
    --format=p `
    --encoding=UTF8 `
    --file=$containerDumpPath
if ($LASTEXITCODE -ne 0) {
    Write-RunnerLog "pg_dump failed."
    Save-State -Status "failed" -BatchNumber $batchNumber -ProcessedPlaces (Get-ProcessedCount) -Message "pg_dump failed"
    exit 1
}

& docker compose cp "postgres:$containerDumpPath" $hostDumpPath
if ($LASTEXITCODE -ne 0) {
    Write-RunnerLog "Copying the dump to the host failed."
    Save-State -Status "failed" -BatchNumber $batchNumber -ProcessedPlaces (Get-ProcessedCount) -Message "Dump copy failed"
    exit 1
}

$dumpFile = Get-Item -LiteralPath $hostDumpPath
if ($dumpFile.Length -le 0) {
    Write-RunnerLog "Dump verification failed because the file is empty."
    Save-State -Status "failed" -BatchNumber $batchNumber -ProcessedPlaces (Get-ProcessedCount) -Message "Dump is empty" -DumpPath $hostDumpPath
    exit 1
}

$processed = Get-ProcessedCount
Write-RunnerLog "Completed. Processed=$processed; dump=$hostDumpPath; bytes=$($dumpFile.Length)."
Save-State -Status "complete" -BatchNumber $batchNumber -ProcessedPlaces $processed -Message "Pipeline and PostgreSQL export completed" -DumpPath $hostDumpPath
