[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$HostName,
    [string]$InitialUser = "ubuntu"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$target = "${InitialUser}@${HostName}"
$dataRoot = Join-Path $projectRoot "data"
$fixturePath = Join-Path $env:TEMP "portal-data.json"

foreach ($directory in @("chroma_db", "portal_media", "reports")) {
    $source = Join-Path $dataRoot $directory
    if (-not (Test-Path -LiteralPath $source -PathType Container)) {
        throw "Required local data directory is missing: $source"
    }
}

$hadDatabaseUrl = Test-Path Env:DATABASE_URL
$previousDatabaseUrl = $env:DATABASE_URL
try {
    # Force Django's local SQLite database for this export, even if .env has a DATABASE_URL.
    $env:DATABASE_URL = ""
    Push-Location $projectRoot
    try {
        & python .\web_portal\manage.py dumpdata `
            --natural-foreign `
            --natural-primary `
            --exclude contenttypes `
            --exclude auth.permission `
            --exclude sessions `
            --output $fixturePath
        if ($LASTEXITCODE -ne 0) {
            throw "Django dumpdata failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        Pop-Location
    }
}
finally {
    if ($hadDatabaseUrl) {
        $env:DATABASE_URL = $previousDatabaseUrl
    }
    else {
        Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    }
}

$remoteStage = "/tmp/patent-agent-data"
& ssh $target "mkdir -p $remoteStage"
if ($LASTEXITCODE -ne 0) {
    throw "Could not create the remote staging directory."
}

$sources = @(
    (Join-Path $dataRoot "chroma_db"),
    (Join-Path $dataRoot "portal_media"),
    (Join-Path $dataRoot "reports"),
    $fixturePath
)
$auditDatabase = Join-Path $projectRoot "patent_agent.db"
if (Test-Path -LiteralPath $auditDatabase -PathType Leaf) {
    $sources += $auditDatabase
}

& scp -r @sources "${target}:${remoteStage}/"
if ($LASTEXITCODE -ne 0) {
    throw "Data transfer failed. The fixture is still available at $fixturePath; rerun this script to retry."
}

Remove-Item -LiteralPath $fixturePath -Force
Write-Host "Data and the portal fixture were copied to $target`:$remoteStage/."
Write-Host "Next, run the VM setup script over SSH: sudo bash /srv/patent_agent/deployment/civo/setup-vm.sh"
