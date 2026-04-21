# build_portable.ps1
# Creates a self-contained "ResearchTeam-Portable" folder you can copy to a thumbdrive.
# Run this once on your main PC. The resulting folder is ~500 MB - 1 GB.
#
# What it produces:
#   ResearchTeam-Portable\
#     config.ini                  ← Edit this: API key + Obsidian vault path
#     FIRST_TIME_SETUP.ps1        ← Run once on each new computer
#     START_AUTOGEN_STUDIO.bat    ← Daily launcher (double-click)
#     README.md
#     app\                        ← Python scripts
#     autogenstudio\              ← AutoGen Studio DB (your team is pre-loaded)
#     python\                     ← Python 3.13 embeddable (downloaded on first setup)

$ErrorActionPreference = "Stop"
$here  = $PSScriptRoot
$dest  = Join-Path $here "ResearchTeam-Portable"

Write-Host ""
Write-Host "=== Building ResearchTeam Portable Bundle ===" -ForegroundColor Cyan
Write-Host "Destination: $dest" -ForegroundColor Gray
Write-Host ""

# ── 1. Create folder structure ────────────────────────────────────────────────────
foreach ($sub in @("", "app", "autogenstudio", "python")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $dest $sub) | Out-Null
}

# ── 2. Copy Python scripts ────────────────────────────────────────────────────────
$scripts = @(
    "research_team.py",
    "register_research_team.py",
    "requirements.txt"
)
foreach ($f in $scripts) {
    $src = Join-Path $here $f
    if (Test-Path $src) {
        Copy-Item $src "$dest\app\$f" -Force
        Write-Host "  Copied: $f" -ForegroundColor Gray
    } else {
        Write-Warning "  Not found (skipped): $f"
    }
}

# ── 3. Copy AutoGen Studio DB (your team is already registered inside) ────────────
$dbSrc = Join-Path $env:USERPROFILE ".autogenstudio\autogen04202.db"
if (Test-Path $dbSrc) {
    Copy-Item $dbSrc "$dest\autogenstudio\autogen04202.db" -Force
    Write-Host "  Copied: AutoGen Studio DB" -ForegroundColor Gray
} else {
    Write-Warning "  DB not found at $dbSrc - you'll need to run register manually after setup."
}

# ── 4. Create config.ini template ────────────────────────────────────────────────
@'
# ResearchTeam Configuration
# Edit this file before running FIRST_TIME_SETUP.ps1

[api]
anthropic_api_key = sk-ant-REPLACE_WITH_YOUR_KEY

[model]
claude_model = claude-haiku-4-5-20251001

[obsidian]
# Full path to the Research subfolder inside your Obsidian vault
vault_path = C:\Users\YOUR_USERNAME\Documents\Obsidian Vault\Vault 1\Research

# Full path to the root of your Obsidian vault
vault_root = C:\Users\YOUR_USERNAME\Documents\Obsidian Vault\Vault 1
'@ | Set-Content "$dest\config.ini" -Encoding UTF8
Write-Host "  Created: config.ini" -ForegroundColor Gray

# ── 5. Create FIRST_TIME_SETUP.ps1 (runs on each new machine) ────────────────────
@'
# FIRST_TIME_SETUP.ps1
# Run this ONCE on each new computer before using ResearchTeam.
# Requirements: Windows 10/11 64-bit, internet connection, ~1 GB free disk space.

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Definition

Write-Host ""
Write-Host "=== ResearchTeam First-Time Setup ===" -ForegroundColor Cyan
Write-Host ""

# ── Step 1: Check config.ini ─────────────────────────────────────────────────────
if (-not (Test-Path "$here\config.ini")) {
    Write-Host "ERROR: config.ini not found. Cannot continue." -ForegroundColor Red
    pause; exit 1
}

$config = @{}
Get-Content "$here\config.ini" | ForEach-Object {
    if ($_ -match "^\s*([^#=\[\]]+?)\s*=\s*(.+)$") {
        $config[$Matches[1].Trim()] = $Matches[2].Trim()
    }
}

$apiKey    = $config["anthropic_api_key"]
$model     = $config["claude_model"]
$vault     = $config["vault_path"]
$vaultRoot = $config["vault_root"]

if ($apiKey -eq "sk-ant-REPLACE_WITH_YOUR_KEY" -or -not $apiKey) {
    Write-Host "ERROR: Edit config.ini and set your Anthropic API key first!" -ForegroundColor Red
    Write-Host "       Then run this script again." -ForegroundColor Yellow
    pause; exit 1
}

Write-Host "Config loaded OK." -ForegroundColor Green

# ── Step 2: Locate or download Python ────────────────────────────────────────────
$pythonDir = "$here\python"
$pythonExe = "$pythonDir\python.exe"

if (Test-Path $pythonExe) {
    Write-Host "Python already present in .\python\" -ForegroundColor Green
} else {
    # Search for Python 3.10+ already on the machine
    $found = $null
    foreach ($candidate in @("python", "python3", "py")) {
        try {
            $v = & $candidate --version 2>&1
            if ("$v" -match "Python 3\.(1[0-9]|[89])") {
                $found = (Get-Command $candidate -ErrorAction SilentlyContinue)?.Source
                break
            }
        } catch {}
    }

    if ($found) {
        Write-Host "Using system Python: $found" -ForegroundColor Green
        $pythonExe = $found
    } else {
        Write-Host "Python not found - downloading Python 3.13 embeddable..." -ForegroundColor Yellow
        $pyVer = "3.13.3"
        $pyZip = "$here\python\_embed.zip"
        $url   = "https://www.python.org/ftp/python/$pyVer/python-$pyVer-embed-amd64.zip"
        New-Item -ItemType Directory -Force -Path $pythonDir | Out-Null
        Write-Host "  Downloading $url" -ForegroundColor Gray
        Invoke-WebRequest -Uri $url -OutFile $pyZip -UseBasicParsing
        Write-Host "  Extracting..." -ForegroundColor Gray
        Expand-Archive -Path $pyZip -DestinationPath $pythonDir -Force
        Remove-Item $pyZip

        # Enable site-packages inside the embeddable layout
        $pth = Get-ChildItem $pythonDir -Filter "python*._pth" | Select-Object -First 1
        if ($pth) {
            (Get-Content $pth.FullName) -replace "#import site", "import site" | Set-Content $pth.FullName
        }

        # Bootstrap pip
        Write-Host "  Bootstrapping pip..." -ForegroundColor Gray
        $getPip = "$pythonDir\_get-pip.py"
        Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPip -UseBasicParsing
        & $pythonDir\python.exe $getPip --no-warn-script-location | Out-Null
        Remove-Item $getPip
    }
}

# Save resolved python path for launchers
$pythonExe | Set-Content "$here\.python_path" -Encoding UTF8
Write-Host "Python: $pythonExe" -ForegroundColor Gray

# ── Step 3: Install packages ──────────────────────────────────────────────────────
Write-Host ""
Write-Host "Installing packages (10-25 min on first run, needs internet)..." -ForegroundColor Yellow

$pkgs = @(
    "autogen-agentchat==0.5.7",
    "autogen-ext==0.5.7",
    "autogenstudio==0.4.2.2",
    "anthropic>=0.94.0",
    "wikipedia-api",
    "arxiv",
    "ddgs",
    "beautifulsoup4",
    "requests",
    "pymupdf4llm",
    "pdfplumber"
)
foreach ($pkg in $pkgs) {
    Write-Host "  pip install $pkg" -ForegroundColor Gray
    & $pythonExe -m pip install $pkg --quiet --no-warn-script-location
}
Write-Host "Packages installed." -ForegroundColor Green

# ── Step 4: Generate research_config.py ──────────────────────────────────────────
Write-Host ""
Write-Host "Writing app\research_config.py..." -ForegroundColor Cyan
@"
# Auto-generated by FIRST_TIME_SETUP.ps1 from config.ini
ANTHROPIC_API_KEY = "$apiKey"
CLAUDE_MODEL      = "$model"
OBSIDIAN_VAULT    = r"$vault"
VAULT_ROOT        = r"$vaultRoot"
"@ | Set-Content "$here\app\research_config.py" -Encoding UTF8

# ── Step 5: Register the AI team in the portable DB ──────────────────────────────
$db = "$here\autogenstudio\autogen04202.db"
if (Test-Path $db) {
    Write-Host "Registering AI team in portable database..." -ForegroundColor Cyan
    & $pythonExe "$here\app\register_research_team.py" `
        --db "$db" `
        --vault "$vault" `
        --vault-root "$vaultRoot"
    Write-Host "Team registered." -ForegroundColor Green
} else {
    Write-Host "DB not found at $db - skipping team registration." -ForegroundColor Yellow
    Write-Host "Run: python app\register_research_team.py --db autogenstudio\autogen04202.db" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "==================================================================" -ForegroundColor Green
Write-Host "  Setup complete!" -ForegroundColor Green
Write-Host "  Double-click START_AUTOGEN_STUDIO.bat to launch." -ForegroundColor Cyan
Write-Host "  Then open http://127.0.0.1:8080 in your browser." -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Green
Write-Host ""
pause
'@ | Set-Content "$dest\FIRST_TIME_SETUP.ps1" -Encoding UTF8
Write-Host "  Created: FIRST_TIME_SETUP.ps1" -ForegroundColor Gray

# ── 6. Create START_AUTOGEN_STUDIO.bat ───────────────────────────────────────────
@'
@echo off
cd /d "%~dp0"
if not exist ".python_path" (
    echo.
    echo  ERROR: Python not configured.
    echo  Please run FIRST_TIME_SETUP.ps1 first (right-click -> Run with PowerShell).
    echo.
    pause
    exit /b 1
)
set /p PYTHON_EXE=<.python_path
echo.
echo  Starting ResearchTeam AutoGen Studio...
echo  Browser: http://127.0.0.1:8080
echo  Press Ctrl+C to stop the server.
echo.
"%PYTHON_EXE%" -m autogenstudio ui --host 127.0.0.1 --port 8080 --appdir "%~dp0autogenstudio"
pause
'@ | Set-Content "$dest\START_AUTOGEN_STUDIO.bat" -Encoding ASCII
Write-Host "  Created: START_AUTOGEN_STUDIO.bat" -ForegroundColor Gray

# ── 7. Create README.md ───────────────────────────────────────────────────────────
@'
# ResearchTeam Portable

An AI-powered research team that writes organized notes to Obsidian.
Built on AutoGen + Claude (Anthropic). Works from a thumbdrive on any Windows PC.

---

## First-Time Setup (each new computer)

1. **Edit `config.ini`** and fill in:
   - `anthropic_api_key` — your Anthropic API key
   - `vault_path` — full path to your Obsidian Research subfolder on this machine
   - `vault_root` — full path to your Obsidian vault root on this machine

2. **Right-click `FIRST_TIME_SETUP.ps1`** → **Run with PowerShell**
   - Downloads Python 3.13 embeddable (if Python is not already installed)
   - Installs all required packages (~500 MB, needs internet, takes 15-25 min)
   - Registers your AI team in the local database

3. Done! Use the daily launcher below from now on.

---

## Daily Use

1. Double-click **`START_AUTOGEN_STUDIO.bat`**
2. Open browser to **http://127.0.0.1:8080**
3. Navigate to the **Research Team** and type your task

---

## What the Agents Do

| Agent | Role |
|---|---|
| **Orchestrator** | Plans the research strategy, decides what to search and how to organize it |
| **WebResearcher** | Web searches (DuckDuckGo) + page scraping + PDF extraction |
| **WikiExpert** | Wikipedia lookups + academic paper search (arXiv) |
| **ObsidianWriter** | Writes, edits, and links notes in your Obsidian vault |
| **Critic** | Reviews completeness and accuracy before finalizing |

---

## Example Tasks

**Research mode** (creates new notes):
> "Research the history of double-entry bookkeeping and write a structured note to Obsidian."

**Vault web mode** (links existing notes):
> "Scan my vault for notes about banking and finance. Create a Map of Content (MOC) that links them all together."

---

## Folder Structure

```
ResearchTeam-Portable/
  config.ini                ← Your settings (edit per machine)
  FIRST_TIME_SETUP.ps1      ← Run once per machine
  START_AUTOGEN_STUDIO.bat  ← Daily launcher
  app/                      ← Python scripts
  autogenstudio/            ← AutoGen Studio database (your team lives here)
  python/                   ← Python 3.13 embeddable (downloaded on first setup)
  .python_path              ← Auto-created by setup, points to Python exe
```

---

## Troubleshooting

**"Site can't be reached"** — The server stopped. Re-launch `START_AUTOGEN_STUDIO.bat`.

**Run gets stuck** — Open a second PowerShell window, run:
```powershell
cd path\to\ResearchTeam-Portable
$python = Get-Content .python_path
& $python app\register_research_team.py --db autogenstudio\autogen04202.db
```

**Wrong Obsidian path** — Edit `config.ini` then re-run `FIRST_TIME_SETUP.ps1`.

**New API key** — Edit `config.ini`, then delete `app\research_config.py` and re-run `FIRST_TIME_SETUP.ps1`.
'@ | Set-Content "$dest\README.md" -Encoding UTF8
Write-Host "  Created: README.md" -ForegroundColor Gray

# ── Done ─────────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "=================================================================" -ForegroundColor Green
Write-Host "  Portable bundle ready!" -ForegroundColor Green
Write-Host "  Location: $dest" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Copy the entire 'ResearchTeam-Portable' folder to your thumbdrive."
Write-Host "  2. On any new PC: edit config.ini, then right-click FIRST_TIME_SETUP.ps1"
Write-Host "     -> 'Run with PowerShell'  (needs internet, ~15-25 min first time)."
Write-Host "  3. Daily use: double-click START_AUTOGEN_STUDIO.bat."
Write-Host ""
