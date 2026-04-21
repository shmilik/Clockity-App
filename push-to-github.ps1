param(
    [string]$CommitMessage = ""
)

$projectPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectPath

Write-Host "==================================" -ForegroundColor Cyan
Write-Host "SlimeTime GitHub Push" -ForegroundColor Cyan
Write-Host "==================================" -ForegroundColor Cyan
Write-Host ""

# Check if we're in a git repository
if (-not (Test-Path .git)) {
    Write-Host "Error: Not in a git repository" -ForegroundColor Red
    exit 1
}

# Show current status
Write-Host "Current status:" -ForegroundColor Yellow
git status --short
Write-Host ""

# If no commit message provided, prompt for one
if ([string]::IsNullOrWhiteSpace($CommitMessage)) {
    $CommitMessage = Read-Host "Enter commit message"
}

if ([string]::IsNullOrWhiteSpace($CommitMessage)) {
    Write-Host "Commit message cannot be empty. Aborting." -ForegroundColor Red
    exit 1
}

# Add, commit, and push
Write-Host "Adding changes..." -ForegroundColor Yellow
git add .

Write-Host "Committing with message: '$CommitMessage'" -ForegroundColor Yellow
git commit -m "$CommitMessage"

Write-Host "Pushing to GitHub..." -ForegroundColor Yellow
git push

Write-Host ""
Write-Host "==================================" -ForegroundColor Green
Write-Host "Push complete!" -ForegroundColor Green
Write-Host "==================================" -ForegroundColor Green
Write-Host ""
Write-Host "Press any key to exit..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
