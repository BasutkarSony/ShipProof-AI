# Create a clean, single-main-branch ParcelProof AI repository.
# Run this from the existing ShipProof-AI project after pulling the latest branch.
# Requires Git, GitHub CLI (gh), and an authenticated GitHub CLI session.

$ErrorActionPreference = "Stop"

$Owner = "BasutkarSony"
$NewRepoName = "ParcelProof-AI"
$NewRepoFullName = "$Owner/$NewRepoName"
$SourceRepoUrl = "https://github.com/BasutkarSony/ShipProof-AI.git"
$SourceBranch = "parcelproof/stage-a-b-order-checkout"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ParentDirectory = Split-Path -Parent $ProjectRoot
$Destination = Join-Path $ParentDirectory $NewRepoName

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git is required. Install Git for Windows and run this script again."
}

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI is required. Install it from https://cli.github.com/ and run: gh auth login"
}

if (Test-Path $Destination) {
    throw "Destination already exists: $Destination. Rename or move that folder before retrying."
}

Write-Host "Checking GitHub CLI authentication..."
gh auth status
if ($LASTEXITCODE -ne 0) {
    throw "GitHub CLI is not authenticated. Run: gh auth login"
}

Write-Host "Downloading the verified ParcelProof source snapshot..."
git clone --depth 1 --branch $SourceBranch $SourceRepoUrl $Destination
if ($LASTEXITCODE -ne 0) {
    throw "Could not download the latest verified development branch."
}

# Remove the old repository history so the new project starts with one clean main branch.
$OldGitDirectory = Join-Path $Destination ".git"
if (Test-Path $OldGitDirectory) {
    Remove-Item -LiteralPath $OldGitDirectory -Recurse -Force
}

Push-Location $Destination
try {
    git init -b main
    if ($LASTEXITCODE -ne 0) { throw "Could not initialize the clean main branch." }

    git add -A
    if ($LASTEXITCODE -ne 0) { throw "Could not stage the clean project files." }

    git commit -m "Initial release: ParcelProof AI"
    if ($LASTEXITCODE -ne 0) { throw "Could not create the initial repository commit." }

    Write-Host "Creating the new public GitHub repository and pushing main..."
    gh repo create $NewRepoFullName --public --source . --remote origin --push --description "PayPal-connected order fulfilment and AI-assisted shipment evidence review."
    if ($LASTEXITCODE -ne 0) {
        throw "GitHub could not create or push the new repository. Check whether $NewRepoFullName already exists and run gh auth status."
    }

    Write-Host ""
    Write-Host "ParcelProof AI is now on GitHub:"
    Write-Host "https://github.com/$NewRepoFullName"
    Write-Host ""
    Write-Host "Local clean project: $Destination"
    Write-Host "Default branch: main"
    Write-Host "Old ShipProof-AI repository was not changed or deleted."
}
finally {
    Pop-Location
}
