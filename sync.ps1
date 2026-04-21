$env:PATH += ";C:\Program Files\Git\cmd"
Set-Location "C:\Users\info\OneDrive\Desktop\JobTracker"

Write-Host ""
Write-Host "=== SlimeTime GitHub Sync ===" -ForegroundColor Cyan

# Pull first
Write-Host "`n⬇  Pulling latest changes..." -ForegroundColor Yellow
git pull

# Check if there's anything to commit
$status = git status --porcelain
if ($status) {
    Write-Host "`n📝 Changes detected:" -ForegroundColor Yellow
    git status --short
    $msg = Read-Host "`nCommit message (press Enter for timestamp)"
    if (-not $msg) { $msg = "Update " + (Get-Date -Format "yyyy-MM-dd HH:mm") }
    git add .
    git commit -m $msg
    git push
    Write-Host "`n✅ Pushed to GitHub!" -ForegroundColor Green
} else {
    Write-Host "`n✅ Nothing new to push — already up to date." -ForegroundColor Green
}

Write-Host ""
pause
