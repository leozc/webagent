"""WebAgent - AI agent browser automation toolkit."""
from .search import (
    SearchResult,
    SearchBackend,
    GoogleSearch,
    DuckDuckGoSearch,
    BingSearch,
    search,
)

from .browser import StealthBrowser, BrowserConfig

from .captcha import (
    CaptchaSolution,
    CaptchaSolver,
    CaptchaProvider,
    solve_captcha,
)

from .http import (
    StealthClient,
    RequestConfig,
    ProxyConfig,
    ProxyPool,
    get, post, fetch, fetch_json,
)

from .inspect import (
    PageInspector,
    PageStructure,
    FormField,
    Link,
    Image,
    RequestBuilder,
)

from .network import (
    NetworkMonitor,
    NetworkRequest,
    NetworkLog,
    enable_network_monitoring,
)

from .scrape import (
    BackgroundScraper,
    ScrapeJob,
    scrape_background,
    spawn_scrape_agent,
)

from .utils import (
    random_string,
    random_email,
    random_username,
    parse_url,
    extract_links,
    extract_emails,
    extract_phones,
    clean_text,
    retry,
    rate_limit,
    Cache,
    RateLimiter,
)

__version__ = "0.1.0"
__all__ = [
    # Search
    "SearchResult",
    "SearchBackend",
    "GoogleSearch",
    "DuckDuckGoSearch", 
    "BingSearch",
    "search",
    # Browser
    "StealthBrowser",
    "BrowserConfig",
    # Captcha
    "CaptchaSolution",
    "CaptchaSolver",
    "CaptchaProvider",
    "solve_captcha",
    # HTTP Client
    "StealthClient",
    "RequestConfig",
    "ProxyConfig",
    "ProxyPool",
    "get",
    "post", 
    "fetch",
    "fetch_json",
    # Inspection
    "PageInspector",
    "PageStructure",
    "FormField",
    "Link",
    "Image",
    "RequestBuilder",
    # Network
    "NetworkMonitor",
    "NetworkRequest",
    "NetworkLog",
    "enable_network_monitoring",
    # Background Scrape
    "BackgroundScraper",
    "ScrapeJob",
    "scrape_background",
    "spawn_scrape_agent",
    # Utils
    "random_string",
    "random_email",
    "random_username",
    "parse_url",
    "extract_links",
    "extract_emails",
    "extract_phones",
    "clean_text",
    "retry",
    "rate_limit",
    "Cache",
    "RateLimiter",
]
