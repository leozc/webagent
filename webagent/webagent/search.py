"""Search backends for web scraping."""
import os
import json
import time
import re
import requests
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from urllib.parse import quote_plus, urljoin
from dataclasses import dataclass, field


@dataclass
class SearchResult:
    """Represents a single search result."""
    title: str
    url: str
    snippet: str
    position: int
    source: str
    extra: Dict[str, Any] = field(default_factory=dict)


class SearchBackend(ABC):
    """Abstract base class for search backends."""
    
    @abstractmethod
    def search(self, query: str, num: int = 10) -> List[SearchResult]:
        """Perform search and return results."""
        pass


class GoogleCustomSearch(SearchBackend):
    """Google Custom Search JSON API (free 100/day)."""
    
    def __init__(self, api_key: str = None, cx: str = None):
        self.api_key = api_key or os.getenv("GOOGLE_CS_API_KEY")
        self.cx = cx or os.getenv("GOOGLE_CS_CX")
        
        if not self.api_key or not self.cx:
            raise ValueError("Google CS API key and CX required. Set GOOGLE_CS_API_KEY and GOOGLE_CS_CX")
    
    def search(self, query: str, num: int = 10) -> List[SearchResult]:
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "key": self.api_key,
            "cx": self.cx,
            "q": query,
            "num": min(num, 10)  # Max 10 per request
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for i, item in enumerate(data.get("items", [])):
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("link", ""),
                snippet=item.get("snippet", ""),
                position=i + 1,
                source="google_cs",
                extra={
                    "displayLink": item.get("displayLink"),
                    "mime": item.get("mime"),
                    "fileFormat": item.get("fileFormat"),
                }
            ))
        
        return results


class SerpAPI(SearchBackend):
    """SerpAPI - paid Google results with no blocking."""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("SERPAPI_KEY")
        
        if not self.api_key:
            raise ValueError("SerpAPI key required. Set SERPAPI_KEY")
    
    def search(self, query: str, num: int = 10) -> List[SearchResult]:
        params = {
            "api_key": self.api_key,
            "q": query,
            "num": num,
            "engine": "google"
        }
        
        response = requests.get("https://serpapi.com/search", params=params)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for i, item in enumerate(data.get("organic_results", [])):
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("link", ""),
                snippet=item.get("snippet", ""),
                position=i + 1,
                source="serpapi",
                extra={
                    "position": item.get("position"),
                    "rating": item.get("rating"),
                    "extensions": item.get("extensions", []),
                }
            ))
        
        return results


class DuckDuckGoSearch(SearchBackend):
    """DuckDuckGo Instant Answer API (free).
    
    Note: DuckDuckGo's free API has become unreliable. For production use,
    we recommend using SerpAPI, Google Custom Search API, or Bing API.
    """
    
    def __init__(self):
        self.base_url = "https://duckduckgo.com/"
        try:
            from bs4 import BeautifulSoup
            self.has_bs4 = True
        except ImportError:
            self.has_bs4 = False
    
    def _parse_html_fallback(self, text: str, num: int) -> List[SearchResult]:
        """Parse HTML without BeautifulSoup."""
        results = []
        
        # Very rough regex parsing
        # Match result links: <a class="result__a" href="...">title</a>
        link_pattern = re.compile(r'<a class="result__a" href="([^"]+)"[^>]*>([^<]+)</a>')
        
        for i, match in enumerate(link_pattern.findall(text)[:num]):
            url, title = match
            # Try to get snippet
            snippet = ""
            results.append(SearchResult(
                title=title.strip(),
                url=url.strip(),
                snippet=snippet,
                position=i + 1,
                source="duckduckgo",
                extra={}
            ))
        
        return results
    
    def _parse_html_bs4(self, text: str, num: int) -> List[SearchResult]:
        """Parse HTML with BeautifulSoup."""
        from bs4 import BeautifulSoup
        
        results = []
        soup = BeautifulSoup(text, "html.parser")
        
        for i, result in enumerate(soup.select(".result")[:num]):
            title_elem = result.select_one(".result__title")
            link_elem = result.select_one(".result__url")
            snippet_elem = result.select_one(".result__snippet")
            
            if title_elem and link_elem:
                results.append(SearchResult(
                    title=title_elem.get_text(strip=True),
                    url=link_elem.get_text(strip=True),
                    snippet=snippet_elem.get_text(strip=True) if snippet_elem else "",
                    position=i + 1,
                    source="duckduckgo",
                    extra={}
                ))
        
        return results
    
    def search(self, query: str, num: int = 10) -> List[SearchResult]:
        # Use the HTML endpoint for more results
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        # First get the token
        resp = requests.post(self.base_url, data={"q": query}, headers=headers, timeout=10)
        token = resp.cookies.get("kl")
        
        # Then search
        params = {
            "q": query,
            "format": "json",
            "kl": "us-en",
        }
        
        if token:
            params["kl"] = token
        
        try:
            response = requests.get(
                "https://lite.duckduckgo.com/lite/",
                params=params,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
        except Exception as e:
            print(f"DuckDuckGo JSON failed: {e}, trying HTML")
            return self._search_html_fallback(query, num, headers)
        
        results = []
        # Parse the JSON response
        try:
            data = response.json()
            for i, item in enumerate(data.get("results", [])[:num]):
                results.append(SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("snippet", ""),
                    position=i + 1,
                    source="duckduckgo",
                    extra={}
                ))
        except Exception as e:
            # Fallback: parse HTML
            print(f"DuckDuckGo JSON parse failed: {e}, using HTML fallback")
            return self._search_html_fallback(query, num, headers)
        
        return results
    
    def _search_html_fallback(self, query: str, num: int, headers: dict) -> List[SearchResult]:
        """Direct HTML scraping fallback."""
        response = requests.get(
            f"https://html.duckduckgo.com/html/?q={quote_plus(query)}",
            headers=headers,
            timeout=10
        )
        response.raise_for_status()
        
        if self.has_bs4:
            return self._parse_html_bs4(response.text, num)
        else:
            return self._parse_html_fallback(response.text, num)


class BingSearch(SearchBackend):
    """Bing Search API."""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("BING_API_KEY")
        self.endpoint = "https://api.bing.microsoft.com/v7.0/search"
        
        if not self.api_key:
            raise ValueError("Bing API key required. Set BING_API_KEY")
    
    def search(self, query: str, num: int = 10) -> List[SearchResult]:
        headers = {"Ocp-Apim-Subscription-Key": self.api_key}
        params = {"q": query, "count": min(num, 50), "mkt": "en-US"}
        
        response = requests.get(self.endpoint, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for i, item in enumerate(data.get("webPages", {}).get("value", [])):
            results.append(SearchResult(
                title=item.get("name", ""),
                url=item.get("url", ""),
                snippet=item.get("snippet", ""),
                position=i + 1,
                source="bing",
                extra={
                    "displayUrl": item.get("displayUrl"),
                    "dateLastCrawled": item.get("dateLastCrawled"),
                }
            ))
        
        return results


class GoogleSearch:
    """Unified Google search with multiple backends."""
    
    def __init__(
        self,
        provider: str = "google_cs",  # google_cs, serpapi, bing
        api_key: str = None,
        cx: str = None
    ):
        self.provider = provider
        
        if provider == "serpapi":
            self.backend = SerpAPI(api_key)
        elif provider == "bing":
            self.backend = BingSearch(api_key)
        elif provider == "duckduckgo":
            self.backend = DuckDuckGoSearch()
        else:  # google_cs or auto
            try:
                self.backend = GoogleCustomSearch(api_key, cx)
            except ValueError as e:
                # Fallback to DuckDuckGo if no Google keys
                print(f"Warning: {e}. Falling back to DuckDuckGo.")
                self.backend = DuckDuckGoSearch()
    
    def search(self, query: str, num: int = 10) -> List[SearchResult]:
        return self.backend.search(query, num)


# Convenience function
def search(query: str, provider: str = "auto", num: int = 10) -> List[SearchResult]:
    """Quick search function.
    
    Args:
        query: Search query
        provider: "google_cs", "serpapi", "bing", "duckduckgo", or "auto"
        num: Number of results
    
    Returns:
        List of SearchResult objects
    """
    if provider == "auto":
        # Try to use best available
        if os.getenv("SERPAPI_KEY"):
            provider = "serpapi"
        elif os.getenv("GOOGLE_CS_API_KEY") and os.getenv("GOOGLE_CS_CX"):
            provider = "google_cs"
        elif os.getenv("BING_API_KEY"):
            provider = "bing"
        else:
            provider = "duckduckgo"
    
    if provider == "serpapi":
        return SerpAPI().search(query, num)
    elif provider == "bing":
        return BingSearch().search(query, num)
    elif provider == "google_cs":
        return GoogleCustomSearch().search(query, num)
    else:
        return DuckDuckGoSearch().search(query, num)
