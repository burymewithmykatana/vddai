[CmdletBinding()]
param(
    [string]$PythonCommand = "",
    [switch]$IncludeFormatting,
    [switch]$IncludeDockerConfig
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ExpectedPythonVersion = "3.14.3"
$ExpectedPipVersion = "26.1.2"
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RequirementsPath = Join-Path $RepositoryRoot "requirements.txt"
$VirtualEnvironmentPython = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [string[]]$Arguments = @()
    )

    Write-Host "> $FilePath $($Arguments -join ' ')"
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Verification command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

function Get-PythonVersion {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath
    )

    $VersionOutput = (& $FilePath --version 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to execute Python command: $FilePath"
    }
    if ($VersionOutput -notmatch '^Python (?<version>\d+\.\d+\.\d+)$') {
        throw "Unexpected Python version output: $VersionOutput"
    }

    return $Matches.version
}

function Get-PipVersion {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath
    )

    $VersionOutput = (& $FilePath -m pip --version 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to inspect pip through: $FilePath"
    }
    if ($VersionOutput -notmatch '^pip (?<version>[^\s]+)\s') {
        throw "Unexpected pip version output: $VersionOutput"
    }

    return $Matches.version
}

function Get-NormalizedPackageName {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    return ($Name.Trim().ToLowerInvariant() -replace '[-_.]+', '-')
}

function Assert-PinnedRequirements {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string]$RequirementsFile
    )

    $InstalledJson = (& $FilePath -m pip list --format=json --disable-pip-version-check | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to inspect installed packages through: $FilePath"
    }

    try {
        $InstalledPackages = ConvertFrom-Json -InputObject $InstalledJson
    }
    catch {
        throw "Unable to parse installed package metadata: $($_.Exception.Message)"
    }

    $InstalledByName = @{}
    foreach ($Package in $InstalledPackages) {
        $NormalizedName = Get-NormalizedPackageName -Name ([string]$Package.name)
        $InstalledByName[$NormalizedName] = [string]$Package.version
    }

    $Drift = [System.Collections.Generic.List[string]]::new()
    foreach ($RawLine in Get-Content -LiteralPath $RequirementsFile) {
        $Line = $RawLine.Trim()
        if ([string]::IsNullOrWhiteSpace($Line) -or $Line.StartsWith("#")) {
            continue
        }
        if ($Line -notmatch '^(?<name>[A-Za-z0-9][A-Za-z0-9_.-]*)==(?<version>[^\s;]+)$') {
            throw "Unsupported requirement syntax; exact name==version pins are required: $Line"
        }

        $RequiredName = Get-NormalizedPackageName -Name $Matches.name
        $RequiredVersion = $Matches.version
        if (-not $InstalledByName.ContainsKey($RequiredName)) {
            $Drift.Add("${RequiredName} is missing; expected ${RequiredVersion}.")
            continue
        }

        $InstalledVersion = $InstalledByName[$RequiredName]
        if ($InstalledVersion -ne $RequiredVersion) {
            $Drift.Add("${RequiredName} is ${InstalledVersion}; expected ${RequiredVersion}.")
        }
    }

    if ($Drift.Count -ne 0) {
        throw "Installed dependencies do not match requirements.txt:`n- $($Drift -join "`n- ")"
    }
}

if (-not (Test-Path -LiteralPath $RequirementsPath -PathType Leaf)) {
    throw "Pinned requirements file is missing: $RequirementsPath"
}

if ([string]::IsNullOrWhiteSpace($PythonCommand)) {
    if (-not (Test-Path -LiteralPath $VirtualEnvironmentPython -PathType Leaf)) {
        throw "Pinned .venv is missing. Run .\scripts\bootstrap.ps1 before verification."
    }
    $PythonCommand = $VirtualEnvironmentPython
}

Push-Location $RepositoryRoot
try {
    Write-Host "VDDAI verification root: $RepositoryRoot"

    $PythonVersion = Get-PythonVersion -FilePath $PythonCommand
    if ($PythonVersion -ne $ExpectedPythonVersion) {
        throw "VDDAI verification requires Python $ExpectedPythonVersion; received $PythonVersion from $PythonCommand."
    }
    Write-Host "Validated Python $PythonVersion."

    $PipVersion = Get-PipVersion -FilePath $PythonCommand
    if ($PipVersion -ne $ExpectedPipVersion) {
        throw "VDDAI verification requires pip $ExpectedPipVersion; received $PipVersion from $PythonCommand."
    }
    Write-Host "Validated pip $PipVersion."

    Assert-PinnedRequirements -FilePath $PythonCommand -RequirementsFile $RequirementsPath
    Write-Host "Validated exact requirements.txt pins."

    Invoke-NativeCommand -FilePath $PythonCommand -Arguments @(
        "-m",
        "pip",
        "check"
    )

    if ($IncludeFormatting) {
        Invoke-NativeCommand -FilePath $PythonCommand -Arguments @(
            "-m",
            "black",
            "--check",
            "."
        )
    }
    else {
        Write-Host "Formatting check skipped. Use -IncludeFormatting when the task requires it."
    }

    Invoke-NativeCommand -FilePath $PythonCommand -Arguments @(
        "-m",
        "pytest",
        "-q"
    )

    if ($IncludeDockerConfig) {
        Invoke-NativeCommand -FilePath "docker" -Arguments @(
            "compose",
            "-f",
            "docker-compose.yaml",
            "config",
            "--quiet"
        )
    }

    Write-Host "VDDAI verification passed."
}
finally {
    Pop-Location
}
