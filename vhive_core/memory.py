"""
AURA 3-Layer Memory System (PARA-inspired).

Layer 1 — Knowledge Graph (Facts): ~/.vhive/memory/knowledge/{projects,areas,resources,archives}/
Layer 2 — Daily Notes (Active State): ~/.vhive/memory/daily/YYYY-MM-DD.md
Layer 3 — Tacit Knowledge (Patterns): ~/.vhive/memory/tacit/{preferences,patterns,rules}.md

All files are plain markdown — human-readable, editable, git-friendly.
"""

from datetime import date, timedelta
from pathlib import Path


VHIVE_HOME = Path.home() / ".vhive"
MEMORY_ROOT = VHIVE_HOME / "memory"

# Layer 1 sub-directories (PARA)
KNOWLEDGE_DIR = MEMORY_ROOT / "knowledge"
KNOWLEDGE_SUBDIRS = ["projects", "areas", "resources", "archives"]

# Layer 2
DAILY_DIR = MEMORY_ROOT / "daily"

# Layer 3
TACIT_DIR = MEMORY_ROOT / "tacit"
TACIT_FILES = {
    "preferences": "preferences.md",
    "patterns": "patterns.md",
    "rules": "rules.md",
}


class AuraMemory:
    """Manages AURA's 3-layer markdown memory filesystem."""

    def __init__(self, root: Path | None = None):
        self.root = root or MEMORY_ROOT
        self.knowledge = self.root / "knowledge"
        self.daily = self.root / "daily"
        self.tacit = self.root / "tacit"

    # ── Bootstrap ──────────────────────────────────────────────

    def init_memory(self) -> None:
        """Create the full directory structure and seed tacit files if missing."""
        for subdir in KNOWLEDGE_SUBDIRS:
            (self.knowledge / subdir).mkdir(parents=True, exist_ok=True)
        self.daily.mkdir(parents=True, exist_ok=True)
        self.tacit.mkdir(parents=True, exist_ok=True)

        # Seed tacit files with defaults if they don't exist
        defaults = {
            "preferences.md": (
                "# AURA Preferences\n\n"
                "- Brand voice: professional, concise, data-driven\n"
                "- Target sites: viperbyproof.com, complybyproof.com, itsvoco.com\n"
            ),
            "patterns.md": (
                "# Learned Patterns\n\n"
                "<!-- AURA appends observations here after analysing results -->\n"
            ),
            "rules.md": (
                "# Hard Rules\n\n"
                "- Never DM the same person twice in 24 hours\n"
                "- Max 50 outreach messages per run\n"
                "- Always validate code in sandbox before deploying\n"
            ),
        }
        for filename, content in defaults.items():
            path = self.tacit / filename
            if not path.exists():
                path.write_text(content)

    # ── Layer 1: Knowledge Graph ───────────────────────────────

    def read_knowledge(self, category: str, topic: str) -> str:
        """Read a knowledge file. Returns empty string if not found."""
        path = self.knowledge / category / f"{topic}.md"
        if path.exists():
            return path.read_text()
        return ""

    def update_knowledge(self, category: str, topic: str, content: str) -> None:
        """Append content to a knowledge file (creates if missing)."""
        dirpath = self.knowledge / category
        dirpath.mkdir(parents=True, exist_ok=True)
        path = dirpath / f"{topic}.md"
        if path.exists():
            existing = path.read_text()
            path.write_text(existing.rstrip() + "\n\n" + content + "\n")
        else:
            path.write_text(f"# {topic}\n\n{content}\n")

    def list_knowledge(self, category: str) -> list[str]:
        """List topic names in a knowledge category."""
        dirpath = self.knowledge / category
        if not dirpath.exists():
            return []
        return sorted(p.stem for p in dirpath.glob("*.md"))

    # ── Layer 2: Daily Notes ───────────────────────────────────

    def write_daily_note(self, content: str, day: date | None = None) -> None:
        """Append a section to today's daily note."""
        day = day or date.today()
        path = self.daily / f"{day.isoformat()}.md"
        if path.exists():
            existing = path.read_text()
            path.write_text(existing.rstrip() + "\n\n---\n\n" + content + "\n")
        else:
            path.write_text(f"# Daily Note — {day.isoformat()}\n\n{content}\n")

    def read_recent_context(self, days: int = 3) -> str:
        """Read the last N days of daily notes as a single context string."""
        today = date.today()
        parts: list[str] = []
        for i in range(days):
            day = today - timedelta(days=i)
            path = self.daily / f"{day.isoformat()}.md"
            if path.exists():
                parts.append(path.read_text())
        return "\n\n".join(parts) if parts else ""

    # ── Layer 3: Tacit Knowledge ───────────────────────────────

    def read_tacit(self, name: str) -> str:
        """Read a tacit knowledge file (preferences, patterns, or rules)."""
        filename = TACIT_FILES.get(name, f"{name}.md")
        path = self.tacit / filename
        if path.exists():
            return path.read_text()
        return ""

    def update_tacit(self, name: str, content: str) -> None:
        """Append to a tacit knowledge file."""
        filename = TACIT_FILES.get(name, f"{name}.md")
        path = self.tacit / filename
        if path.exists():
            existing = path.read_text()
            path.write_text(existing.rstrip() + "\n\n" + content + "\n")
        else:
            path.write_text(f"# {name.title()}\n\n{content}\n")

    # ── Cross-layer search ─────────────────────────────────────

    def search_memory(self, query: str) -> list[dict]:
        """Simple keyword search across all markdown files. Returns matches with file path and snippet."""
        query_lower = query.lower()
        results: list[dict] = []
        for md_file in self.root.rglob("*.md"):
            try:
                text = md_file.read_text()
            except OSError:
                continue
            lines = text.splitlines()
            for i, line in enumerate(lines):
                if query_lower in line.lower():
                    # Relative path from memory root
                    rel = md_file.relative_to(self.root)
                    results.append({
                        "file": str(rel),
                        "line": i + 1,
                        "snippet": line.strip()[:200],
                    })
        return results

    # ── Generic file access (for API) ──────────────────────────

    def read_file(self, layer: str, filepath: str) -> str | None:
        """Read any memory file by layer and relative path. Returns None if not found."""
        layer_dir = {"knowledge": self.knowledge, "daily": self.daily, "tacit": self.tacit}.get(layer)
        if not layer_dir:
            return None
        path = layer_dir / filepath
        # Prevent path traversal
        try:
            path.resolve().relative_to(layer_dir.resolve())
        except ValueError:
            return None
        if path.exists() and path.is_file():
            return path.read_text()
        return None

    def write_file(self, layer: str, filepath: str, content: str) -> bool:
        """Write/overwrite a memory file by layer and relative path."""
        layer_dir = {"knowledge": self.knowledge, "daily": self.daily, "tacit": self.tacit}.get(layer)
        if not layer_dir:
            return False
        path = layer_dir / filepath
        # Prevent path traversal
        try:
            path.resolve().relative_to(layer_dir.resolve())
        except ValueError:
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return True

    def list_files(self, layer: str, subdir: str = "") -> list[str]:
        """List files in a memory layer (optionally within a subdirectory)."""
        layer_dir = {"knowledge": self.knowledge, "daily": self.daily, "tacit": self.tacit}.get(layer)
        if not layer_dir:
            return []
        target = layer_dir / subdir if subdir else layer_dir
        # Prevent path traversal
        try:
            target.resolve().relative_to(layer_dir.resolve())
        except ValueError:
            return []
        if not target.exists():
            return []
        return sorted(str(p.relative_to(layer_dir)) for p in target.rglob("*.md"))


# Global singleton
memory = AuraMemory()
