"""
Amethyst OKF Engine - Google Open Knowledge Format
==================================================
Provides structured, cross-linked knowledge graph management,
local markdown wiki parsing, agentic graph traversal, and memory auto-compilation.
Zero GPU VRAM usage — operates entirely in lightweight CPU memory.
"""

import os
import re
import time
import zipfile
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import yaml

log = logging.getLogger("amethyst.okf")

# Storage for OKF Knowledge Bundles
if "AMETHYST_HOME" in os.environ:
    KNOWLEDGE_DIR = Path(os.environ["AMETHYST_HOME"]) / "knowledge"
else:
    KNOWLEDGE_DIR = Path.home() / ".amethyst" / "knowledge"

KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class OKFNode:
    """Represents a single node in Google's Open Knowledge Format (OKF)."""
    id: str
    title: str
    type: str  # project, concept, reference, profile, session, guide
    tags: List[str] = field(default_factory=list)
    summary: str = ""
    related: List[str] = field(default_factory=list)
    content: str = ""
    file_path: Optional[Path] = None
    created: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)
    inline_links: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "type": self.type,
            "tags": self.tags,
            "summary": self.summary,
            "related": self.related,
            "inline_links": self.inline_links,
            "file_name": self.file_path.name if self.file_path else "",
            "content_preview": self.content[:200] + ("..." if len(self.content) > 200 else ""),
            "updated": self.updated
        }


class OKFEngine:
    """
    Google Open Knowledge Format (OKF) Engine.
    Provides structured, cross-linked knowledge graph management,
    local markdown wiki parsing, agentic graph traversal, and auto-compilation.
    Zero GPU VRAM usage — operates entirely in lightweight CPU memory.
    """

    def __init__(self, knowledge_dir: Path = KNOWLEDGE_DIR):
        self.knowledge_dir = knowledge_dir
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        self.nodes: Dict[str, OKFNode] = {}
        self.graph: Dict[str, Set[str]] = {}  # Adjacency list: node_id -> set of connected node_ids
        self._last_loaded = 0.0

    def load_all_bundles(self) -> int:
        """Scan knowledge directory and index all OKF markdown files."""
        self.nodes.clear()
        self.graph.clear()
        
        md_files = list(self.knowledge_dir.rglob("*.md"))
        for file_path in md_files:
            node = self.parse_file(file_path)
            if node:
                self.nodes[node.id] = node

        # Build bidirectional semantic graph edges
        for node_id, node in self.nodes.items():
            if node_id not in self.graph:
                self.graph[node_id] = set()
            
            # Explicit related list in YAML frontmatter
            for rel in node.related:
                if rel in self.nodes:
                    self.graph[node_id].add(rel)
                    if rel not in self.graph:
                        self.graph[rel] = set()
                    self.graph[rel].add(node_id)
            
            # Inline cross-links in markdown
            for link in node.inline_links:
                target_id = self._resolve_link_target(link)
                if target_id and target_id in self.nodes:
                    self.graph[node_id].add(target_id)
                    if target_id not in self.graph:
                        self.graph[target_id] = set()
                    self.graph[target_id].add(node_id)

        self._last_loaded = time.time()
        log.info(f"OKF Knowledge Graph indexed: {len(self.nodes)} nodes, {sum(len(v) for v in self.graph.values()) // 2} cross-links.")
        return len(self.nodes)

    def parse_file(self, file_path: Path) -> Optional[OKFNode]:
        """Parse an OKF Markdown file with YAML frontmatter."""
        try:
            text = file_path.read_text(encoding="utf-8")
        except Exception as e:
            log.warning(f"Could not read {file_path}: {e}")
            return None

        # Check for YAML frontmatter between --- and ---
        frontmatter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
        if not frontmatter_match:
            # Markdown file without frontmatter — create default metadata
            meta = {}
            body = text
        else:
            raw_meta, body = frontmatter_match.groups()
            try:
                meta = yaml.safe_load(raw_meta) or {}
            except Exception as e:
                log.warning(f"YAML parsing error in {file_path}: {e}")
                meta = {}

        node_id = str(meta.get("id") or file_path.stem.lower().replace(" ", "-"))
        title = meta.get("title") or file_path.stem.replace("_", " ").title()
        node_type = meta.get("type", "concept")
        tags = [str(t).lower() for t in meta.get("tags", [])]
        summary = meta.get("summary", "")
        related = [str(r) for r in meta.get("related", [])]

        # Extract inline Markdown links: [Title](link.md)
        inline_links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", body)
        extracted_links = [target for _, target in inline_links if not target.startswith("http")]

        return OKFNode(
            id=node_id,
            title=title,
            type=node_type,
            tags=tags,
            summary=summary,
            related=related,
            content=body.strip(),
            file_path=file_path,
            created=float(meta.get("created", file_path.stat().st_ctime)),
            updated=float(meta.get("updated", file_path.stat().st_mtime)),
            inline_links=extracted_links
        )

    def _resolve_link_target(self, link: str) -> Optional[str]:
        """Map a markdown relative file path to a node id."""
        stem = Path(link).stem.lower().replace(" ", "-")
        if stem in self.nodes:
            return stem
        for n_id in self.nodes:
            if n_id.endswith(stem) or stem in n_id:
                return n_id
        return None

    def query(self, query_text: str, max_nodes: int = 4, max_depth: int = 1) -> str:
        """
        Search the OKF graph, traverse connected related nodes, and
        return a structured, LLM-ready context block.
        """
        if not self.nodes:
            self.load_all_bundles()
        if not self.nodes:
            return ""

        query_tokens = set(re.findall(r"\w+", query_text.lower()))
        if not query_tokens:
            return ""

        # Score nodes based on ID, title, tags, summary, and content
        scored_nodes: List[Tuple[float, str]] = []
        for node_id, node in self.nodes.items():
            score = 0.0
            
            # Exact or partial ID / Title match
            title_tokens = set(re.findall(r"\w+", node.title.lower()))
            overlap = query_tokens.intersection(title_tokens)
            score += len(overlap) * 5.0

            # Tags match
            tag_overlap = query_tokens.intersection(set(node.tags))
            score += len(tag_overlap) * 4.0

            # Summary overlap
            summary_tokens = set(re.findall(r"\w+", node.summary.lower()))
            score += len(query_tokens.intersection(summary_tokens)) * 2.0

            # Body overlap
            content_lower = node.content.lower()
            for token in query_tokens:
                if len(token) > 2 and token in content_lower:
                    score += 0.5

            if score > 0:
                scored_nodes.append((score, node_id))

        if not scored_nodes:
            return ""

        scored_nodes.sort(key=lambda x: x[0], reverse=True)
        top_seed_ids = [nid for _, nid in scored_nodes[:2]]

        # Graph Traversal: Expand context to connected nodes up to max_depth hops
        collected_ids: Set[str] = set(top_seed_ids)
        current_layer = set(top_seed_ids)

        for _ in range(max_depth):
            next_layer = set()
            for nid in current_layer:
                neighbors = self.graph.get(nid, set())
                for neighbor in neighbors:
                    if neighbor not in collected_ids and len(collected_ids) < max_nodes:
                        collected_ids.add(neighbor)
                        next_layer.add(neighbor)
            current_layer = next_layer

        # Build OKF Structured Context Output
        context_parts = []
        for nid in collected_ids:
            node = self.nodes.get(nid)
            if not node:
                continue
            related_titles = [self.nodes[r].title for r in self.graph.get(nid, set()) if r in self.nodes]
            meta_header = f"### [{node.type.upper()}] {node.title}"
            if node.summary:
                meta_header += f"\n*Summary:* {node.summary}"
            if related_titles:
                meta_header += f"\n*Connected Topics:* {', '.join(related_titles[:5])}"

            # Limit body length per node to avoid prompt bloat
            content_snippet = node.content
            if len(content_snippet) > 1000:
                content_snippet = content_snippet[:1000] + "\n...(continues)"

            context_parts.append(f"{meta_header}\n\n{content_snippet}")

        return "\n\n---\n\n".join(context_parts)

    def compile_profile_and_sessions(self, memory_manager) -> int:
        """
        Auto-compile Amethyst long-term memory (user profile facts, preferences,
        and past session summaries) into structured Google OKF Markdown files.
        """
        count = 0
        profile_dir = self.knowledge_dir / "profile"
        sessions_dir = self.knowledge_dir / "sessions"
        profile_dir.mkdir(parents=True, exist_ok=True)
        sessions_dir.mkdir(parents=True, exist_ok=True)

        profile = getattr(memory_manager, 'profile', getattr(memory_manager, '_profile', None))

        # 1. Compile User Profile Card
        profile_md = f"""---
id: user-profile
title: User Profile & Preferences
type: profile
tags: [profile, user, preferences, facts, environment]
summary: Consolidated facts, technical preferences, and active projects of the user.
related: []
created: {time.time()}
updated: {time.time()}
---
# User Profile & Operating Facts

## Known Facts
"""
        for fact in profile.facts:
            profile_md += f"- {fact}\n"
        if not profile.facts:
            profile_md += "- No facts recorded yet.\n"

        profile_md += "\n## Preferences\n"
        for pref in profile.preferences:
            profile_md += f"- {pref}\n"
        if not profile.preferences:
            profile_md += "- Default preferences active.\n"

        profile_md += "\n## Active Projects & Topics\n"
        for proj in profile.projects:
            profile_md += f"- {proj}\n"
        for top in profile.topics:
            profile_md += f"- Topic: {top}\n"

        (profile_dir / "user_profile.md").write_text(profile_md, encoding="utf-8")
        count += 1

        # 2. Compile Summarized Sessions
        stored_sessions = memory_manager._store.list_sessions()
        for s in stored_sessions:
            if s.summarized and s.summary:
                sess_id = f"session-{s.id[:8]}"
                sess_md = f"""---
id: {sess_id}
title: "Session: {s.title}"
type: session
tags: [session, history, summary]
summary: "Conversation summary for {s.title}"
related: [user-profile]
created: {s.created}
updated: {s.updated}
---
# Session Summary: {s.title}

*Date:* {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(s.created))}
*Messages:* {s.message_count}
*Related:* [User Profile](../profile/user_profile.md)

## Key Takeaways & Context
{s.summary}
"""
                (sessions_dir / f"{sess_id}.md").write_text(sess_md, encoding="utf-8")
                count += 1

        # Re-index all loaded bundles
        self.load_all_bundles()
        log.info(f"Auto-compiled {count} OKF knowledge documents from Amethyst memory.")
        return count

    def get_topics_list(self) -> List[dict]:
        """Return list of indexed topics for frontend visualization."""
        if not self.nodes:
            self.load_all_bundles()
        return [node.to_dict() for node in self.nodes.values()]
