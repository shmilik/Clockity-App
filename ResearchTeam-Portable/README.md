# ResearchTeam Portable

An AI-powered research team that writes organized notes to Obsidian.
Built on AutoGen + Claude (Anthropic). Works from a thumbdrive on any Windows PC.

---

## First-Time Setup (each new computer)

1. **Edit `config.ini`** and fill in:
   - `anthropic_api_key` â€” your Anthropic API key
   - `vault_path` â€” full path to your Obsidian Research subfolder on this machine
   - `vault_root` â€” full path to your Obsidian vault root on this machine

2. **Right-click `FIRST_TIME_SETUP.ps1`** â†’ **Run with PowerShell**
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
  config.ini                â† Your settings (edit per machine)
  FIRST_TIME_SETUP.ps1      â† Run once per machine
  START_AUTOGEN_STUDIO.bat  â† Daily launcher
  app/                      â† Python scripts
  autogenstudio/            â† AutoGen Studio database (your team lives here)
  python/                   â† Python 3.13 embeddable (downloaded on first setup)
  .python_path              â† Auto-created by setup, points to Python exe
```

---

## Troubleshooting

**"Site can't be reached"** â€” The server stopped. Re-launch `START_AUTOGEN_STUDIO.bat`.

**Run gets stuck** â€” Open a second PowerShell window, run:
```powershell
cd path\to\ResearchTeam-Portable
$python = Get-Content .python_path
& $python app\register_research_team.py --db autogenstudio\autogen04202.db
```

**Wrong Obsidian path** â€” Edit `config.ini` then re-run `FIRST_TIME_SETUP.ps1`.

**New API key** â€” Edit `config.ini`, then delete `app\research_config.py` and re-run `FIRST_TIME_SETUP.ps1`.
