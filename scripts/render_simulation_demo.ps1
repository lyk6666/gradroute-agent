[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$BackendPort = 8000,

    [ValidateRange(1, 65535)]
    [int]$FrontendPort = 3000,

    [switch]$Fixture,
    [switch]$SkipCapture,
    [switch]$SkipNarration,
    [switch]$HeadedCapture
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$frontendRoot = Join-Path $repoRoot "frontend"
$videoRoot = Join-Path $repoRoot "video"
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"
$videoModules = Join-Path $videoRoot "node_modules"
$logRoot = Join-Path $repoRoot "var\video-logs"
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
    catch { return $false }
    finally { $client.Dispose() }
}

function Wait-ForHttp {
    param([string]$Url, [string]$Name, [int]$Attempts = 180)
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) { return }
        }
        catch {
            if ($attempt -eq $Attempts) { throw "$Name did not become ready at $Url." }
        }
        Start-Sleep -Milliseconds 500
    }
}

function Stop-ProcessTree {
    param([System.Diagnostics.Process]$Process)
    if ($null -eq $Process) { return }
    try {
        if (-not $Process.HasExited) {
            $Process.Kill($true)
            $Process.WaitForExit(10000) | Out-Null
        }
    }
    catch [System.InvalidOperationException] {}
    finally { $Process.Dispose() }
}

function Read-DotEnvValue {
    param([string]$Path, [string]$Name)
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    $line = Get-Content -LiteralPath $Path | Where-Object { $_ -match "^\s*$([Regex]::Escape($Name))\s*=" } | Select-Object -Last 1
    if (-not $line) { return $null }
    return (($line -split "=", 2)[1]).Trim().Trim('"').Trim("'")
}

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Python environment not found. Complete the repository setup in README.md first."
}
if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot "node_modules"))) {
    throw "Frontend dependencies are missing. Run npm ci in the frontend folder first."
}
$backendAlreadyRunning = Test-ListeningPort -Port $BackendPort
$frontendAlreadyRunning = Test-ListeningPort -Port $FrontendPort
$reuseServices = $backendAlreadyRunning -and $frontendAlreadyRunning
if ($backendAlreadyRunning -xor $frontendAlreadyRunning) {
    throw "Only one requested service port is already in use. Stop that service or choose two unused ports."
}
if ($reuseServices) {
    Wait-ForHttp -Url "http://127.0.0.1:$BackendPort/api/v1/ready" -Name "Existing backend" -Attempts 2
    Wait-ForHttp -Url "http://localhost:$FrontendPort" -Name "Existing frontend" -Attempts 2
    if ($Fixture) { throw "Fixture mode cannot replace an already-running backend. Stop the services first or omit -Fixture." }
    Write-Host "Reusing healthy services on ports $BackendPort and $FrontendPort." -ForegroundColor Cyan
}

$npmCommand = Get-Command npm.cmd -ErrorAction Stop
if (-not (Test-Path -LiteralPath $videoModules)) {
    Write-Host "Installing video dependencies..." -ForegroundColor Cyan
    & $npmCommand.Source ci --prefix $videoRoot
    if ($LASTEXITCODE -ne 0) { throw "Video dependency installation failed." }
}

if (-not $SkipNarration) {
    & $pythonPath -c "import edge_tts" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Installing the narration dependency..." -ForegroundColor Cyan
        & $pythonPath -m pip install "edge-tts==7.2.8"
        if ($LASTEXITCODE -ne 0) { throw "Narration dependency installation failed." }
    }
}

$envFile = Join-Path $repoRoot ".env"
$configuredMode = if ($Fixture) { "fixture" } else { Read-DotEnvValue -Path $envFile -Name "EXECUTION_MODE" }
$configuredProfile = Read-DotEnvValue -Path $envFile -Name "AWS_PROFILE"
if ($configuredMode -eq "bedrock" -and $configuredProfile) {
    $awsCommand = Get-Command aws.exe -ErrorAction SilentlyContinue
    if (-not $awsCommand) { throw "AWS CLI is required for the configured Bedrock capture." }
    & $awsCommand.Source sts get-caller-identity --profile $configuredProfile --output json | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "The AWS SSO session is unavailable. Run: aws sso login --profile $configuredProfile"
    }
}

New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
$backendProcess = $null
$frontendProcess = $null
$previousEnvironment = @{
    API_HOST = [Environment]::GetEnvironmentVariable("API_HOST", "Process")
    API_PORT = [Environment]::GetEnvironmentVariable("API_PORT", "Process")
    FRONTEND_ORIGIN = [Environment]::GetEnvironmentVariable("FRONTEND_ORIGIN", "Process")
    NEXT_PUBLIC_API_BASE_URL = [Environment]::GetEnvironmentVariable("NEXT_PUBLIC_API_BASE_URL", "Process")
    EXECUTION_MODE = [Environment]::GetEnvironmentVariable("EXECUTION_MODE", "Process")
}

try {
    $env:API_HOST = "127.0.0.1"
    $env:API_PORT = $BackendPort.ToString()
    $env:FRONTEND_ORIGIN = "http://localhost:$FrontendPort"
    $env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:$BackendPort"
    if ($Fixture) { $env:EXECUTION_MODE = "fixture" }

    if (-not $reuseServices) {
        $backendProcess = Start-Process `
            -FilePath $pythonPath `
            -ArgumentList "-m", "graduation_exception_agent.api" `
            -WorkingDirectory $repoRoot `
            -RedirectStandardOutput $backendStdout `
            -RedirectStandardError $backendStderr `
            -WindowStyle Hidden `
            -PassThru
        Wait-ForHttp -Url "http://127.0.0.1:$BackendPort/api/v1/ready" -Name "Backend"

        $frontendProcess = Start-Process `
            -FilePath $npmCommand.Source `
            -ArgumentList "run", "dev", "--", "--port", $FrontendPort.ToString() `
            -WorkingDirectory $frontendRoot `
            -RedirectStandardOutput $frontendStdout `
            -RedirectStandardError $frontendStderr `
            -WindowStyle Hidden `
            -PassThru
        Wait-ForHttp -Url "http://localhost:$FrontendPort" -Name "Frontend"
    }

    if (-not $SkipNarration) {
        & $pythonPath (Join-Path $videoRoot "scripts\generate_narration.py") --force
        if ($LASTEXITCODE -ne 0) { throw "Narration generation failed." }
    }

    if (-not $SkipCapture) {
        & $npmCommand.Source --prefix $videoRoot exec playwright install ffmpeg
        if ($LASTEXITCODE -ne 0) { throw "The isolated Playwright recording dependency could not be prepared." }
        $captureArguments = @(
            "run", "capture", "--",
            "--frontend-url=http://localhost:$FrontendPort",
            "--backend-url=http://127.0.0.1:$BackendPort",
            "--headed=$($HeadedCapture.IsPresent.ToString().ToLowerInvariant())"
        )
        & $npmCommand.Source --prefix $videoRoot @captureArguments
        if ($LASTEXITCODE -ne 0) { throw "Automated browser capture failed." }
    }

    & $npmCommand.Source --prefix $videoRoot run render
    if ($LASTEXITCODE -ne 0) { throw "Remotion render failed." }
    $output = Join-Path $videoRoot "output\simulation-demo-4k.mp4"
    Write-Host "4K simulation video created: $output" -ForegroundColor Green
}
finally {
    Stop-ProcessTree -Process $frontendProcess
    Stop-ProcessTree -Process $backendProcess
    foreach ($name in $previousEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name], "Process")
    }
    Write-Host "Capture services stopped. Logs: $logRoot"
}
