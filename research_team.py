"""
AutoGen Research Team → Obsidian
====================================================
A team of Claude-powered agents that:
  1. Search the web (DuckDuckGo), Wikipedia, and arXiv
  2. Scrape and read web pages
  3. Synthesize findings into structured Obsidian notes
     with a Map of Content (MOC) linking everything together.

Usage:
  python research_team.py "Transformer architecture in deep learning"
  python research_team.py  (interactive prompt mode)

Config:
  Set ANTHROPIC_API_KEY in environment or in research_config.py
"""

import asyncio
import os
import re
import sys
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Try importing local config (API keys etc.) ─────────────────────────────────
try:
    import research_config as cfg
    ANTHROPIC_API_KEY = getattr(cfg, "ANTHROPIC_API_KEY", os.environ.get("ANTHROPIC_API_KEY", ""))
    VAULT_PATH = Path(getattr(cfg, "OBSIDIAN_VAULT", r"C:\Users\info\OneDrive\Documents\Obsidian Vault\Vault 1\Research"))
    CLAUDE_MODEL = getattr(cfg, "CLAUDE_MODEL", "claude-sonnet-4-5-20251001")
except ImportError:
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    VAULT_PATH = Path(r"C:\Users\info\OneDrive\Documents\Obsidian Vault\Vault 1\Research")
    CLAUDE_MODEL = "claude-sonnet-4-5-20251001"

if not ANTHROPIC_API_KEY:
    print("❌  ANTHROPIC_API_KEY not set. Add it to research_config.py or as an env variable.")
    sys.exit(1)

# ── AutoGen imports ─────────────────────────────────────────────────────────────
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import MaxMessageTermination, TextMentionTermination
from autogen_agentchat.teams import SelectorGroupChat
from autogen_agentchat.ui import Console
from autogen_ext.models.anthropic import AnthropicChatCompletionClient

# ── Research tool imports ───────────────────────────────────────────────────────
import requests
import wikipediaapi
import arxiv
from bs4 import BeautifulSoup
try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS


# ══════════════════════════════════════════════════════════════════════════════════
# TOOL FUNCTIONS  (plain Python – agents call these via function calling)
# ══════════════════════════════════════════════════════════════════════════════════

def web_search(query: str, max_results: int = 8) -> str:
    """Search the web with DuckDuckGo. Returns titles, URLs, and snippets."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        if not results:
            return "No search results found for this query."
        lines = []
        for i, r in enumerate(results, 1):
            snippet = r.get("body", "")[:300]
            lines.append(f"{i}. **{r['title']}**\n   URL: {r['href']}\n   {snippet}")
        return "\n\n".join(lines)
    except Exception as e:
        return f"Search error: {e}"


def fetch_url(url: str) -> str:
    """Fetch a web page and return its readable text content (max ~5000 chars)."""
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            )
        }
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        # Remove noise tags
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        # Collapse blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text[:5000] + ("\n\n[...content truncated...]" if len(text) > 5000 else "")
    except Exception as e:
        return f"Error fetching {url}: {e}"


def wikipedia_lookup(topic: str) -> str:
    """Fetch a Wikipedia article with summary and key sections."""
    try:
        wiki = wikipediaapi.Wikipedia(
            user_agent="AutoGenResearchBot/1.0 (autogen-team)", language="en"
        )
        page = wiki.page(topic)
        if not page.exists():
            return (
                f"No Wikipedia page found for '{topic}'. "
                "Try a slightly different title (e.g. more/less specific)."
            )
        # Pull up to 6 sections
        section_texts = []
        for s in page.sections[:6]:
            if s.text.strip():
                section_texts.append(f"### {s.title}\n{s.text[:700]}")
        body = "\n\n".join(section_texts)
        return (
            f"# {page.title}\n\n"
            f"**Summary:** {page.summary[:1200]}\n\n"
            f"{body}\n\n"
            f"**Wikipedia URL:** {page.fullurl}"
        )
    except Exception as e:
        return f"Wikipedia error: {e}"


def arxiv_search(query: str, max_results: int = 5) -> str:
    """Search arXiv for academic papers. Returns titles, authors, abstracts, and links."""
    try:
        client = arxiv.Client()
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.Relevance,
        )
        results = list(client.results(search))
        if not results:
            return "No arXiv papers found for this query."
        lines = []
        for p in results:
            authors = ", ".join(a.name for a in p.authors[:4])
            pub_date = p.published.strftime("%Y-%m-%d") if p.published else "unknown"
            abstract = p.summary[:500].replace("\n", " ")
            lines.append(
                f"**{p.title}**\n"
                f"Authors: {authors}\n"
                f"Published: {pub_date}\n"
                f"URL: {p.entry_id}\n"
                f"Abstract: {abstract}..."
            )
        return "\n\n---\n\n".join(lines)
    except Exception as e:
        return f"arXiv search error: {e}"


def write_obsidian_note(
    relative_path: str,
    content: str,
    tags: Optional[list] = None,
) -> str:
    """
    Write a Markdown note to the Obsidian vault.

    Args:
        relative_path: Path relative to the Research folder, e.g. "AI/Overview.md"
        content:       Full Markdown body (do NOT include frontmatter – it's added automatically).
        tags:          List of tag strings (no #), e.g. ["AI", "research", "2025"]
    """
    tags = tags or []
    note_path = VAULT_PATH / relative_path
    note_path.parent.mkdir(parents=True, exist_ok=True)

    tag_lines = "\n".join(f"  - {t}" for t in tags) if tags else "  - research"
    created = datetime.now().strftime("%Y-%m-%d")
    frontmatter = (
        f"---\n"
        f"created: {created}\n"
        f"tags:\n{tag_lines}\n"
        f"---\n\n"
    )
    full_content = frontmatter + content.lstrip()
    note_path.write_text(full_content, encoding="utf-8")
    return f"✅ Note saved: {note_path.relative_to(VAULT_PATH.parent)}"


def list_vault_notes(subfolder: str = "") -> str:
    """List existing Markdown notes in the Research vault (or a subfolder)."""
    target = VAULT_PATH / subfolder if subfolder else VAULT_PATH
    if not target.exists():
        return f"Folder does not exist yet: {target}"
    notes = sorted(target.rglob("*.md"))
    if not notes:
        return "No notes yet."
    return "\n".join(str(n.relative_to(VAULT_PATH)) for n in notes)


def get_note_content(relative_path: str) -> str:
    """Read an existing Obsidian note from the vault."""
    note_path = VAULT_PATH / relative_path
    if not note_path.exists():
        return f"Note not found: {relative_path}"
    return note_path.read_text(encoding="utf-8")


def append_to_note(relative_path: str, content: str) -> str:
    """Append content to the end of an existing Obsidian note. Creates the note if it does not exist."""
    note_path = VAULT_PATH / relative_path
    if not note_path.exists():
        return f"Note not found: {relative_path}. Use write_obsidian_note to create it first."
    existing = note_path.read_text(encoding="utf-8")
    note_path.write_text(existing.rstrip() + "\n\n" + content.lstrip(), encoding="utf-8")
    return f"✅ Appended to: {relative_path}"


def replace_note_section(relative_path: str, section_heading: str, new_content: str) -> str:
    """Replace the content of a specific ## heading section in an existing Obsidian note.
    section_heading: exact heading text without the ## prefix.
    new_content: replacement body for that section (heading line is preserved).
    If the section is not found it is appended as a new section.
    """
    note_path = VAULT_PATH / relative_path
    if not note_path.exists():
        return f"Note not found: {relative_path}"
    text = note_path.read_text(encoding="utf-8")
    pattern = rf"(#+\s{re.escape(section_heading)}\n)(.*?)(?=\n#+ |\Z)"
    replacement = f"## {section_heading}\n{new_content.strip()}\n"
    new_text, count = re.subn(pattern, replacement, text, flags=re.DOTALL)
    if count == 0:
        new_text = text.rstrip() + f"\n\n## {section_heading}\n{new_content.strip()}\n"
        note_path.write_text(new_text, encoding="utf-8")
        return f"✅ Section '{section_heading}' not found — appended as new section in {relative_path}"
    note_path.write_text(new_text, encoding="utf-8")
    return f"✅ Replaced section '{section_heading}' in {relative_path}"


def find_replace_in_note(relative_path: str, find_text: str, replace_text: str) -> str:
    """Find and replace an exact string inside an existing Obsidian note."""
    note_path = VAULT_PATH / relative_path
    if not note_path.exists():
        return f"Note not found: {relative_path}"
    text = note_path.read_text(encoding="utf-8")
    if find_text not in text:
        return f"Text not found in {relative_path}: {repr(find_text[:80])}"
    count = text.count(find_text)
    note_path.write_text(text.replace(find_text, replace_text), encoding="utf-8")
    return f"✅ Replaced {count} occurrence(s) in {relative_path}"


# ══════════════════════════════════════════════════════════════════════════════════
# AGENT DEFINITIONS
# ══════════════════════════════════════════════════════════════════════════════════

from autogen_core.models import ModelInfo, ModelFamily

_MODEL_INFO_OVERRIDE = ModelInfo(
    vision=True,
    function_calling=True,
    json_output=True,
    family=ModelFamily.UNKNOWN,
    structured_output=False,
    multiple_system_messages=False,
)

def build_model(temperature: float = 0.3) -> AnthropicChatCompletionClient:
    return AnthropicChatCompletionClient(
        model=CLAUDE_MODEL,
        api_key=ANTHROPIC_API_KEY,
        temperature=temperature,
        model_info=_MODEL_INFO_OVERRIDE,
    )


def make_orchestrator() -> AssistantAgent:
    return AssistantAgent(
        name="ResearchOrchestrator",
        model_client=build_model(0.2),
        description=(
            "The lead coordinator. Receives the research topic, creates a structured "
            "research plan with subtopics and questions, delegates work to specialist "
            "agents, and signals DONE when all notes are written."
        ),
        system_message=textwrap.dedent("""
            You are the **Research Orchestrator** — the lead coordinator for a research team.

            When given a topic:
            1. Break it into 3-6 focused sub-topics or research questions.
            2. Direct the WebResearcher, WikiExpert, and ArXivAgent to gather information
               on each sub-topic.
            3. Once research is gathered, instruct the ObsidianWriter to organize it into
               notes with a Map of Content (MOC).
            4. When all notes are written and the MOC is complete, say exactly: RESEARCH_COMPLETE

            Keep delegations concise — one clear instruction per message.
            Track which sub-topics have been researched and which haven't yet.
        """).strip(),
    )


def make_web_researcher() -> AssistantAgent:
    return AssistantAgent(
        name="WebResearcher",
        model_client=build_model(0.3),
        tools=[web_search, fetch_url],
        description=(
            "Searches the web using DuckDuckGo and reads web pages. "
            "Use for current information, news, tutorials, and general resources."
        ),
        system_message=textwrap.dedent("""
            You are the **Web Researcher** — expert at finding information online.

            When given a research task:
            1. Use `web_search` to find 5-8 relevant results.
            2. Pick the 2-3 most promising URLs and use `fetch_url` to read them.
            3. Synthesize: extract key facts, definitions, examples, and important details.
            4. Present your findings as clear, structured Markdown that the ObsidianWriter
               can use directly. Include source URLs.

            Be thorough but focused — quality over quantity.
        """).strip(),
    )


def make_wiki_expert() -> AssistantAgent:
    return AssistantAgent(
        name="WikiExpert",
        model_client=build_model(0.2),
        tools=[wikipedia_lookup],
        description=(
            "Fetches and summarizes Wikipedia articles. "
            "Use for foundational concepts, definitions, and encyclopedic overviews."
        ),
        system_message=textwrap.dedent("""
            You are the **Wikipedia Expert** — you retrieve authoritative encyclopedic knowledge.

            When given a concept or topic:
            1. Use `wikipedia_lookup` to fetch the article.
            2. Summarize the key information: definition, history, key concepts, notable examples.
            3. Format your output as clean Markdown with ## headings.
            4. If the first lookup fails, try an alternative phrasing.
            5. Always include the Wikipedia URL as a source.
        """).strip(),
    )


def make_arxiv_agent() -> AssistantAgent:
    return AssistantAgent(
        name="ArXivAgent",
        model_client=build_model(0.2),
        tools=[arxiv_search],
        description=(
            "Finds academic papers on arXiv. "
            "Use for cutting-edge research, technical details, and scholarly context."
        ),
        system_message=textwrap.dedent("""
            You are the **arXiv Research Agent** — specialist in academic literature.

            When given a research topic:
            1. Use `arxiv_search` with 2-3 targeted queries.
            2. Select the 3-5 most relevant papers.
            3. For each paper, extract: key contribution, methodology, main findings.
            4. Format as Markdown with proper citations (Author, Year, Title [link]).
            5. Highlight connections between papers and the main topic.
        """).strip(),
    )


def make_obsidian_writer() -> AssistantAgent:
    return AssistantAgent(
        name="ObsidianWriter",
        model_client=build_model(0.4),
        tools=[write_obsidian_note, list_vault_notes, get_note_content,
               append_to_note, replace_note_section, find_replace_in_note],
        description=(
            "Creates and writes well-structured Obsidian Markdown notes with "
            "[[wiki-links]], tags, and a Map of Content (MOC). "
            "Call when research findings need to be organized into the vault."
        ),
        system_message=textwrap.dedent("""
            You are the **Obsidian Writer** — you turn raw research into beautiful,
            interconnected Obsidian Markdown notes.

            Structure every research session as:
            ```
            Research/
              MOCs/
                MOC - <Topic>.md          ← Map of Content linking everything
              <Topic>/
                Overview.md               ← High-level synthesis
                Web Sources.md            ← Findings from web research
                Wikipedia Notes.md        ← Encyclopedic knowledge
                Research Papers.md        ← Academic sources
                Key Concepts.md           ← Definitions and terminology
            ```

            Obsidian Markdown rules:
            - Use [[Note Title]] for internal links between notes.
            - Use #tag for inline tags (also add them to frontmatter).
            - Use ## and ### headings generously for structure.
            - Use > blockquotes for important quotes or key insights.
            - Use - [ ] for action items or open questions.
            - End every note with a ## Sources section.

            The MOC must:
            - Link to ALL created notes using [[...]] 
            - Have a brief description of each linked note.
            - Include a "Key Questions" and "Key Concepts" section.
            - Be saved as: MOCs/MOC - <Topic>.md

            Call `write_obsidian_note` for each file. Use the topic as part of
            the folder name (sanitize: no special chars, use Title Case).
            Add relevant tags like the topic name, "research", current year.

            IMPORTANT: Write ALL notes (Overview, Web Sources, Wikipedia Notes,
            Research Papers, Key Concepts, and MOC) before declaring done.

            Editing existing notes:
            - Use `get_note_content` first to read a note before editing it.
            - Use `append_to_note` to add new sections without overwriting.
            - Use `replace_note_section` to update a specific ## section by heading name.
            - Use `find_replace_in_note` for targeted text fixes (links, dates, names).
            - Use `write_obsidian_note` only when creating or fully rewriting a note.
        """).strip(),
    )


# ══════════════════════════════════════════════════════════════════════════════════
# TEAM ASSEMBLY & RUNNER
# ══════════════════════════════════════════════════════════════════════════════════

async def run_research(topic: str) -> None:
    print(f"\n🔬 Starting research on: {topic}")
    print(f"📁 Vault path: {VAULT_PATH}\n")

    orchestrator   = make_orchestrator()
    web_researcher = make_web_researcher()
    wiki_expert    = make_wiki_expert()
    arxiv_agent    = make_arxiv_agent()
    writer         = make_obsidian_writer()

    # Termination: stop when orchestrator says RESEARCH_COMPLETE or after 60 messages
    termination = (
        TextMentionTermination("RESEARCH_COMPLETE") |
        MaxMessageTermination(60)
    )

    team = SelectorGroupChat(
        participants=[orchestrator, web_researcher, wiki_expert, arxiv_agent, writer],
        model_client=build_model(0.1),   # Selector model (fast, cold)
        termination_condition=termination,
        selector_prompt=(
            "You are coordinating a research team. Select the next agent based on "
            "what's needed:\n"
            "- ResearchOrchestrator: planning, coordination, deciding next steps\n"
            "- WebResearcher: searching the web for current info\n"
            "- WikiExpert: getting encyclopedic/foundational knowledge\n"
            "- ArXivAgent: finding academic papers\n"
            "- ObsidianWriter: writing and organizing notes into the vault\n\n"
            "Current conversation:\n{history}\n\n"
            "Next agent to act (name only):"
        ),
    )

    task = (
        f"Research the following topic comprehensively: **{topic}**\n\n"
        f"Research date: {datetime.now().strftime('%Y-%m-%d')}\n\n"
        "Steps:\n"
        "1. Plan the research (identify 4-5 sub-topics to investigate).\n"
        "2. Gather web research, Wikipedia knowledge, and academic papers.\n"
        "3. Have the ObsidianWriter create all notes and the MOC.\n"
        "4. Say RESEARCH_COMPLETE when everything is saved to the vault."
    )

    await Console(team.run_stream(task=task))
    print(f"\n✅ Research complete! Check your vault at:\n   {VAULT_PATH}")


# ══════════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) > 1:
        topic = " ".join(sys.argv[1:])
    else:
        topic = input("📚 Enter research topic: ").strip()
        if not topic:
            print("No topic provided. Exiting.")
            sys.exit(0)

    asyncio.run(run_research(topic))
