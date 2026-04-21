"""
Registers the Research Team into AutoGen Studio's database.
Run once. After running, refresh the AutoGen Studio UI to see the team.

Usage:
  python register_research_team.py                  # uses default paths
  python register_research_team.py --db path/to.db  # custom DB for portable use
"""
import sqlite3, json, sys, os, argparse
from datetime import datetime

# ── Argument parsing ─────────────────────────────────────────────────────────────
_parser = argparse.ArgumentParser(add_help=False)
_parser.add_argument("--db", default=None)
_parser.add_argument("--vault", default=None)
_parser.add_argument("--vault-root", default=None)
_parser.add_argument("--user", default=None)
_args, _ = _parser.parse_known_args()

# ── Defaults (overridden by --args above) ────────────────────────────────────────
DB_PATH      = _args.db        or r"C:\Users\info\.autogenstudio\autogen04202.db"
USER_ID      = _args.user      or "guestuser@gmail.com"
VAULT        = _args.vault     or r"C:\Users\info\OneDrive\Documents\Obsidian Vault\Vault 1\Research"
VAULT_ROOT   = _args.vault_root or r"C:\Users\info\OneDrive\Documents\Obsidian Vault\Vault 1"

# ── Read API key from research_config (search script dir first for portability) ──
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)
# Also try the original install location as fallback
_orig_dir = r"C:\Users\info\OneDrive\Desktop\JobTracker"
if _orig_dir not in sys.path:
    sys.path.append(_orig_dir)
import research_config as cfg
API_KEY = cfg.ANTHROPIC_API_KEY

# ── Model client template ────────────────────────────────────────────────────────
MODEL_INFO = {
    "vision": True,
    "function_calling": True,
    "json_output": True,
    "structured_output": False,
    "family": "unknown",
    "multiple_system_messages": False,
}

def model_client(temperature: float = 0.3) -> dict:
    return {
        "provider": "autogen_ext.models.anthropic.AnthropicChatCompletionClient",
        "component_type": "model",
        "version": 1,
        "component_version": 1,
        "description": "Claude claude-haiku-4-5 via Anthropic API.",
        "label": "AnthropicChatCompletionClient",
        "config": {
            "model": "claude-haiku-4-5-20251001",
            "api_key": API_KEY,
            "temperature": temperature,
            "max_tokens": 4096,
            "model_info": MODEL_INFO,
        }
    }

# ── Tool helper ──────────────────────────────────────────────────────────────────
def tool(name: str, description: str, source_code: str, global_imports: list = None) -> dict:
    return {
        "provider": "autogen_core.tools.FunctionTool",
        "component_type": "tool",
        "version": 1,
        "component_version": 1,
        "description": "Create custom tools by wrapping standard Python functions.",
        "label": "FunctionTool",
        "config": {
            "source_code": source_code,
            "name": name,
            "description": description,
            "global_imports": global_imports or [],
            "has_cancellation_support": False,
        }
    }

def workbench(tools: list) -> dict:
    return {
        "provider": "autogen_core.tools.StaticWorkbench",
        "component_type": "workbench",
        "version": 1,
        "component_version": 1,
        "description": "A workbench that provides a static set of tools.",
        "label": "StaticWorkbench",
        "config": {"tools": tools}
    }

def model_context() -> dict:
    return {
        "provider": "autogen_core.model_context.UnboundedChatCompletionContext",
        "component_type": "chat_completion_context",
        "version": 1,
        "component_version": 1,
        "description": "Unbounded chat completion context.",
        "label": "UnboundedChatCompletionContext",
        "config": {}
    }

def agent(name: str, label: str, description: str, system_message: str, tools_list: list, temperature: float = 0.3) -> dict:
    cfg_agent = {
        "name": name,
        "model_client": model_client(temperature),
        "model_context": model_context(),
        "description": description,
        "system_message": system_message,
        "model_client_stream": False,
        "reflect_on_tool_use": False,
        "tool_call_summary_format": "{result}",
    }
    if tools_list:
        cfg_agent["workbench"] = workbench(tools_list)
    return {
        "provider": "autogen_agentchat.agents.AssistantAgent",
        "component_type": "agent",
        "version": 1,
        "component_version": 1,
        "description": description,
        "label": label,
        "config": cfg_agent,
    }


# ══════════════════════════════════════════════════════════════════════════════════
# TOOL SOURCE CODE  (all imports must be inside the function body)
# ══════════════════════════════════════════════════════════════════════════════════

WEB_SEARCH_SRC = '''\
def web_search(query: str, max_results: int = 8) -> str:
    """Search the web with DuckDuckGo. Returns titles, URLs, and snippets."""
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS
    import re
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        if not results:
            return "No search results found."
        lines = []
        for i, r in enumerate(results, 1):
            snippet = r.get("body", "")[:300]
            lines.append(f"{i}. **{r['title']}**\\n   URL: {r['href']}\\n   {snippet}")
        return "\\n\\n".join(lines)
    except Exception as e:
        return f"Search error: {e}"
'''

FETCH_URL_SRC = '''\
def fetch_url(url: str) -> str:
    """Fetch a web page and return its readable text (max ~5000 chars)."""
    import requests, re
    from bs4 import BeautifulSoup
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
            tag.decompose()
        text = soup.get_text(separator="\\n", strip=True)
        text = re.sub(r"\\n{3,}", "\\n\\n", text)
        return text[:5000] + ("\\n\\n[...truncated...]" if len(text) > 5000 else "")
    except Exception as e:
        return f"Error fetching {url}: {e}"
'''

WIKIPEDIA_SRC = '''\
def wikipedia_lookup(topic: str) -> str:
    """Fetch a Wikipedia article with summary and key sections."""
    import wikipediaapi
    try:
        wiki = wikipediaapi.Wikipedia(user_agent="AutoGenResearchBot/1.0", language="en")
        page = wiki.page(topic)
        if not page.exists():
            return f"No Wikipedia page found for '{topic}'."
        section_texts = []
        for s in page.sections[:6]:
            if s.text.strip():
                section_texts.append(f"### {s.title}\\n{s.text[:700]}")
        body = "\\n\\n".join(section_texts)
        return (
            f"# {page.title}\\n\\n"
            f"**Summary:** {page.summary[:1200]}\\n\\n"
            f"{body}\\n\\n"
            f"**Wikipedia URL:** {page.fullurl}"
        )
    except Exception as e:
        return f"Wikipedia error: {e}"
'''

ARXIV_SRC = '''\
def arxiv_search(query: str, max_results: int = 5) -> str:
    """Search arXiv for academic papers."""
    import arxiv as ax
    try:
        client = ax.Client()
        search = ax.Search(query=query, max_results=max_results, sort_by=ax.SortCriterion.Relevance)
        results = list(client.results(search))
        if not results:
            return "No arXiv papers found."
        lines = []
        for p in results:
            authors = ", ".join(a.name for a in p.authors[:4])
            pub_date = p.published.strftime("%Y-%m-%d") if p.published else "unknown"
            abstract = p.summary[:500].replace("\\n", " ")
            lines.append(
                f"**{p.title}**\\nAuthors: {authors}\\nPublished: {pub_date}\\n"
                f"URL: {p.entry_id}\\nAbstract: {abstract}..."
            )
        return "\\n\\n---\\n\\n".join(lines)
    except Exception as e:
        return f"arXiv error: {e}"
'''

WRITE_NOTE_SRC = f'''\
def write_obsidian_note(relative_path: str, content: str, tags: list = None) -> str:
    """Write a Markdown note to the Obsidian vault under the Research folder."""
    import pathlib
    from datetime import datetime
    tags = tags or []
    vault = pathlib.Path(r"{VAULT}")
    note_path = vault / relative_path
    note_path.parent.mkdir(parents=True, exist_ok=True)
    tag_lines = "\\n".join(f"  - {{t}}" for t in tags) if tags else "  - research"
    created = datetime.now().strftime("%Y-%m-%d")
    frontmatter = f"---\\ncreated: {{created}}\\ntags:\\n{{tag_lines}}\\n---\\n\\n"
    note_path.write_text(frontmatter + content.lstrip(), encoding="utf-8")
    return f"Note saved: {{relative_path}}"
'''

LIST_NOTES_SRC = f'''\
def list_vault_notes(subfolder: str = "") -> str:
    """List existing Markdown notes in the Research vault."""
    import pathlib
    vault = pathlib.Path(r"{VAULT}")
    target = vault / subfolder if subfolder else vault
    if not target.exists():
        return f"Folder does not exist yet: {{target}}"
    notes = sorted(target.rglob("*.md"))
    if not notes:
        return "No notes yet."
    return "\\n".join(str(n.relative_to(vault)) for n in notes)
'''

GET_NOTE_SRC = f'''\
def get_note_content(relative_path: str) -> str:
    """Read an existing Obsidian note from the vault."""
    import pathlib
    vault = pathlib.Path(r"{VAULT}")
    note_path = vault / relative_path
    if not note_path.exists():
        return f"Note not found: {{relative_path}}"
    return note_path.read_text(encoding="utf-8")
'''

APPEND_NOTE_SRC = f'''\
def append_to_note(relative_path: str, content: str) -> str:
    """Append content to the end of an existing Obsidian note. Creates the note if it does not exist."""
    import pathlib
    vault = pathlib.Path(r"{VAULT}")
    note_path = vault / relative_path
    if not note_path.exists():
        return f"Note not found: {{relative_path}}. Use write_obsidian_note to create it first."
    existing = note_path.read_text(encoding="utf-8")
    note_path.write_text(existing.rstrip() + "\\n\\n" + content.lstrip(), encoding="utf-8")
    return f"Appended to: {{relative_path}}"
'''

REPLACE_SECTION_SRC = f'''\
def replace_note_section(relative_path: str, section_heading: str, new_content: str) -> str:
    """Replace the content of a specific ## heading section in an existing Obsidian note.
    The section is identified by its exact heading text (without the ## prefix).
    new_content should be the full replacement body for that section (heading is preserved).
    """
    import pathlib, re
    vault = pathlib.Path(r"{VAULT}")
    note_path = vault / relative_path
    if not note_path.exists():
        return f"Note not found: {{relative_path}}"
    text = note_path.read_text(encoding="utf-8")
    # Match any heading level for the section
    pattern = rf"(#+ {{re.escape(section_heading)}}\\n)(.*?)(?=\\n#+ |\\Z)"
    replacement = f"## {{section_heading}}\\n{{new_content.strip()}}\\n"
    new_text, count = re.subn(pattern, replacement, text, flags=re.DOTALL)
    if count == 0:
        # Section not found — append it
        new_text = text.rstrip() + f"\\n\\n## {{section_heading}}\\n{{new_content.strip()}}\\n"
        note_path.write_text(new_text, encoding="utf-8")
        return f"Section '{{section_heading}}' not found — appended as new section in {{relative_path}}"
    note_path.write_text(new_text, encoding="utf-8")
    return f"Replaced section '{{section_heading}}' in {{relative_path}}"
'''

FIND_REPLACE_SRC = f'''\
def find_replace_in_note(relative_path: str, find_text: str, replace_text: str) -> str:
    """Find and replace an exact string inside an existing Obsidian note.
    Returns how many replacements were made.
    """
    import pathlib
    vault = pathlib.Path(r"{VAULT}")
    note_path = vault / relative_path
    if not note_path.exists():
        return f"Note not found: {{relative_path}}"
    text = note_path.read_text(encoding="utf-8")
    if find_text not in text:
        return f"Text not found in {{relative_path}}: {{repr(find_text[:80])}}"
    count = text.count(find_text)
    new_text = text.replace(find_text, replace_text)
    note_path.write_text(new_text, encoding="utf-8")
    return f"Replaced {{count}} occurrence(s) in {{relative_path}}"
'''

# ── Vault-wide tools (access all of Vault 1, not just Research subfolder) ───────

SCAN_VAULT_SRC = f'''\
def scan_vault_structure(subfolder: str = "") -> str:
    """Scan the entire Obsidian vault and return all Markdown notes with their headings
    and outgoing [[wiki-links]]. Use this to understand what already exists before creating new notes.
    subfolder: optional path relative to Vault 1 root to limit scope (e.g. "Finance").
    Leave empty to scan the full vault.
    """
    import pathlib, re
    vault_root = pathlib.Path(r"{VAULT_ROOT}")
    target = vault_root / subfolder if subfolder else vault_root
    notes = sorted(target.rglob("*.md"))
    if not notes:
        return "No notes found."
    lines = []
    for note in notes:
        rel = note.relative_to(vault_root)
        try:
            text = note.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        headings = re.findall(r"^(#+ .+)$", text, re.MULTILINE)
        links = re.findall(r"\\[\\[([^\\]|]+)(?:\\|[^\\]]*)?\\]\\]", text)
        links_unique = list(dict.fromkeys(links))
        h_str = " | ".join(h.strip() for h in headings[:5])
        l_str = ", ".join(f"[[{{l}}]]" for l in links_unique[:10])
        lines.append(f"NOTE: {{rel}}\\n  Headings: {{h_str or chr(40) + chr(110) + chr(111) + chr(110) + chr(101) + chr(41)}}\\n  Links to: {{l_str or chr(40) + chr(110) + chr(111) + chr(110) + chr(101) + chr(41)}}")
    return "\\n\\n".join(lines)
'''

SEARCH_VAULT_SRC = f'''\
def search_vault_content(keyword: str, subfolder: str = "") -> str:
    """Search all notes in the Obsidian vault for a keyword or phrase (case-insensitive).
    Returns matching note paths and the lines containing the keyword.
    subfolder: optional path relative to Vault 1 root to narrow the search.
    """
    import pathlib
    vault_root = pathlib.Path(r"{VAULT_ROOT}")
    target = vault_root / subfolder if subfolder else vault_root
    notes = sorted(target.rglob("*.md"))
    results = []
    kw = keyword.lower()
    for note in notes:
        try:
            text = note.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if kw not in text.lower():
            continue
        rel = note.relative_to(vault_root)
        matches = []
        for i, line in enumerate(text.splitlines(), 1):
            if kw in line.lower():
                matches.append(f"  L{{i}}: {{line.strip()[:120]}}")
            if len(matches) >= 5:
                break
        results.append(f"{{rel}}:\\n" + "\\n".join(matches))
    if not results:
        return f"No notes found containing keyword."
    return f"Found in {{len(results)}} note(s):\\n\\n" + "\\n\\n".join(results)
'''

GET_ANY_NOTE_SRC = f'''\
def get_vault_note(relative_path: str) -> str:
    """Read any Markdown note from anywhere in the Obsidian vault (not just Research folder).
    relative_path is relative to Vault 1 root, e.g. "Finance/Banking.md"
    """
    import pathlib
    vault_root = pathlib.Path(r"{VAULT_ROOT}")
    note_path = vault_root / relative_path
    if not note_path.exists():
        return f"Note not found: {{relative_path}}"
    return note_path.read_text(encoding="utf-8", errors="ignore")
'''

WRITE_ANY_NOTE_SRC = f'''\
def write_vault_note(relative_path: str, content: str) -> str:
    """Write or overwrite any Markdown note anywhere in the Obsidian vault.
    Use this to create MOCs or connection notes outside the Research subfolder.
    relative_path is relative to Vault 1 root, e.g. "MOCs/Banking Web.md"
    content is the full Markdown content including any frontmatter.
    """
    import pathlib
    vault_root = pathlib.Path(r"{VAULT_ROOT}")
    note_path = vault_root / relative_path
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(content, encoding="utf-8")
    return f"Saved: {{relative_path}}"
'''

APPEND_ANY_NOTE_SRC = f'''\
def append_to_vault_note(relative_path: str, content: str) -> str:
    """Append content to any existing note anywhere in the Obsidian vault.
    Use this to add [[links]] or new sections to existing notes without overwriting.
    relative_path is relative to Vault 1 root, e.g. "Finance/Banking.md"
    """
    import pathlib
    vault_root = pathlib.Path(r"{VAULT_ROOT}")
    note_path = vault_root / relative_path
    if not note_path.exists():
        return f"Note not found: {{relative_path}}"
    existing = note_path.read_text(encoding="utf-8", errors="ignore")
    note_path.write_text(existing.rstrip() + "\\n\\n" + content.lstrip(), encoding="utf-8")
    return f"Appended to: {{relative_path}}"
'''


# ── Termination conditions ───────────────────────────────────────────────────────
termination = {
    "provider": "autogen_agentchat.base.OrTerminationCondition",
    "component_type": "termination",
    "version": 1,
    "component_version": 1,
    "description": "Terminate on keyword or message limit.",
    "label": "OrTerminationCondition",
    "config": {
        "conditions": [
            {
                "provider": "autogen_agentchat.conditions.TextMentionTermination",
                "component_type": "termination",
                "version": 1,
                "component_version": 1,
                "description": "Terminate when RESEARCH_COMPLETE is mentioned.",
                "label": "TextMentionTermination",
                "config": {"text": "RESEARCH_COMPLETE"}
            },
            {
                "provider": "autogen_agentchat.conditions.MaxMessageTermination",
                "component_type": "termination",
                "version": 1,
                "component_version": 1,
                "description": "Terminate after 60 messages.",
                "label": "MaxMessageTermination",
                "config": {"max_messages": 60, "include_agent_event": False}
            }
        ]
    }
}


# ══════════════════════════════════════════════════════════════════════════════════
# AGENT DEFINITIONS
# ══════════════════════════════════════════════════════════════════════════════════

orchestrator = agent(
    name="ResearchOrchestrator",
    label="ResearchOrchestrator",
    description="Plans research, assigns tasks to specialists, and signals completion.",
    temperature=0.2,
    tools_list=[],
    system_message="""You are the **Research Orchestrator** — the lead coordinator for a research team.

You have two operating modes:

**MODE 1 — Research new topics:**
When given a topic to research:
1. Break it into 3-6 focused sub-topics.
2. Direct WebResearcher, WikiExpert, and ArXivAgent to gather information.
3. Instruct ObsidianWriter to organize findings into notes + a MOC.
4. When all notes are written, say exactly: RESEARCH_COMPLETE

**MODE 2 — Build webs from existing vault:**
When asked to map, link, or web-ify existing Obsidian notes:
1. Instruct ObsidianWriter to scan the vault with scan_vault_structure.
2. Instruct ObsidianWriter to search for related notes with search_vault_content.
3. Instruct ObsidianWriter to create a MOC using write_vault_note that links all relevant existing notes.
4. Instruct ObsidianWriter to append backlinks or See Also sections to the existing notes.
5. When the web is complete, say exactly: RESEARCH_COMPLETE

Keep delegations concise — one clear instruction per message.
Track which sub-topics have been researched and which haven't yet.""",
)

web_researcher = agent(
    name="WebResearcher",
    label="WebResearcher",
    description="Searches the web and reads pages for current information.",
    temperature=0.3,
    tools_list=[
        tool("web_search", "Search the web with DuckDuckGo", WEB_SEARCH_SRC),
        tool("fetch_url", "Fetch and read a web page's text content", FETCH_URL_SRC),
    ],
    system_message="""You are the **Web Researcher** — expert at finding information online.

When given a research task:
1. Use `web_search` to find 5-8 relevant results.
2. Pick the 2-3 most promising URLs and use `fetch_url` to read them.
3. Synthesize: extract key facts, definitions, examples, and important details.
4. Present findings as clear, structured Markdown with source URLs.""",
)

wiki_expert = agent(
    name="WikiExpert",
    label="WikiExpert",
    description="Fetches Wikipedia articles for encyclopedic background knowledge.",
    temperature=0.2,
    tools_list=[
        tool("wikipedia_lookup", "Fetch a Wikipedia article by topic name", WIKIPEDIA_SRC),
    ],
    system_message="""You are the **Wikipedia Expert** — you retrieve authoritative encyclopedic knowledge.

When given a concept or topic:
1. Use `wikipedia_lookup` to fetch the article.
2. Summarize key information: definition, history, key concepts, notable examples.
3. Format output as clean Markdown with ## headings.
4. If the first lookup fails, try an alternative phrasing.
5. Always include the Wikipedia URL as a source.""",
)

arxiv_agent = agent(
    name="ArXivAgent",
    label="ArXivAgent",
    description="Finds academic papers on arXiv for scholarly context.",
    temperature=0.2,
    tools_list=[
        tool("arxiv_search", "Search arXiv for academic papers", ARXIV_SRC),
    ],
    system_message="""You are the **arXiv Research Agent** — specialist in academic literature.

When given a research topic:
1. Use `arxiv_search` with 2-3 targeted queries.
2. Select the 3-5 most relevant papers.
3. For each paper extract: key contribution, methodology, main findings.
4. Format as Markdown with citations (Author, Year, Title [link]).
5. Highlight connections between papers and the main topic.""",
)

obsidian_writer = agent(
    name="ObsidianWriter",
    label="ObsidianWriter",
    description="Writes and edits Obsidian notes, builds MOCs, and creates knowledge webs by linking existing vault notes.",
    temperature=0.4,
    tools_list=[
        # Research subfolder tools
        tool("write_obsidian_note", "Write (create or overwrite) a Markdown note in the Research subfolder", WRITE_NOTE_SRC),
        tool("list_vault_notes", "List existing notes in the Research subfolder", LIST_NOTES_SRC),
        tool("get_note_content", "Read a note from the Research subfolder", GET_NOTE_SRC),
        tool("append_to_note", "Append content to a note in the Research subfolder", APPEND_NOTE_SRC),
        tool("replace_note_section", "Replace a ## section in a Research subfolder note", REPLACE_SECTION_SRC),
        tool("find_replace_in_note", "Find and replace text in a Research subfolder note", FIND_REPLACE_SRC),
        # Full vault tools
        tool("scan_vault_structure", "Scan all notes in the entire vault - returns paths, headings, and links", SCAN_VAULT_SRC),
        tool("search_vault_content", "Search all vault notes for a keyword or phrase", SEARCH_VAULT_SRC),
        tool("get_vault_note", "Read any note from anywhere in the vault", GET_ANY_NOTE_SRC),
        tool("write_vault_note", "Write or overwrite any note anywhere in the vault", WRITE_ANY_NOTE_SRC),
        tool("append_to_vault_note", "Append content to any existing note anywhere in the vault", APPEND_ANY_NOTE_SRC),
    ],
    system_message=f"""You are the **Obsidian Writer** — you create, edit, and interconnect notes in Obsidian.

You have two modes:

## MODE 1: Research → New Notes
When given fresh research to organize, create this structure in the Research subfolder:
```
Research/<Topic>/
  Overview.md
  Web Sources.md
  Wikipedia Notes.md
  Research Papers.md
  Key Concepts.md
Research/MOCs/
  MOC - <Topic>.md
```
Use write_obsidian_note (paths relative to Research folder).

## MODE 2: Vault Web / Linking Existing Notes
When asked to build a web or map from existing vault content:
1. Use `scan_vault_structure` to discover all existing notes (pass subfolder to narrow scope).
2. Use `search_vault_content` to find notes related to specific topics.
3. Use `get_vault_note` to read the full content of relevant notes.
4. Use `write_vault_note` to create a new MOC anywhere in the vault (e.g. "MOCs/Banking Web.md").
5. Use `append_to_vault_note` to add [[backlinks]] or a See Also section to existing notes.

Obsidian Markdown rules:
- Use [[Exact Note Title]] for wiki-links (title only, no path, no .md extension).
- Use #tag inline and in YAML frontmatter tags list.
- Use ## and ### headings generously.
- Use > blockquotes for key insights.
- End every MOC with a ## Sources and ## Open Questions section.

MOC format:
```
---
tags:
  - moc
  - <topic>
created: YYYY-MM-DD
---
# MOC - <Topic>

## Overview
<1-2 sentence summary>

## Notes in this Web
- [[Note A]] — description
- [[Note B]] — description

## Key Concepts
- ...

## Open Questions
- [ ] ...

## Sources
- ...
```

Vault root: {VAULT_ROOT}
Research folder: {VAULT}

Always read notes before editing them. Report every file created or modified.""",
)

# ══════════════════════════════════════════════════════════════════════════════════
# TEAM (SelectorGroupChat)
# ══════════════════════════════════════════════════════════════════════════════════

SELECTOR_PROMPT = """\
You are coordinating a research team. Select the next agent based on what is needed:
- ResearchOrchestrator: planning, coordination, deciding next steps, assigning sub-topics
- WebResearcher: searching the web for current info, reading web pages
- WikiExpert: getting encyclopedic/foundational knowledge from Wikipedia
- ArXivAgent: finding academic papers on arXiv
- ObsidianWriter: writing new notes, editing existing notes, scanning the vault, building knowledge webs and MOCs that link existing notes together

Current conversation:
{history}

Next agent to act (name only):"""

team_component = {
    "provider": "autogen_agentchat.teams.SelectorGroupChat",
    "component_type": "team",
    "version": 1,
    "component_version": 1,
    "description": "A research team that finds information and writes organized notes to Obsidian.",
    "label": "Research Team → Obsidian",
    "config": {
        "participants": [orchestrator, web_researcher, wiki_expert, arxiv_agent, obsidian_writer],
        "model_client": model_client(0.1),
        "termination_condition": termination,
        "selector_prompt": SELECTOR_PROMPT,
        "allow_repeated_speaker": True,
        "max_selector_attempts": 5,
        "emit_team_events": False,
    }
}


# ══════════════════════════════════════════════════════════════════════════════════
# INSERT INTO DATABASE
# ══════════════════════════════════════════════════════════════════════════════════

def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    now = datetime.utcnow().isoformat()

    # Check if already exists
    cur.execute("SELECT id FROM team WHERE user_id=? AND json_extract(component,'$.label')=?",
                (USER_ID, "Research Team → Obsidian"))
    existing = cur.fetchone()

    component_json = json.dumps(team_component, ensure_ascii=False)

    if existing:
        team_id = existing[0]
        cur.execute(
            "UPDATE team SET component=?, updated_at=?, version=? WHERE id=?",
            (component_json, now, "0.0.1", team_id)
        )
        print(f"✅ Updated existing Research Team (id={team_id}) in AutoGen Studio.")
    else:
        cur.execute(
            "INSERT INTO team (created_at, updated_at, user_id, version, component) VALUES (?,?,?,?,?)",
            (now, now, USER_ID, "0.0.1", component_json)
        )
        team_id = cur.lastrowid
        print(f"✅ Registered Research Team (id={team_id}) in AutoGen Studio.")

    conn.commit()
    conn.close()
    print("\nRefresh your AutoGen Studio UI (localhost:8080) → Build → Teams")
    print("Look for: 'Research Team → Obsidian'")

if __name__ == "__main__":
    main()
