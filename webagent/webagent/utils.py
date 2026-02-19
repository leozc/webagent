"""Utility functions for webagent."""
import os
import re
import json
import hashlib
import time
import random
import string
from typing import Dict, Any, List, Optional, Callable
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse


def random_string(length: int = 16, charset: str = None) -> str:
    """Generate random string."""
    charset = charset or string.ascii_letters + string.digits
    return ''.join(random.choices(charset, k=length))


def random_email(domain: str = "example.com") -> str:
    """Generate random email."""
    name = random_string(8).lower()
    return f"{name}@{domain}"


def random_username(prefix: str = "user") -> str:
    """Generate random username."""
    return f"{prefix}_{random_string(8).lower()}"


def md5(text: str) -> str:
    """Get MD5 hash."""
    return hashlib.md5(text.encode()).hexdigest()


def sha256(text: str) -> str:
    """Get SHA256 hash."""
    return hashlib.sha256(text.encode()).hexdigest()


def parse_url(url: str) -> Dict[str, Any]:
    """Parse URL into components."""
    parsed = urlparse(url)
    return {
        "scheme": parsed.scheme,
        "netloc": parsed.netloc,
        "hostname": parsed.hostname,
        "port": parsed.port,
        "path": parsed.path,
        "params": parsed.params,
        "query": parse_qs(parsed.query),
        "fragment": parsed.fragment,
    }


def build_url(base: str, path: str = "", params: Dict = None) -> str:
    """Build URL from components."""
    parsed = urlparse(base)
    
    if path and not path.startswith("/"):
        path = "/" + path
    
    new_parsed = parsed._replace(
        path=path,
        query=urlencode(params) if params else ""
    )
    
    return urlunparse(new_parsed)


def extract_domain(url: str) -> str:
    """Extract domain from URL."""
    return urlparse(url).netloc


def extract_links(html: str, base_url: str = "") -> List[str]:
    """Extract all links from HTML."""
    pattern = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
    links = pattern.findall(html)
    
    # Resolve relative URLs
    if base_url:
        links = [urljoin(base_url, link) for link in links]
    
    return links


def extract_emails(text: str) -> List[str]:
    """Extract emails from text."""
    pattern = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
    return pattern.findall(text)


def extract_phones(text: str) -> List[str]:
    """Extract phone numbers from text."""
    pattern = re.compile(r'\+?[1-9]\d{1,14}')
    return pattern.findall(text)


def clean_text(text: str) -> str:
    """Clean text for display."""
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    # Remove control characters
    text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\r\t')
    return text.strip()


def retry(max_attempts: int = 3, delay: float = 1, backoff: float = 2, exceptions: tuple = (Exception,)):
    """Retry decorator.
    
    Args:
        max_attempts: Maximum number of attempts
        delay: Initial delay between retries
        backoff: Multiplier for delay after each attempt
        exceptions: Tuple of exceptions to catch
    """
    def decorator(func: Callable):
        def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        time.sleep(current_delay)
                        current_delay *= backoff
                    continue
            
            raise last_exception
        
        return wrapper
    return decorator


def rate_limit(calls: int, period: float):
    """Rate limit decorator.
    
    Args:
        calls: Maximum number of calls
        period: Time period in seconds
    """
    call_times: List[float] = []
    
    def decorator(func: Callable):
        def wrapper(*args, **kwargs):
            now = time.time()
            
            # Remove old calls outside the period
            while call_times and now - call_times[0] > period:
                call_times.pop(0)
            
            if len(call_times) >= calls:
                sleep_time = period - (now - call_times[0])
                if sleep_time > 0:
                    time.sleep(sleep_time)
                return wrapper(*args, **kwargs)
            
            call_times.append(now)
            return func(*args, **kwargs)
        
        return wrapper
    return decorator


def load_json(path: str) -> Dict:
    """Load JSON from file."""
    with open(path, "r") as f:
        return json.load(f)


def save_json(data: Dict, path: str, indent: int = 2):
    """Save JSON to file."""
    with open(path, "w") as f:
        json.dump(data, f, indent=indent)


def load_env(path: str = ".env"):
    """Load environment variables from .env file."""
    if not os.path.exists(path):
        return
    
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                key, _, value = line.partition("=")
                os.environ[key.strip()] = value.strip()


class Cache:
    """Simple in-memory cache with TTL."""
    
    def __init__(self, ttl: float = 300):
        """Initialize cache.
        
        Args:
            ttl: Time to live in seconds
        """
        self.ttl = ttl
        self._cache: Dict[str, tuple] = {}
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get value from cache."""
        if key in self._cache:
            value, timestamp = self._cache[key]
            if time.time() - timestamp < self.ttl:
                return value
            del self._cache[key]
        return default
    
    def set(self, key: str, value: Any):
        """Set value in cache."""
        self._cache[key] = (value, time.time())
    
    def delete(self, key: str):
        """Delete value from cache."""
        if key in self._cache:
            del self._cache[key]
    
    def clear(self):
        """Clear all cache."""
        self._cache.clear()
    
    def __contains__(self, key: str) -> bool:
        """Check if key exists in cache."""
        return self.get(key) is not None
    
    def __getitem__(self, key: str) -> Any:
        """Get value (raises KeyError if not found)."""
        value = self.get(key)
        if value is None:
            raise KeyError(key)
        return value
    
    def __setitem__(self, key: str, value: Any):
        """Set value."""
        self.set(key, value)


class RateLimiter:
    """Rate limiter for API calls."""
    
    def __init__(self, calls: int, period: float):
        """Initialize rate limiter.
        
        Args:
            calls: Maximum number of calls
            period: Time period in seconds
        """
        self.calls = calls
        self.period = period
        self._calls: List[float] = []
    
    def __call__(self, func: Callable) -> Callable:
        """Decorator to rate limit function."""
        def wrapper(*args, **kwargs):
            now = time.time()
            
            # Remove old calls
            while self._calls and now - self._calls[0] > self.period:
                self._calls.pop(0)
            
            if len(self._calls) >= self.calls:
                sleep_time = self.period - (now - self._calls[0])
                if sleep_time > 0:
                    time.sleep(sleep_time)
                return wrapper(*args, **kwargs)
            
            self._calls.append(now)
            return func(*args, **kwargs)
        
        return wrapper
