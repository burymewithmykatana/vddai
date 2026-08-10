[CmdletBinding()]
param(
    [string]$PythonCommand = "python",
    [switch]$CheckOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ExpectedPythonVersion = "3.14.3"
$ExpectedPipVersion = "26.1.2"
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RequirementsPath = Join-Path $RepositoryRoot "requirements.txt"
$EnvironmentExamplePath = Join-Path $RepositoryRoot ".env.example"
$EnvironmentPath = Join-Path $RepositoryRoot ".env"
$VirtualEnvironmentPath = Join-Path $RepositoryRoot ".venv"
$VirtualEnvironmentPython = Join-Path $VirtualEnvironmentPath "Scripts\python.exe"

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [string[]]$Arguments = @()
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

function Get-PythonVersion {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath
    )

    $versionOutput = (& $FilePath --version 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to execute Python command: $FilePath"
    }

    if ($versionOutput -notmatch '^Python (?<version>\d+\.\d+\.\d+)$') {
        throw "Unexpected Python version output: $versionOutput"
    }

    return $Matches.version
}

if (-not (Test-Path -LiteralPath $RequirementsPath -PathType Leaf)) {
    throw "Pinned requirements file is missing: $RequirementsPath"
}

if (-not (Test-Path -LiteralPath $EnvironmentExamplePath -PathType Leaf)) {
    throw "Environment template is missing: $EnvironmentExamplePath"
}

$BootstrapPythonVersion = Get-PythonVersion -FilePath $PythonCommand
if ($BootstrapPythonVersion -ne $ExpectedPythonVersion) {
    throw "VDDAI requires Python $ExpectedPythonVersion; received $BootstrapPythonVersion from $PythonCommand."
}

Push-Location $RepositoryRoot
try {
    if (-not (Test-Path -LiteralPath $VirtualEnvironmentPython -PathType Leaf)) {
        if ($CheckOnly) {
            throw "Virtual environment is missing or incomplete: $VirtualEnvironmentPath"
        }

        Write-Host "Creating .venv with Python $ExpectedPythonVersion..."
        Invoke-NativeCommand -FilePath $PythonCommand -Arguments @(
            "-m",
            "venv",
            $VirtualEnvironmentPath
        )
    }

    $VenvPythonVersion = Get-PythonVersion -FilePath $VirtualEnvironmentPython
    if ($VenvPythonVersion -ne $ExpectedPythonVersion) {
        throw "Existing .venv uses Python $VenvPythonVersion; expected $ExpectedPythonVersion. Remove or relocate it explicitly, then rerun bootstrap."
    }

    if (-not $CheckOnly) {
        Write-Host "Installing the pinned bootstrap toolchain..."
        Invoke-NativeCommand -FilePath $VirtualEnvironmentPython -Arguments @(
            "-m",
            "pip",
            "install",
            "--upgrade",
            "pip==$ExpectedPipVersion"
        )

        Write-Host "Installing pinned project dependencies..."
        Invoke-NativeCommand -FilePath $VirtualEnvironmentPython -Arguments @(
            "-m",
            "pip",
            "install",
            "--requirement",
            $RequirementsPath
        )
    }

    $PipVersionOutput = (
        & $VirtualEnvironmentPython -m pip --version 2>&1 | Out-String
    ).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to inspect pip in .venv."
    }
    if ($PipVersionOutput -notmatch "^pip $([regex]::Escape($ExpectedPipVersion))\b") {
        throw "VDDAI bootstrap expects pip $ExpectedPipVersion; received: $PipVersionOutput"
    }

    Invoke-NativeCommand -FilePath $VirtualEnvironmentPython -Arguments @(
        "-m",
        "pip",
        "check"
    )

    if (-not (Test-Path -LiteralPath $EnvironmentPath -PathType Leaf)) {
        if ($CheckOnly) {
            throw "Local .env is missing. Run bootstrap without -CheckOnly to create it from .env.example."
        }

        Copy-Item -LiteralPath $EnvironmentExamplePath -Destination $EnvironmentPath
        Write-Host "Created .env from .env.example. Review hostnames before running services on the host."
    }
    else {
        Write-Host "Preserved existing .env."
    }

    $Mode = if ($CheckOnly) { "validation" } else { "bootstrap" }
    Write-Host "VDDAI $Mode complete: Python $ExpectedPythonVersion, pip $ExpectedPipVersion, dependencies valid."
}
finally {
    Pop-Location
}
