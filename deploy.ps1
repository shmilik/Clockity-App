param(
    [string]$CommitMessage = ""
)

$env:PATH += ';C:\Program Files\Git\cmd'
$projectPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectPath

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Clockity Deploy" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ── Step 1: Commit & push to GitHub ──────────────────────────────────────────
git add .
$status = git status --porcelain
if ($status) {
    if ([string]::IsNullOrWhiteSpace($CommitMessage)) {
        $CommitMessage = Read-Host "Commit message (or Enter for timestamp)"
    }
    if ([string]::IsNullOrWhiteSpace($CommitMessage)) {
        $CommitMessage = "Update " + (Get-Date -Format 'yyyy-MM-dd HH:mm')
    }
    git commit -m $CommitMessage
    if ($LASTEXITCODE -ne 0) { Write-Host "Commit failed." -ForegroundColor Red; exit 1 }
} else {
    Write-Host "Nothing to commit." -ForegroundColor Yellow
}

git push
if ($LASTEXITCODE -ne 0) { Write-Host "Push failed." -ForegroundColor Red; exit 1 }
Write-Host "✅ Pushed to GitHub." -ForegroundColor Green
Write-Host ""

# ── Step 2: Pull on server & restart ─────────────────────────────────────────
Write-Host "Deploying to clockity.us..." -ForegroundColor Yellow
ssh root@45.32.169.88 "cd /var/www/jobtracker && git pull && systemctl restart jobtracker && echo 'DEPLOY_OK'"

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "✅ Deploy complete! clockity.us is live." -ForegroundColor Green
} else {
    Write-Host "❌ Server deploy failed. Check the server." -ForegroundColor Red
}
