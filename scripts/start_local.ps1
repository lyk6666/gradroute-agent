[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$BackendPort = 8000,

    [ValidateRange(1, 65535)]
    [int]$FrontendPort = 3000
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$frontendRoot = Join-Path $repoRoot "frontend"
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"
$logRoot = Join-Path $repoRoot "var\logs"
$runId = Get-Date -Format "yyyyMMdd-HHmmss"
$backendStdout = Join-Path $logRoot "backend-$runId.stdout.log"
$backendStderr = Join-Path $logRoot "backend-$runId.stderr.log"
$frontendStdout = Join-Path $logRoot "frontend-$runId.stdout.log"
$frontendStderr = Join-Path $logRoot "frontend-$runId.stderr.log"

function Test-ListeningPort {
    param([int]$Port)

    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $connect = $client.ConnectAsync("127.0.0.1", $Port)
        return $connect.Wait(250) -and $client.Connected
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

function Wait-ForHttp {
    param(
        [string]$Url,
        [string]$Name,
        [int]$Attempts = 40
    )

    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
                return
            }
        }
        catch {
            if ($attempt -eq $Attempts) {
                throw "$Name did not become ready at $Url."
            }
        }
        Start-Sleep -Milliseconds 500
    }
}

function Get-ListeningProcessIds {
    param([int]$Port)

    $pattern = "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$"
    return @(
        netstat.exe -ano |
            Select-String -Pattern $pattern |
            ForEach-Object {
                if ($_.Line -match $pattern) {
                    [int]$Matches[1]
                }
            } |
            Sort-Object -Unique
    )
}

function Stop-ProcessTree {
    param([System.Diagnostics.Process]$Process)

    if ($null -eq $Process) {
        return
    }

    try {
        if (-not $Process.HasExited) {
            $Process.Kill($true)
            $Process.WaitForExit(5000) | Out-Null
        }
    }
    catch [System.InvalidOperationException] {
        # The process exited between the status check and the kill request.
    }
}

function Stop-ListeningProcesses {
    param([int[]]$ProcessIds)

    foreach ($processId in $ProcessIds) {
        try {
            $process = [System.Diagnostics.Process]::GetProcessById($processId)
            $process.Kill($true)
            $process.WaitForExit(5000) | Out-Null
            $process.Dispose()
        }
        catch [System.ArgumentException] {
            # The listening process has already exited.
        }
    }
}

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Python environment not found at $pythonPath. Run the initial setup in README.md first."
}

if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot "node_modules"))) {
    throw "Frontend dependencies are missing. Run 'npm ci' in $frontendRoot first."
}

$npmCommand = Get-Command npm.cmd -ErrorAction Stop

if (Test-ListeningPort -Port $BackendPort) {
    throw "Backend port $BackendPort is already in use."
}

if (Test-ListeningPort -Port $FrontendPort) {
    throw "Frontend port $FrontendPort is already in use."
}

New-Item -ItemType Directory -Force -Path $logRoot | Out-Null

$previousApiHost = [Environment]::GetEnvironmentVariable("API_HOST", "Process")
$previousApiPort = [Environment]::GetEnvironmentVariable("API_PORT", "Process")
$previousFrontendOrigin = [Environment]::GetEnvironmentVariable("FRONTEND_ORIGIN", "Process")
$previousApiBase = [Environment]::GetEnvironmentVariable("NEXT_PUBLIC_API_BASE_URL", "Process")

$backendProcess = $null
$frontendProcess = $null
$backendListenerIds = @()
$frontendListenerIds = @()

try {
    $env:API_HOST = "127.0.0.1"
    $env:API_PORT = $BackendPort.ToString()
    $env:FRONTEND_ORIGIN = "http://localhost:$FrontendPort"
    $env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:$BackendPort"

    $backendProcess = Start-Process `
        -FilePath $pythonPath `
        -ArgumentList "-m", "graduation_exception_agent.api" `
        -WorkingDirectory $repoRoot `
        -RedirectStandardOutput $backendStdout `
        -RedirectStandardError $backendStderr `
        -WindowStyle Hidden `
        -PassThru

    Wait-ForHttp `
        -Url "http://127.0.0.1:$BackendPort/api/v1/ready" `
        -Name "Backend"
    $backendListenerIds = @(Get-ListeningProcessIds -Port $BackendPort)
    if ($backendListenerIds.Count -eq 0) {
        throw "Backend became ready but its listening process could not be identified."
    }

    $frontendProcess = Start-Process `
        -FilePath $npmCommand.Source `
        -ArgumentList "run", "dev", "--", "--port", $FrontendPort.ToString() `
        -WorkingDirectory $frontendRoot `
        -RedirectStandardOutput $frontendStdout `
        -RedirectStandardError $frontendStderr `
        -WindowStyle Hidden `
        -PassThru

    Wait-ForHttp -Url "http://localhost:$FrontendPort" -Name "Frontend"
    $frontendListenerIds = @(Get-ListeningProcessIds -Port $FrontendPort)
    if ($frontendListenerIds.Count -eq 0) {
        throw "Frontend became ready but its listening process could not be identified."
    }

    Write-Host "Graduation Exception Agent is running." -ForegroundColor Green
    Write-Host "Frontend: http://localhost:$FrontendPort"
    Write-Host "Backend:  http://127.0.0.1:$BackendPort"
    Write-Host "API docs: http://127.0.0.1:$BackendPort/docs"
    Write-Host "Logs:     $logRoot"
    Read-Host "Press Enter to stop both services" | Out-Null

    if ($backendProcess.HasExited) {
        throw "Backend exited unexpectedly. See $backendStderr"
    }
    if ($frontendProcess.HasExited) {
        throw "Frontend exited unexpectedly. See $frontendStderr"
    }
}
finally {
    Stop-ProcessTree -Process $frontendProcess
    Stop-ProcessTree -Process $backendProcess
    Stop-ListeningProcesses -ProcessIds $frontendListenerIds
    Stop-ListeningProcesses -ProcessIds $backendListenerIds

    [Environment]::SetEnvironmentVariable("API_HOST", $previousApiHost, "Process")
    [Environment]::SetEnvironmentVariable("API_PORT", $previousApiPort, "Process")
    [Environment]::SetEnvironmentVariable("FRONTEND_ORIGIN", $previousFrontendOrigin, "Process")
    [Environment]::SetEnvironmentVariable("NEXT_PUBLIC_API_BASE_URL", $previousApiBase, "Process")

    Write-Host "Frontend and backend stopped."
}
