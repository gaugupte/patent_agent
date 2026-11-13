[CmdletBinding()]
# Require the target VM hostname and allow overriding its initial SSH username.
param(
    [Parameter(Mandatory = $true)]
    [string]$HostName,
    [string]$InitialUser = "ubuntu"
)

# Stop at the first PowerShell error instead of continuing with incomplete data.
$ErrorActionPreference = "Stop"
# Resolve the repository root relative to this script's location.
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
# Build the SSH destination from the VM login name and hostname.
$target = "${InitialUser}@${HostName}"
# Point to local application data that Git intentionally does not track.
$dataRoot = Join-Path $projectRoot "data"
# Use a temporary path for the Django fixture exported from the local database.
$fixturePath = Join-Path $env:TEMP "portal-data.json"

# Confirm every required data directory exists before starting any transfer.
foreach ($directory in @("chroma_db", "portal_media", "reports")) {
    # Find this required directory under the repository's data folder.
    $source = Join-Path $dataRoot $directory
    # Fail early with the missing path if local application data is incomplete.
    if (-not (Test-Path -LiteralPath $source -PathType Container)) {
        throw "Required local data directory is missing: $source"
    }
}

# Remember whether this process already had a database URL so it can be restored.
$hadDatabaseUrl = Test-Path Env:DATABASE_URL
# Preserve the current database URL before temporarily selecting local SQLite.
$previousDatabaseUrl = $env:DATABASE_URL
# Ensure cleanup and restoration happen even if fixture export fails.
try {
    # Force Django's local SQLite database for this export, even if .env has a DATABASE_URL.
    $env:DATABASE_URL = ""
    # Run Django's export command from the project root so its settings resolve.
    Push-Location $projectRoot
    # Restore the prior working directory even if dumpdata returns an error.
    try {
        # Export portal rows while omitting framework-owned and session records.
        & python .\web_portal\manage.py dumpdata `
            --natural-foreign `
            --natural-primary `
            --exclude contenttypes `
            --exclude auth.permission `
            --exclude sessions `
            --output $fixturePath
        # Treat a nonzero Django exit status as a failed preparation step.
        if ($LASTEXITCODE -ne 0) {
            throw "Django dumpdata failed with exit code $LASTEXITCODE."
        }
    }
    # Always leave the caller in the directory where this script was started.
    finally {
        Pop-Location
    }
}
# Restore DATABASE_URL to its exact prior state, including removing it if absent.
finally {
    # Restore the previous value when the variable was originally defined.
    if ($hadDatabaseUrl) {
        $env:DATABASE_URL = $previousDatabaseUrl
    }
    else {
        # Remove the temporary variable when it did not exist before the script.
        Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    }
}

# Use a temporary remote directory to receive data before first-time setup.
$remoteStage = "/tmp/patent-agent-data"
# Create the staging directory on the VM over SSH.
& ssh $target "mkdir -p $remoteStage"
# Stop if SSH could not create the destination directory.
if ($LASTEXITCODE -ne 0) {
    throw "Could not create the remote staging directory."
}

# Prepare the source list containing required data directories and Django fixture.
$sources = @(
    (Join-Path $dataRoot "chroma_db"),
    (Join-Path $dataRoot "portal_media"),
    (Join-Path $dataRoot "reports"),
    $fixturePath
)
# Copy data recursively to the VM's temporary staging area.
& scp -r @sources "${target}:${remoteStage}/"
# Preserve the exported fixture if transfer fails so the operation can be retried.
if ($LASTEXITCODE -ne 0) {
    throw "Data transfer failed. The fixture is still available at $fixturePath; rerun this script to retry."
}

# Delete the temporary fixture only after all requested data transferred successfully.
Remove-Item -LiteralPath $fixturePath -Force
# Report the transfer destination and the next setup command to the operator.
Write-Host "Data and the portal fixture were copied to $target`:$remoteStage/."
Write-Host "Next, run the VM setup script over SSH: sudo bash /srv/patent_agent/deployment/civo/setup-vm.sh"
