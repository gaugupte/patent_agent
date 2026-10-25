$ErrorActionPreference = 'Stop'

$projectRoot = $PSScriptRoot
$frontendDirectory = Join-Path $projectRoot 'web_portal\frontend'

if (-not (Test-Path (Join-Path $frontendDirectory 'package.json'))) {
    throw "React frontend was not found at '$frontendDirectory'."
}

function Start-ProjectTerminal {
    param(
        [Parameter(Mandatory = $true)][string]$Title,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$Command
    )

    $terminalCommand = "`$Host.UI.RawUI.WindowTitle = '$Title'; $Command"
    Start-Process -FilePath 'powershell.exe' `
        -WorkingDirectory $WorkingDirectory `
        -ArgumentList @('-NoExit', '-Command', $terminalCommand)
}

Start-ProjectTerminal -Title 'Ollama - Mistral' -WorkingDirectory $projectRoot -Command 'ollama run mistral'
Start-ProjectTerminal -Title 'FastAPI - Patent Service' -WorkingDirectory $projectRoot -Command 'python -m uvicorn app:app --reload --host 127.0.0.1 --port 8000'
Start-ProjectTerminal -Title 'Django - Portal' -WorkingDirectory $projectRoot -Command 'python web_portal/manage.py runserver 127.0.0.1:8001'
Start-ProjectTerminal -Title 'React - Vite' -WorkingDirectory $frontendDirectory -Command 'npm run dev'

Write-Host 'Started four PowerShell windows: Ollama, FastAPI, Django, and React.'
