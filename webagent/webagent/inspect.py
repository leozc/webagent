"""Page inspection and debugging tools for AI-assisted scraping.

This module helps an AI understand page structure and generate request-based
scrapers after inspecting the page in a browser.
"""
import json
import re
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field, asdict
from urllib.parse import urlparse, urljoin

# Optional: BeautifulSoup
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

from .browser import StealthBrowser
from .http import StealthClient


@dataclass
class FormField:
    """Represents a form field."""
    name: str
    type: str
    id: str = None
    css_selector: str = None
    xpath: str = None
    label: str = None
    required: bool = False
    value: str = None
    options: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class Link:
    """Represents a link."""
    text: str
    href: str
    css_selector: str = None


@dataclass
class Image:
    """Represents an image."""
    src: str
    alt: str = None
    css_selector: str = None


@dataclass
class PageElement:
    """Represents a page element."""
    tag: str
    id: str = None
    class_name: str = None
    css_selector: str = None
    xpath: str = None
    text: str = None
    attributes: Dict[str, str] = field(default_factory=dict)
    children: List["PageElement"] = field(default_factory=list)
    
    @property
    def selector(self) -> str:
        """Get best selector for this element."""
        if self.id:
            return f"#{self.id}"
        if self.css_selector:
            return self.css_selector
        if self.xpath:
            return self.xpath
        return self.tag


@dataclass
class PageStructure:
    """Complete page structure analysis."""
    url: str
    title: str
    forms: List[FormField] = field(default_factory=list)
    links: List[Link] = field(default_factory=list)
    images: List[Image] = field(default_factory=list)
    tables: List[Dict[str, Any]] = field(default_factory=list)
    scripts: List[str] = field(default_factory=list)
    stylesheets: List[str] = field(default_factory=list)
    meta: Dict[str, str] = field(default_factory=dict)
    body_text: str = None
    element_tree: List[PageElement] = field(default_factory=list)
    api_endpoints: List[str] = field(default_factory=list)
    ajax_patterns: List[str] = field(default_factory=list)


class PageInspector:
    """Inspect page structure for AI-assisted scraping.
    
    Usage:
        inspector = PageInspector()
        
        # Analyze page
        structure = inspector.inspect("https://example.com")
        
        # Generate request-based scraper code
        code = inspector.generate_scraper(structure)
    """
    
    def __init__(self, browser: StealthBrowser = None):
        self.browser = browser
    
    def inspect(self, url: str, browser: StealthBrowser = None) -> PageStructure:
        """Inspect page and return structure.
        
        Args:
            url: URL to inspect
            browser: Optional existing browser instance
        
        Returns:
            PageStructure with full analysis
        """
        browser = browser or self.browser
        
        if browser:
            return self._inspect_browser(url, browser)
        else:
            return self._inspect_requests(url)
    
    def _inspect_browser(self, url: str, browser: StealthBrowser) -> PageStructure:
        """Inspect using browser."""
        browser.go(url)
        return self._analyze_page(browser)
    
    def _inspect_requests(self, url: str) -> PageStructure:
        """Inspect using requests."""
        from .http import StealthClient
        
        client = StealthClient()
        response = client.get(url)
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        structure = PageStructure(
            url=url,
            title=soup.title.string if soup.title else None,
            body_text=soup.get_text(separator="\n", strip=True)[:5000],
        )
        
        # Forms
        for form in soup.find_all("form"):
            for inp in form.find_all(["input", "select", "textarea"]):
                field = FormField(
                    name=inp.get("name", ""),
                    type=inp.get("type", "text"),
                    id=inp.get("id"),
                    required=inp.get("required") is not None,
                    value=inp.get("value"),
                )
                
                if inp.name == "select":
                    for opt in inp.find_all("option"):
                        field.options.append({
                            "value": opt.get("value", ""),
                            "text": opt.get_text(strip=True)
                        })
                
                structure.forms.append(field)
        
        # Links
        for a in soup.find_all("a", href=True):
            structure.links.append(Link(
                text=a.get_text(strip=True),
                href=urljoin(url, a["href"])
            ))
        
        # Images
        for img in soup.find_all("img"):
            structure.images.append(Image(
                src=urljoin(url, img.get("src", "")),
                alt=img.get("alt")
            ))
        
        # Scripts
        for script in soup.find_all("script", src=True):
            structure.scripts.append(script["src"])
        
        # Stylesheets
        for link in soup.find_all("link", rel="stylesheet"):
            if link.get("href"):
                structure.stylesheets.append(urljoin(url, link["href"]))
        
        # Meta
        for meta in soup.find_all("meta"):
            if meta.get("name"):
                structure.meta[meta["name"]] = meta.get("content")
            elif meta.get("property"):
                structure.meta[meta["property"]] = meta.get("content")
        
        # API endpoints (heuristics)
        structure.api_endpoints = self._find_api_endpoints(soup, url)
        
        return structure
    
    def _analyze_page(self, browser: StealthBrowser) -> PageStructure:
        """Analyze page from browser instance."""
        html = browser.html()
        soup = BeautifulSoup(html, "html.parser")
        
        structure = PageStructure(
            url=browser.url,
            title=browser.title,
        )
        
        # Get more details via JS
        try:
            structure.body_text = browser.eval("document.body.innerText").strip()[:5000]
        except:
            structure.body_text = soup.get_text(separator="\n", strip=True)[:5000]
        
        # Forms with more detail
        for i, form in enumerate(soup.find_all("form")):
            form_id = form.get("id") or f"form-{i}"
            
            for inp in form.find_all(["input", "select", "textarea"]):
                name = inp.get("name", "")
                if not name:
                    continue
                
                # Build CSS selector
                css_sel = self._build_css_selector(inp)
                
                field = FormField(
                    name=name,
                    type=inp.get("type", "text"),
                    id=inp.get("id"),
                    css_selector=css_sel,
                    required=inp.get("required") is not None,
                    value=inp.get("value"),
                )
                
                if inp.name == "select":
                    for opt in inp.find_all("option"):
                        field.options.append({
                            "value": opt.get("value", ""),
                            "text": opt.get_text(strip=True)
                        })
                
                structure.forms.append(field)
        
        # Links
        for a in soup.find_all("a", href=True):
            structure.links.append(Link(
                text=a.get_text(strip=True),
                href=urljoin(browser.url, a["href"]),
                css_selector=self._build_css_selector(a)
            ))
        
        # Images
        for img in soup.find_all("img"):
            structure.images.append(Image(
                src=urljoin(browser.url, img.get("src", "")),
                alt=img.get("alt"),
                css_selector=self._build_css_selector(img)
            ))
        
        # Tables
        for table in soup.find_all("table"):
            table_data = self._parse_table(table, browser.url)
            if table_data:
                structure.tables.append(table_data)
        
        # Scripts
        for script in soup.find_all("script", src=True):
            structure.scripts.append(script["src"])
        
        # Stylesheets
        for link in soup.find_all("link", rel="stylesheet"):
            if link.get("href"):
                structure.stylesheets.append(urljoin(browser.url, link["href"]))
        
        # Meta
        for meta in soup.find_all("meta"):
            if meta.get("name"):
                structure.meta[meta["name"]] = meta.get("content")
            elif meta.get("property"):
                structure.meta[meta["property"]] = meta.get("content")
        
        # API endpoints
        structure.api_endpoints = self._find_api_endpoints(soup, browser.url)
        
        # AJAX patterns
        structure.ajax_patterns = self._find_ajax_patterns(browser)
        
        return structure
    
    def _build_css_selector(self, element) -> str:
        """Build CSS selector for element."""
        if element.get("id"):
            return f"#{element['id']}"
        
        if element.get("class"):
            classes = " ".join(element.get("class", []))
            return f"{element.name}.{classes.replace(' ', '.')}"
        
        # Try parents
        parts = [element.name]
        parent = element.parent
        while parent and parent.name not in ["html", "body"]:
            if parent.get("id"):
                parts.append(f"#{parent['id']}")
                break
            if parent.get("class"):
                cls = " ".join(parent.get("class", [])[:1])
                parts.append(f"{parent.name}.{cls}")
                break
            parts.append(parent.name)
            parent = parent.parent
        
        return " > ".join(reversed(parts))
    
    def _parse_table(self, table, base_url: str) -> Dict:
        """Parse table into structured data."""
        rows = table.find_all("tr")
        if not rows:
            return None
        
        # Get headers
        header_row = rows[0]
        headers = [th.get_text(strip=True) for th in header_row.find_all(["th", "td"])]
        
        # Get data rows
        data = []
        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            row_data = {}
            for i, cell in enumerate(cells):
                if i < len(headers):
                    row_data[headers[i]] = cell.get_text(strip=True)
                
                # Check for links in cells
                links = cell.find_all("a", href=True)
                if links:
                    row_data[f"_links_{i}"] = [urljoin(base_url, a["href"]) for a in links]
            
            if row_data:
                data.append(row_data)
        
        return {
            "headers": headers,
            "rows": data[:50],  # Limit
            "row_count": len(data)
        }
    
    def _find_api_endpoints(self, soup, base_url: str) -> List[str]:
        """Find potential API endpoints."""
        endpoints = set()
        
        # From script tags
        for script in soup.find_all("script", src=True):
            src = script["src"]
            if "api" in src.lower() or "ajax" in src.lower() or ".js" in src:
                endpoints.add(urljoin(base_url, src))
        
        # From fetch/XHR calls in scripts (heuristic)
        for script in soup.find_all("script"):
            text = script.get_text()
            # Match URL patterns
            patterns = [
                r'fetch\s*\(\s*["\']([^"\']+)["\']',
                r'axios\.[a-z]+\s*\(\s*["\']([^"\']+)["\']',
                r'\.get\s*\(\s*["\']([^"\']+)["\']',
                r'\.post\s*\(\s*["\']([^"\']+)["\']',
                r'XMLHttpRequest.*?open\s*\(\s*["\'][^"\']+["\']\s*,\s*["\']([^"\']+)["\']',
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                for match in matches:
                    if match.startswith("http"):
                        endpoints.add(match)
                    elif match.startswith("/"):
                        endpoints.add(urljoin(base_url, match))
        
        return list(endpoints)[:20]
    
    def _find_ajax_patterns(self, browser: StealthBrowser) -> List[str]:
        """Find AJAX/XHR request patterns."""
        patterns = []
        
        try:
            # Get fetch/intercepted requests from performance
            js = """
                () => {
                    const patterns = [];
                    // Check for common API patterns in window
                    for (let key in window) {
                        if (key.includes('API') || key.includes('api') || key.includes('Service')) {
                            patterns.push(key);
                        }
                    }
                    return patterns;
                }
            """
            patterns = browser.eval(js) or []
        except:
            pass
        
        return patterns
    
    # ============ Code Generation ============
    
    def generate_scraper(self, structure: PageStructure, target: str = "requests") -> str:
        """Generate request-based scraper code from inspected structure.
        
        Args:
            structure: PageStructure from inspection
            target: "requests" or "httpx"
        
        Returns:
            Python code string
        """
        if target == "httpx":
            client_code = "import httpx"
            client_init = "client = httpx.Client()"
            client_close = "client.close()"
        else:
            client_code = "import requests"
            client_init = "client = requests.Session()"
            client_close = "client.close()"
        
        code = f'''{client_code}
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_URL = "{structure.url}"

{client_init}

# Headers to mimic browser
client.headers.update({{
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}})


def get_page(path: str = "") -> BeautifulSoup:
    """Fetch a page and return parsed HTML."""
    url = urljoin(BASE_URL, path)
    response = client.get(url)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def get_json(path: str, **kwargs) -> dict:
    """Fetch JSON API endpoint."""
    url = urljoin(BASE_URL, path)
    response = client.get(url, **kwargs)
    response.raise_for_status()
    return response.json()

'''
        
        # Add form handling if forms exist
        if structure.forms:
            code += '''
# Form fields found:
'''
            for form in structure.forms[:5]:  # Limit to first 5
                code += f'# - {form.name}: {form.type}'
                if form.options:
                    code += f" (options: {len(form.options)})"
                code += "\n"
            
            code += f'''

def submit_form(data: dict) -> BeautifulSoup:
    """Submit form with data."""
    response = client.post(BASE_URL, data=data)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")

'''
        
        # Add link scraping if links exist
        if structure.links:
            code += '''
# Links found on page:
# '''
            unique_domains = set()
            for link in structure.links[:10]:
                if link.href:
                    domain = urlparse(link.href).netloc
                    unique_domains.add(domain)
            
            code += ", ".join(unique_domains) + "\n"
        
        # Add table parsing if tables exist
        if structure.tables:
            table = structure.tables[0]
            code += f'''

# Table with {table.get("row_count", 0)} rows:
# Headers: {table.get("headers", [])}

def parse_table(soup) -> list:
    """Parse table into list of dicts."""
    rows = soup.select("table tr")
    if not rows:
        return []
    
    headers = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]
    data = []
    
    for row in rows[1:]:
        cells = row.find_all(["td", "th"])
        row_data = {headers[i]: cells[i].get_text(strip=True) for i in range(min(len(cells), len(headers)))}
        data.append(row_data)
    
    return data

'''
        
        # Add API endpoints if found
        if structure.api_endpoints:
            code += "\n# Potential API endpoints:\n"
            for endpoint in structure.api_endpoints[:5]:
                code += f"# - {endpoint}\n"
            
            code += '''
def fetch_api(endpoint: str, **kwargs) -> dict:
    """Fetch from API endpoint."""
    url = urljoin(BASE_URL, endpoint)
    response = client.get(url, **kwargs)
    response.raise_for_status()
    return response.json()

'''
        
        code += f'''

if __name == "__main__":
    soup = get_page()
    print(f"Title: {soup.title.string if soup.title else 'N/A'}")
    {client_close}
'''
        
        return code
    
    def generate_login_scraper(self, structure: PageStructure, username_field: str = None, password_field: str = None) -> str:
        """Generate code for login flow.
        
        Args:
            structure: PageStructure from login page inspection
            username_field: Name of username field
            password_field: Name of password field
        """
        # Auto-detect fields if not provided
        if not username_field or not password_field:
            for form in structure.forms:
                for field in form.fields:
                    if field.type in ["email", "text"]:
                        if not username_field:
                            username_field = field.name
                    if field.type == "password":
                        if not password_field:
                            password_field = field.name
        
        return f'''import requests
from bs4 import BeautifulSoup

LOGIN_URL = "{structure.url}"

session = requests.Session()

# Get login page to extract CSRF token
resp = session.get(LOGIN_URL)
soup = BeautifulSoup(resp.text, "html.parser")

# Find CSRF token (common names)
csrf_token = (
    soup.find("input", {{"name": "csrf"}}) or
    soup.find("input", {{"name": "_token"}}) or
    soup.find("input", {{"name": "csrf_token"}}) or
    soup.find("input", {{"name": "authenticity_token"}})
)
token = csrf_token["value"] if csrf_token else None

# Login
login_data = {{
    "{username_field or 'username'}": "your_username",
    "{password_field or 'password'}": "your_password",
}}
if token:
    login_data["csrf_token"] = token

resp = session.post(LOGIN_URL, data=login_data)
print(f"Login status: {{resp.status_code}}")

# Now access protected pages
# resp = session.get("https://example.com/protected")
'''
    
    def generate_pagination_scraper(self, structure: PageStructure, list_selector: str = None) -> str:
        """Generate code for paginated scraping."""
        return f'''import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_URL = "{structure.url}"
session = requests.Session()

def scrape_page(page_num: int) -> list:
    """Scrape a single page."""
    # Adjust URL pattern for pagination
    url = f"{{BASE_URL}}?page={{page_num}}"
    
    resp = session.get(url)
    soup = BeautifulSoup(resp.text, "html.parser")
    
    items = []
    for item in soup.select("{list_selector or '.item'}"):
        # Adjust extraction logic
        title = item.select_one(".title")
        if title:
            items.append({{"title": title.get_text(strip=True)}})
    
    return items


def scrape_all(max_pages: int = 10) -> list:
    """Scrape all pages."""
    all_items = []
    
    for page in range(1, max_pages + 1):
        print(f"Scraping page {{page}}...")
        items = scrape_page(page)
        
        if not items:
            break
        
        all_items.extend(items)
    
    return all_items


if __name__ == "__main__":
    items = scrape_all()
    print(f"Total items: {{len(items)}}")
'''


class RequestBuilder:
    """Build HTTP requests from browser interactions.
    
    Use this to record browser actions and generate code to replicate them.
    """
    
    def __init__(self):
        self.actions: List[Dict[str, Any]] = []
    
    def record(self, action: str, **data):
        """Record an action."""
        self.actions.append({
            "action": action,
            "data": data,
            "timestamp": None  # Could add time
        })
    
    def generate_code(self) -> str:
        """Generate Python code to replicate actions."""
        code = "import requests\n\n"
        code += "session = requests.Session()\n\n"
        
        for action in self.actions:
            if action["action"] == "GET":
                code += f'# GET {action["data"].get("url")}\n'
                code += f'response = session.get("{action["data"].get("url")}")\n\n'
            
            elif action["action"] == "POST":
                code += f'# POST {action["data"].get("url")}\n'
                data = action["data"].get("data", {})
                if data:
                    code += f'data = {json.dumps(data, indent=4)}\n'
                    code += f'response = session.post("{action["data"].get("url")}", data=data)\n'
                else:
                    code += f'response = session.post("{action["data"].get("url")}")\n'
                code += "\n"
            
            elif action["action"] == "CLICK":
                code += f'# Click: {action["data"].get("selector")}\n'
                # Would need more complex logic
                code += "# (Click handling requires re-implementing with requests)\n\n"
        
        return code
    
    def export(self, path: str):
        """Export recorded actions to JSON."""
        with open(path, "w") as f:
            json.dump(self.actions, f, indent=2)
    
    def load(self, path: str):
        """Load actions from JSON."""
        with open(path, "r") as f:
            self.actions = json.load(f)
