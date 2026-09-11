# Windows PowerShell / pwsh entry for the research-cycle operator pack.
# This is not a POSIX shell script. POSIX operators should use
# scripts/run_research_cycle_audit.sh instead.
#
# Read-only by default. Writes only under -OutputDir / --output-dir.
# Does not download data, install packages, mutate git, or run solvers
# unless --allow-solver is passed through to the Python orchestrator.
#
# Infrastructure PASS is not a scientific PASS.
# Synthetic fixtures are not an empirical PASS.

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$OutputDir = "",

    [Parameter(Mandatory = $false)]
    [string]$Python = "",

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Remaining = @()
)

$ErrorActionPreference = "Stop"

function Get-RepoRoot {
    $scriptDir = Split-Path -Parent $PSCommandPath
    return (Resolve-Path (Join-Path $scriptDir "..")).Path
}

$passthru = New-Object System.Collections.Generic.List[string]
$resolvedOutput = $OutputDir

if ($Remaining) {
    for ($i = 0; $i -lt $Remaining.Count; $i++) {
        $token = $Remaining[$i]
        if ($token -eq "--output-dir") {
            if ($i + 1 -ge $Remaining.Count) {
                Write-Error "--output-dir requires a path"
                exit 20
            }
            $resolvedOutput = $Remaining[$i + 1]
            [void]$passthru.Add($token)
            [void]$passthru.Add($Remaining[$i + 1])
            $i++
            continue
        }
        if ($token -like "--output-dir=*") {
            $resolvedOutput = $token.Substring("--output-dir=".Length)
            [void]$passthru.Add($token)
            continue
        }
        [void]$passthru.Add($token)
    }
}

if ([string]::IsNullOrWhiteSpace($resolvedOutput)) {
    Write-Error "-OutputDir / --output-dir is required; refusing to write elsewhere"
    exit 20
}

if (-not ($passthru -contains "--output-dir") -and -not ($passthru | Where-Object { $_ -like "--output-dir=*" })) {
    [void]$passthru.Insert(0, $resolvedOutput)
    [void]$passthru.Insert(0, "--output-dir")
}

$repoRoot = Get-RepoRoot
Set-Location $repoRoot

$pythonExe = $Python
if ([string]::IsNullOrWhiteSpace($pythonExe)) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) {
        $pythonExe = $cmd.Source
    }
    else {
        $cmd = Get-Command python3 -ErrorAction SilentlyContinue
        if ($cmd) {
            $pythonExe = $cmd.Source
        }
        else {
            $cmd = Get-Command py -ErrorAction SilentlyContinue
            if ($cmd) {
                $pythonExe = $cmd.Source
            }
        }
    }
}

if ([string]::IsNullOrWhiteSpace($pythonExe)) {
    Write-Error "python/python3/py not found (NOT_AVAILABLE)"
    exit 40
}

$env:PYTHONPATH = if ($env:PYTHONPATH) { "$repoRoot;$env:PYTHONPATH" } else { $repoRoot }

$argList = @(
    "-m", "ops.research_cycle", "audit",
    "--shell-family", "powershell",
    "--python", $pythonExe
) + $passthru.ToArray()

& $pythonExe @argList
exit $LASTEXITCODE
