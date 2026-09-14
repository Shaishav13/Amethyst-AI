"""
Amethyst Web Search Engine
===========================
Scrapes DuckDuckGo's static HTML endpoint for live web results.
Designed to be offline-safe: always check is_connected() before calling search().

Fixes applied:
  - is_connected() catches ALL exceptions, not just ConnectionError
  - Rate limiting: minimum 3 seconds between searches
  - Singleton-style reuse: instantiate once, reuse across requests
  - Robust URL extraction with fallback to snippets
"""

import logging
import time
import requests
import urllib.parse
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

log = logging.getLogger("amethyst.search")


class WebSearchEngine:
    """Singleton-friendly web search engine with built-in rate limiting."""

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/115.0.0.0 Safari/537.36"
        }
        self._last_search_time = 0.0
        self._min_interval = 3.0  # seconds between searches (rate limit)
        self._session = requests.Session()
        self._session.headers.update(self.headers)

    def _scrape_url(self, url: str) -> str:
        """Scrapes the text content of a single URL."""
        try:
            resp = self._session.get(url, timeout=5)
            if resp.status_code != 200:
                return ""
            resp.encoding = resp.apparent_encoding  # handle non-UTF8 pages
            soup = BeautifulSoup(resp.text, "html.parser")

            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()

            text = soup.get_text(separator=" ")
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = "\n".join(chunk for chunk in chunks if chunk)

            return text[:1500]
        except Exception as e:
            log.debug(f"Failed to scrape {url}: {e}")
            return ""

    def search(self, query: str, max_results: int = 3, scrape: bool = True) -> str:
        """
        Performs a DuckDuckGo HTML search, extracts real URLs, optionally
        scrapes the top pages, and returns a formatted context string.

        Rate-limited: will not fire more than once every 3 seconds.
        """
        # ── Rate limiting ────────────────────────────────────────────────
        now = time.time()
        elapsed = now - self._last_search_time
        if elapsed < self._min_interval:
            wait = self._min_interval - elapsed
            log.info(f"Rate limit: waiting {wait:.1f}s before next search.")
            time.sleep(wait)
        self._last_search_time = time.time()

        log.info(f"Performing live web search for: '{query}'")
        try:
            url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
            resp = self._session.get(url, timeout=8)

            if resp.status_code != 200:
                return f"Search engine returned status code {resp.status_code}"

            resp.encoding = resp.apparent_encoding
            soup = BeautifulSoup(resp.text, "html.parser")

            # DDG uses .result__a for clickable title links (more reliable than .result__url)
            result_links = soup.select(".result__a")
            snippets_tags = soup.select(".result__snippet")

            # Extract real URLs from DDG redirect links
            urls = []
            snippets = []
            for i, a_tag in enumerate(result_links[:max_results]):
                href = a_tag.get("href", "")
                if "uddg=" in href:
                    qs = urllib.parse.urlparse(href).query
                    params = urllib.parse.parse_qs(qs)
                    if "uddg" in params:
                        urls.append(params["uddg"][0])
                elif href.startswith("http"):
                    urls.append(href)

                # Grab the snippet text as fallback content
                if i < len(snippets_tags):
                    snippets.append(snippets_tags[i].get_text(strip=True))
                else:
                    snippets.append("")

            if not urls:
                return "No search results found."

            context = []
            if scrape:
                with ThreadPoolExecutor(max_workers=min(max_results, 3)) as executor:
                    future_to_idx = {
                        executor.submit(self._scrape_url, u): i
                        for i, u in enumerate(urls)
                    }
                    for future in as_completed(future_to_idx):
                        idx = future_to_idx[future]
                        page_text = future.result()
                        # Fall back to DDG snippet if scraping failed
                        content = page_text if page_text else snippets[idx]
                        if content:
                            context.append(
                                f"Source: {urls[idx]}\nContent:\n{content}\n"
                            )

            if not context:
                # Last resort: just return the snippets
                for i, u in enumerate(urls):
                    if snippets[i]:
                        context.append(f"Source: {u}\nSnippet: {snippets[i]}\n")

            if not context:
                return "Could not extract readable content from the search results."

            return "\n\n".join(context)

        except Exception as e:
            log.error(f"Web search failed: {e}")
            return f"Web search failed: {str(e)}"

    def is_connected(self) -> bool:
        """
        Check if we have an active internet connection.
        Catches ALL exceptions (not just ConnectionError) to prevent crashes
        on DNS failures, SSL errors, timeouts, firewall blocks, etc.
        """
        try:
            requests.head("https://1.1.1.1", timeout=2)
            return True
        except Exception:
            return False
