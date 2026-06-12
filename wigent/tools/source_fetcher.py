"""
Role: Source-driven development tool for grounding decisions in official docs.
Author: Wigent AI
Version: 1.0.0

Fetches official documentation, verifies framework decisions against sources,
cites sources in recommendations, and flags unverified claims.

Usage:
    from wigent.tools.source_fetcher import SourceFetcher, SourceCitation

    fetcher = SourceFetcher(cache_dir=".wigent/sources")

    # Fetch and verify
    source = fetcher.fetch("https://docs.python.org/3/library/asyncio.html")
    verified = fetcher.verify_claim(
        claim="asyncio.run() should only be called once",
        source=source
    )

    # Cite in output
    citation = SourceCitation(
        source="Python asyncio docs",
        url="https://docs.python.org/3/library/asyncio.html",
        section="Running an asyncio program",
        quote="This function should be used as a main entry point for asyncio programs..."
    )
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    pass


@dataclass(frozen=True)
class SourceCitation:
    """A verified citation from official documentation."""

    source: str
    url: str
    section: str
    quote: str
    accessed: str = field(default_factory=lambda: time.strftime("%Y-%m-%d"))
    verification_status: str = "verified"

    def to_markdown(self) -> str:
        """Render as markdown footnote."""
        status_icon = {
            "verified": "\u2705",
            "partial": "\u26a0\ufe0f",
            "unverified": "\u274c"
        }.get(self.verification_status, "\u2753")

        return (
            f"{status_icon} **{self.source}** -- "
            f"[{self.section}]({self.url}) "
            f"(accessed {self.accessed})\n"
            f"> {self.quote[:200]}{'...' if len(self.quote) > 200 else ''}"
        )


@dataclass
class SourceDocument:
    """A fetched and processed documentation page."""

    url: str
    title: str
    content: str
    sections: dict[str, str] = field(default_factory=dict)
    fetched_at: float = field(default_factory=time.time)
    cache_path: Path | None = None

    def find_claim(self, claim: str) -> tuple[bool, str | None]:
        """
        Search for evidence supporting or contradicting a claim.

        Returns:
            Tuple of (found_support, matching_quote_or_none)
        """
        claim_words = set(claim.lower().split())

        for heading, section_content in self.sections.items():
            section_words = set(section_content.lower().split())
            overlap = len(claim_words & section_words) / len(claim_words) if claim_words else 0

            if overlap > 0.7:
                sentences = re.split(r'(?<=[.!?])\s+', section_content)
                for sentence in sentences:
                    sent_words = set(sentence.lower().split())
                    if len(claim_words & sent_words) / len(claim_words) > 0.5:
                        return True, sentence.strip()

        if claim.lower() in self.content.lower():
            idx = self.content.lower().find(claim.lower())
            start = max(0, idx - 100)
            end = min(len(self.content), idx + len(claim) + 100)
            return True, self.content[start:end].strip()

        return False, None


class SourceFetcher:
    """
    Fetches and caches official documentation for source-driven decisions.

    Principles:
    1. Official docs > Stack Overflow > Blog posts > AI hallucinations
    2. Version-specific URLs -- "latest" is not acceptable
    3. Cached locally -- network is not required for verification
    4. Exact quotes -- paraphrasing introduces error
    5. Flag unverified -- "I couldn't find this in the docs" is honest
    """

    OFFICIAL_SOURCES = {
        "python": r"docs\.python\.org",
        "django": r"docs\.djangoproject\.com",
        "fastapi": r"fastapi\.tiangolo\.com",
        "react": r"react\.dev",
        "vue": r"vuejs\.org",
        "angular": r"angular\.io",
        "nodejs": r"nodejs\.org/docs",
        "postgres": r"postgresql\.org/docs",
        "docker": r"docs\.docker\.com",
        "kubernetes": r"kubernetes\.io/docs",
        "aws": r"docs\.aws\.amazon\.com",
        "gcp": r"cloud\.google\.com/docs",
        "azure": r"learn\.microsoft\.com/azure",
        "pytest": r"docs\.pytest\.org",
        "sqlalchemy": r"docs\.sqlalchemy\.org",
        "pydantic": r"docs\.pydantic\.dev",
        "langchain": r"python\.langchain\.com",
        "openai": r"platform\.openai\.com/docs",
        "anthropic": r"docs\.anthropic\.com",
    }

    UNTRUSTED_PATTERNS = [
        r"medium\.com", r"dev\.to", r"hackernoon\.com",
        r"stackoverflow\.com/questions",
        r"github\.com/.*/issues",
        r"reddit\.com", r"quora\.com",
    ]

    def __init__(
        self,
        cache_dir: str | Path = ".wigent/sources",
        ttl_days: int = 7,
        max_cache_size_mb: int = 100,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_days * 24 * 3600
        self.max_cache_size = max_cache_size_mb * 1024 * 1024

        self.fetches_from_network = 0
        self.fetches_from_cache = 0
        self.verification_attempts = 0
        self.verification_successes = 0

    def fetch(self, url: str, force_refresh: bool = False) -> SourceDocument:
        """
        Fetch documentation from URL or cache.

        Args:
            url: The documentation URL
            force_refresh: Ignore cache and re-fetch

        Returns:
            SourceDocument with parsed content

        Raises:
            SourceError: If fetch fails and no cache exists
        """
        cache_key = self._cache_key(url)
        cache_path = self.cache_dir / f"{cache_key}.json"

        if not force_refresh and cache_path.exists():
            doc = self._load_from_cache(cache_path)
            if doc and (time.time() - doc.fetched_at) < self.ttl_seconds:
                self.fetches_from_cache += 1
                return doc

        try:
            doc = self._fetch_from_network(url)
            self._save_to_cache(doc, cache_path)
            self.fetches_from_network += 1
            return doc
        except Exception as e:
            if cache_path.exists():
                doc = self._load_from_cache(cache_path)
                if doc:
                    doc.fetched_at = time.time() - self.ttl_seconds - 1
                    return doc
            raise SourceError(f"Failed to fetch {url}: {e}") from e

    def verify_claim(
        self,
        claim: str,
        source: SourceDocument | str,
    ) -> SourceCitation:
        """
        Verify a claim against a source document.

        Args:
            claim: The claim to verify
            source: SourceDocument or URL to fetch

        Returns:
            SourceCitation with verification status
        """
        self.verification_attempts += 1

        if isinstance(source, str):
            source = self.fetch(source)

        found, quote = source.find_claim(claim)

        if found and quote:
            self.verification_successes += 1
            return SourceCitation(
                source=source.title or urlparse(source.url).netloc,
                url=source.url,
                section=self._find_section_for_quote(source, quote),
                quote=quote[:300],
                verification_status="verified",
            )
        elif found:
            return SourceCitation(
                source=source.title or urlparse(source.url).netloc,
                url=source.url,
                section="General",
                quote="Claim mentioned but exact wording not found",
                verification_status="partial",
            )
        else:
            return SourceCitation(
                source=source.title or urlparse(source.url).netloc,
                url=source.url,
                section="Not found",
                quote="Claim could not be verified in source",
                verification_status="unverified",
            )

    def verify_multiple(
        self,
        claims: list[str],
        sources: list[str | SourceDocument],
    ) -> list[SourceCitation]:
        """Verify multiple claims against multiple sources."""
        results = []

        for claim in claims:
            verified = False
            for source in sources:
                citation = self.verify_claim(claim, source)
                results.append(citation)
                if citation.verification_status == "verified":
                    verified = True
                    break

            if not verified:
                results.append(SourceCitation(
                    source="All sources checked",
                    url="",
                    section="N/A",
                    quote=f"Could not verify: {claim}",
                    verification_status="unverified",
                ))

        return results

    def check_source_trust(self, url: str) -> dict[str, str | bool]:
        """
        Evaluate trustworthiness of a source URL.

        Returns:
            Dict with trust assessment
        """
        result = {
            "url": url,
            "is_official": False,
            "official_for": None,
            "is_untrusted": False,
            "warning": None,
        }

        for name, pattern in self.OFFICIAL_SOURCES.items():
            if re.search(pattern, url):
                result["is_official"] = True
                result["official_for"] = name
                return result

        for pattern in self.UNTRUSTED_PATTERNS:
            if re.search(pattern, url):
                result["is_untrusted"] = True
                result["warning"] = (
                    "This source is not official documentation. "
                    "Verify claims against primary sources before relying on this information."
                )
                return result

        result["warning"] = (
            "Not an official source. Consider verifying against "
            "primary documentation."
        )
        return result

    def suggest_sources(self, topic: str, framework: str | None = None) -> list[str]:
        """
        Suggest official sources for a given topic.

        Args:
            topic: The technology or concept (e.g., "asyncio", "React hooks")
            framework: Optional framework name for filtering

        Returns:
            List of suggested official URLs
        """
        suggestions = []

        framework_sources = {
            "python": [
                f"https://docs.python.org/3/library/{topic.lower()}.html",
                f"https://docs.python.org/3/tutorial/{topic.lower()}.html",
            ],
            "django": [
                f"https://docs.djangoproject.com/en/stable/topics/{topic.lower()}/",
                f"https://docs.djangoproject.com/en/stable/ref/{topic.lower()}/",
            ],
            "fastapi": [
                f"https://fastapi.tiangolo.com/tutorial/{topic.lower()}/",
            ],
            "react": [
                f"https://react.dev/reference/react/{topic}",
                f"https://react.dev/learn/{topic.lower().replace(' ', '-')}",
            ],
            "pytest": [
                f"https://docs.pytest.org/en/stable/how-to/{topic.lower()}.html",
            ],
        }

        if framework and framework.lower() in framework_sources:
            suggestions.extend(framework_sources[framework.lower()])

        suggestions.extend([
            f"https://docs.python.org/3/search.html?q={topic.replace(' ', '+')}",
            f"https://readthedocs.org/search/?q={topic.replace(' ', '+')}",
        ])

        return suggestions

    def get_stats(self) -> dict[str, int | float]:
        """Return fetch and verification statistics."""
        total_fetches = self.fetches_from_network + self.fetches_from_cache
        cache_hit_rate = (
            self.fetches_from_cache / total_fetches if total_fetches > 0 else 0
        )
        verification_rate = (
            self.verification_successes / self.verification_attempts
            if self.verification_attempts > 0 else 0
        )

        return {
            "fetches_from_network": self.fetches_from_network,
            "fetches_from_cache": self.fetches_from_cache,
            "cache_hit_rate": cache_hit_rate,
            "verification_attempts": self.verification_attempts,
            "verification_successes": self.verification_successes,
            "verification_rate": verification_rate,
            "cache_size_mb": self._get_cache_size() / (1024 * 1024),
        }

    def clear_cache(self) -> None:
        """Clear all cached documents."""
        for cache_file in self.cache_dir.glob("*.json"):
            cache_file.unlink()

    # =================================================================
    # Internal Methods
    # =================================================================

    def _cache_key(self, url: str) -> str:
        """Generate cache key from URL."""
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    def _load_from_cache(self, path: Path) -> SourceDocument | None:
        """Load document from cache file."""
        try:
            data = json.loads(path.read_text())
            return SourceDocument(
                url=data["url"],
                title=data.get("title", ""),
                content=data.get("content", ""),
                sections=data.get("sections", {}),
                fetched_at=data.get("fetched_at", 0),
                cache_path=path,
            )
        except (json.JSONDecodeError, KeyError):
            return None

    def _save_to_cache(self, doc: SourceDocument, path: Path) -> None:
        """Save document to cache file."""
        if self._get_cache_size() > self.max_cache_size:
            self._evict_oldest()

        data = {
            "url": doc.url,
            "title": doc.title,
            "content": doc.content,
            "sections": doc.sections,
            "fetched_at": doc.fetched_at,
        }
        path.write_text(json.dumps(data, indent=2))

    def _fetch_from_network(self, url: str) -> SourceDocument:
        """Fetch document from network."""
        try:
            import requests
        except ImportError:
            raise SourceError("requests library required for network fetch")

        headers = {
            "User-Agent": "Wigent-SourceFetcher/1.0 (AI Coding Agent)"
        }

        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        content = response.text

        title = self._extract_title(content)
        sections = self._extract_sections(content)

        return SourceDocument(
            url=url,
            title=title,
            content=content,
            sections=sections,
        )

    def _extract_title(self, html: str) -> str:
        """Extract title from HTML."""
        match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        return match.group(1).strip() if match else "Untitled"

    def _extract_sections(self, html: str) -> dict[str, str]:
        """Extract sections from HTML headings."""
        sections = {}

        pattern = r"<h[123][^>]*>(.*?)</h[123]>(.*?)(?=<h[123]|$)"
        matches = re.findall(pattern, html, re.IGNORECASE | re.DOTALL)

        for heading, content in matches:
            clean_heading = re.sub(r"<[^>]+>", "", heading).strip()
            clean_content = re.sub(r"<[^>]+>", " ", content).strip()

            if clean_heading and len(clean_content) > 50:
                sections[clean_heading] = clean_content[:5000]

        return sections

    def _find_section_for_quote(self, source: SourceDocument, quote: str) -> str:
        """Find which section contains a quote."""
        for heading, content in source.sections.items():
            if quote[:100] in content:
                return heading
        return "Unknown section"

    def _get_cache_size(self) -> int:
        """Calculate total cache size in bytes."""
        return sum(f.stat().st_size for f in self.cache_dir.glob("*.json"))

    def _evict_oldest(self) -> None:
        """Remove oldest cache files to make room."""
        files = sorted(
            self.cache_dir.glob("*.json"),
            key=lambda f: f.stat().st_mtime
        )
        to_remove = len(files) // 5
        for f in files[:to_remove]:
            f.unlink()


class SourceError(Exception):
    """Raised when source fetching or verification fails."""
    pass
