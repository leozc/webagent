"""HTTP client with stealth capabilities for request-based scraping."""
import os
import time
import random
import requests
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from urllib.parse import urlparse, urljoin

# Optional: fake-useragent
try:
    from fake_useragent import UserAgent
    FAKE_UA_AVAILABLE = True
except ImportError:
    FAKE_UA_AVAILABLE = False

from .utils import Cache, RateLimiter, retry


@dataclass
class ProxyConfig:
    """Proxy configuration."""
    host: str
    port: int
    protocol: str = "http"  # http, https, socks5
    username: str = None
    password: str = None
    
    @property
    def url(self) -> str:
        """Get proxy URL."""
        if self.username and self.password:
            return f"{self.protocol}://{self.username}:{self.password}@{self.host}:{self.port}"
        return f"{self.protocol}://{self.host}:{self.port}"
    
    @classmethod
    def from_string(cls, proxy_str: str) -> "ProxyConfig":
        """Parse proxy string like user:pass@host:port or just host:port."""
        # Remove protocol if present
        if "://" in proxy_str:
            protocol, rest = proxy_str.split("://", 1)
        else:
            protocol = "http"
            rest = proxy_str
        
        # Check for auth
        if "@" in rest:
            auth, host_port = rest.split("@", 1)
            username, password = auth.split(":", 1)
        else:
            username = password = None
            host_port = rest
        
        # Parse host:port
        if ":" in host_port:
            host, port = host_port.rsplit(":", 1)
            port = int(port)
        else:
            host = host_port
            port = 8080
        
        return cls(
            host=host,
            port=port,
            protocol=protocol,
            username=username,
            password=password
        )


class ProxyPool:
    """Pool of rotating proxies."""
    
    def __init__(self, proxies: List[str] = None, rotate_on_error: bool = True):
        """Initialize proxy pool.
        
        Args:
            proxies: List of proxy strings
            rotate_on_error: Rotate to next proxy on error
        """
        self.proxies = [ProxyConfig.from_string(p) for p in (proxies or [])]
        self.rotate_on_error = rotate_on_error
        self._index = 0
        self._failed: set = set()
    
    def add(self, proxy: str):
        """Add proxy to pool."""
        self.proxies.append(ProxyConfig.from_string(proxy))
    
    def get(self) -> Optional[ProxyConfig]:
        """Get next working proxy."""
        if not self.proxies:
            return None
        
        # Try all proxies
        for _ in range(len(self.proxies)):
            proxy = self.proxies[self._index]
            self._index = (self._index + 1) % len(self.proxies)
            
            if proxy not in self._failed:
                return proxy
        
        # All failed, reset and return first
        self._failed.clear()
        return self.proxies[0] if self.proxies else None
    
    def mark_failed(self, proxy: ProxyConfig):
        """Mark proxy as failed."""
        self._failed.add(proxy)
    
    def __len__(self) -> int:
        return len(self.proxies)


@dataclass
class RequestConfig:
    """Configuration for stealth HTTP requests."""
    # Request settings
    timeout: int = 30
    follow_redirects: bool = True
    verify_ssl: bool = True
    
    # Identity
    user_agent: str = None  # Auto-generated if None
    accept_language: str = "en-US,en;q=0.9"
    accept_encoding: str = "gzip, deflate, br"
    accept: str = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    
    # Stealth
    use_fake_user_agent: bool = True
    random_user_agent: bool = True
    rotate_user_agent: bool = False
    
    # Headers
    extra_headers: Dict[str, str] = field(default_factory=dict)
    
    # Proxy
    proxy: str = None  # "host:port" or "user:pass@host:port"
    proxy_pool: ProxyPool = None
    
    # Rate limiting
    rate_limit_calls: int = None
    rate_limit_period: float = None
    
    # Cookies
    cookies: Dict[str, str] = field(default_factory=dict)
    persist_cookies: bool = True
    
    # Cache
    cache_enabled: bool = False
    cache_ttl: int = 300
    
    # Callbacks
    on_request: Callable = None
    on_response: Callable = None
    on_error: Callable = None


class StealthClient:
    """Stealth HTTP client for web scraping.
    
    Features:
    - User agent rotation
    - Proxy support (single or pool)
    - Rate limiting
    - Cookie persistence
    - Caching
    - Request/response callbacks
    """
    
    DEFAULT_USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    ]
    
    def __init__(self, config: RequestConfig = None):
        self.config = config or RequestConfig()
        self.session = requests.Session()
        self._cache = Cache(ttl=self.config.cache_ttl) if self.config.cache_enabled else None
        self._rate_limiter = None
        
        if self.config.rate_limit_calls and self.config.rate_limit_period:
            self._rate_limiter = RateLimiter(
                self.config.rate_limit_calls,
                self.config.rate_limit_period
            )
        
        # Try to use fake-useragent
        self._ua = None
        if self.config.use_fake_user_agent and FAKE_UA_AVAILABLE:
            try:
                self._ua = UserAgent()
            except:
                pass
        
        # Setup session
        self._setup_session()
    
    def _setup_session(self):
        """Setup session with headers and cookies."""
        # Headers
        self.session.headers.update({
            "User-Agent": self._get_user_agent(),
            "Accept": self.config.accept,
            "Accept-Language": self.config.accept_language,
            "Accept-Encoding": self.config.accept_encoding,
        })
        self.session.headers.update(self.config.extra_headers)
        
        # Cookies
        if self.config.cookies:
            self.session.cookies.update(self.config.cookies)
    
    def _get_user_agent(self) -> str:
        """Get user agent."""
        if self.config.user_agent:
            return self.config.user_agent
        
        if self._ua:
            try:
                return self._ua.random
            except:
                pass
        
        if self.config.random_user_agent:
            return random.choice(self.DEFAULT_USER_AGENTS)
        
        return self.DEFAULT_USER_AGENTS[0]
    
    def _get_proxy(self) -> Optional[Dict]:
        """Get proxy dict for requests."""
        # Check proxy pool first
        if self.config.proxy_pool:
            proxy = self.config.proxy_pool.get()
            if proxy:
                return {"http": proxy.url, "https": proxy.url}
        
        # Single proxy
        if self.config.proxy:
            proxy_cfg = ProxyConfig.from_string(self.config.proxy)
            return {"http": proxy_cfg.url, "https": proxy_cfg.url}
        
        return None
    
    def _build_request(self, method: str, url: str, **kwargs) -> requests.Request:
        """Build request object."""
        # Rotate UA if enabled
        if self.config.rotate_user_agent:
            self.session.headers["User-Agent"] = self._get_user_agent()
        
        # Merge kwargs
        request_kwargs = {
            "timeout": self.config.timeout,
            "allow_redirects": self.config.follow_redirects,
            "verify": self.config.verify_ssl,
        }
        request_kwargs.update(kwargs)
        
        # Proxy
        proxy = self._get_proxy()
        if proxy:
            request_kwargs["proxies"] = proxy
        
        return requests.Request(method, url, **request_kwargs)
    
    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Make HTTP request.
        
        Args:
            method: HTTP method
            url: Target URL
            **kwargs: Additional request arguments
        
        Returns:
            Response object
        """
        # Rate limiting
        if self._rate_limiter:
            # Simple blocking wait
            time.sleep(random.uniform(0.1, 0.3))
        
        # Check cache for GET
        cache_key = None
        if self._cache and method == "GET":
            cache_key = f"{method}:{url}"
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached
        
        # Build request
        request_kwargs = {}
        
        # Headers
        request_kwargs["headers"] = kwargs.pop("headers", {})
        
        # Data/JSON
        if "data" in kwargs:
            request_kwargs["data"] = kwargs.pop("data")
        if "json" in kwargs:
            request_kwargs["json"] = kwargs.pop("json")
        
        # Callback
        if self.config.on_request:
            self.config.on_request(method, url, request_kwargs)
        
        # Make request with retry
        proxy = self._get_proxy()
        
        try:
            response = self.session.request(
                method,
                url,
                **request_kwargs,
                timeout=self.config.timeout,
                proxies=proxy,
                verify=self.config.verify_ssl,
            )
            
            # Callback
            if self.config.on_response:
                self.config.on_response(response)
            
            # Cache GET responses
            if self._cache and cache_key and response.status_code == 200:
                self._cache.set(cache_key, response)
            
            # Mark proxy as working if from pool
            if proxy and self.config.proxy_pool:
                pass  # Could track success
            
            return response
            
        except requests.RequestException as e:
            # Mark proxy as failed
            if proxy and self.config.proxy_pool and hasattr(proxy, 'host'):
                self.config.proxy_pool.mark_failed(proxy)
            
            if self.config.on_error:
                self.config.on_error(e)
            
            raise
    
    def get(self, url: str, **kwargs) -> requests.Response:
        """GET request."""
        return self.request("GET", url, **kwargs)
    
    def post(self, url: str, **kwargs) -> requests.Response:
        """POST request."""
        return self.request("POST", url, **kwargs)
    
    def put(self, url: str, **kwargs) -> requests.Response:
        """PUT request."""
        return self.request("PUT", url, **kwargs)
    
    def delete(self, url: str, **kwargs) -> requests.Response:
        """DELETE request."""
        return self.request("DELETE", url, **kwargs)
    
    def head(self, url: str, **kwargs) -> requests.Response:
        """HEAD request."""
        return self.request("HEAD", url, **kwargs)
    
    # ============ Convenience Methods ============
    
    def fetch(self, url: str, **kwargs) -> str:
        """Fetch URL and return text."""
        response = self.get(url, **kwargs)
        return response.text
    
    def fetch_json(self, url: str, **kwargs) -> Any:
        """Fetch URL and parse JSON."""
        response = self.get(url, **kwargs)
        return response.json()
    
    def fetch_html(self, url: str, **kwargs) -> str:
        """Fetch HTML (alias for fetch)."""
        return self.fetch(url, **kwargs)
    
    def download(self, url: str, path: str, **kwargs):
        """Download file to path."""
        response = self.get(url, stream=True, **kwargs)
        response.raise_for_status()
        
        with open(path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        return path
    
    # ============ Session Management ============
    
    def save_session(self, path: str):
        """Save session to file."""
        import json
        
        session_data = {
            "cookies": {c.name: c.value for c in self.session.cookies},
            "headers": dict(self.session.headers),
        }
        
        with open(path, "w") as f:
            json.dump(session_data, f)
    
    def load_session(self, path: str):
        """Load session from file."""
        import json
        
        with open(path, "r") as f:
            session_data = json.load(f)
        
        self.session.cookies.update(session_data.get("cookies", {}))
        self.session.headers.update(session_data.get("headers", {}))
    
    def clear_cookies(self):
        """Clear all cookies."""
        self.session.cookies.clear()
    
    @property
    def cookies(self) -> Dict[str, str]:
        """Get current cookies."""
        return {c.name: c.value for c in self.session.cookies}
    
    @property
    def headers(self) -> Dict[str, str]:
        """Get current headers."""
        return dict(self.session.headers)
    
    # ============ Context Manager ============
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()
    
    def close(self):
        """Close session."""
        self.session.close()


# ============ Quick Client ============

def get(url: str, **kwargs) -> requests.Response:
    """Quick GET request."""
    with StealthClient() as client:
        return client.get(url, **kwargs)


def post(url: str, **kwargs) -> requests.Response:
    """Quick POST request."""
    with StealthClient() as client:
        return client.post(url, **kwargs)


def fetch(url: str, **kwargs) -> str:
    """Quick fetch text."""
    return get(url, **kwargs).text


def fetch_json(url: str, **kwargs) -> Any:
    """Quick fetch JSON."""
    return get(url, **kwargs).json()
