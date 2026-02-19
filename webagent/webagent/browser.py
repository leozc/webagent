"""Browser automation with stealth capabilities."""
import os
import time
import random
import json
from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass, field
from urllib.parse import urlparse, urljoin

# Try to import browser automation libraries
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.chrome.service import Service
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

try:
    from playwright.sync_api import sync_playwright, Page, Browser
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


@dataclass
class BrowserConfig:
    """Configuration for stealth browser."""
    # Browser options
    headless: bool = False
    user_data_dir: Optional[str] = None
    
    # Stealth options
    disable_webdriver: bool = True
    randomize_window_size: bool = True
    randomize_user_agent: bool = True
    block_images: bool = False
    block_css: bool = False
    
    # Human-like behavior
    human_typing_speed: bool = True
    min_typing_delay: float = 0.05
    max_typing_delay: float = 0.15
    human_click: bool = True
    random_mouse_movements: bool = True
    
    # Timeouts
    default_timeout: int = 30
    page_load_timeout: int = 60
    
    # Proxy
    proxy: Optional[str] = None  # "http://user:pass@host:port"
    
    # Extensions
    extensions: List[str] = field(default_factory=list)


class StealthBrowser:
    """Stealth browser for web scraping and automation.
    
    Uses Selenium or Playwright with anti-detection features.
    """
    
    # Common user agents for randomization
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    ]
    
    def __init__(self, config: BrowserConfig = None):
        self.config = config or BrowserConfig()
        self.driver = None
        self.playwright = None
        self.browser = None
        self.page = None
        
        # Use Playwright by default if available, otherwise Selenium
        if PLAYWRIGHT_AVAILABLE:
            self._init_playwright()
        elif SELENIUM_AVAILABLE:
            self._init_selenium()
        else:
            raise RuntimeError("Neither Playwright nor Selenium is available. Install one: pip install playwright && playwright install chromium")
    
    def _init_playwright(self):
        """Initialize Playwright browser."""
        self.playwright = sync_playwright().start()
        
        # Launch browser
        launch_options = {
            "headless": self.config.headless,
            "args": self._get_stealth_args()
        }
        
        if self.config.proxy:
            launch_options["proxy"] = {
                "server": self.config.proxy
            }
        
        self.browser = self.playwright.chromium.launch(**launch_options)
        
        # Create context
        context_options = self._get_context_options()
        self.context = self.browser.new_context(**context_options)
        
        # Create page
        self.page = self.context.new_page()
        self._setup_page_handlers()
    
    def _init_selenium(self):
        """Initialize Selenium browser."""
        options = ChromeOptions()
        
        if self.config.headless:
            options.add_argument("--headless=new")
        
        # Stealth arguments
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument(f"--user-agent={self._get_user_agent()}")
        
        # Disable webdriver flag
        if self.config.disable_webdriver:
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)
        
        # Block images/css for speed
        if self.config.block_images:
            prefs = {"profile.managed_default_content_settings.images": 2}
            options.add_experimental_option("prefs", prefs)
        
        # Proxy
        if self.config.proxy:
            options.add_argument(f"--proxy-server={self.config.proxy}")
        
        # Extensions
        for ext in self.config.extensions:
            options.add_extension(ext)
        
        self.driver = webdriver.Chrome(options=options)
        
        # Remove webdriver property
        if self.config.disable_webdriver:
            self.driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
        
        self.driver.set_page_load_timeout(self.config.page_load_timeout)
    
    def _get_stealth_args(self) -> List[str]:
        """Get stealth arguments for Playwright."""
        args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process",
            "--allow-running-insecure-content",
            "--disable-extensions",
            "--disable-plugins",
            "--disable-default-apps",
            "--disable-background-networking",
            "--disable-sync",
            "--metrics-recording-only",
            "--mute-audio",
            "--no-first-run",
            "--safebrowsing-disable-auto-update",
        ]
        
        if self.config.block_images:
            args.append("--blink-settings=imagesEnabled=false")
        
        return args
    
    def _get_context_options(self) -> Dict[str, Any]:
        """Get context options for Playwright."""
        options = {}
        
        # User agent
        options["user_agent"] = self._get_user_agent()
        
        # Viewport
        if self.config.randomize_window_size:
            width = random.randint(1280, 1920)
            height = random.randint(720, 1080)
        else:
            width, height = 1920, 1080
        
        options["viewport"] = {"width": width, "height": height}
        
        # Locale
        options["locale"] = "en-US"
        options["timezone_id"] = "America/New_York"
        
        # Permissions
        options["permissions"] = ["geolocation"]
        
        # Extra HTTP headers
        options["extra_http_headers"] = {
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        }
        
        return options
    
    def _get_user_agent(self) -> str:
        """Get random user agent."""
        if self.config.randomize_user_agent:
            return random.choice(self.USER_AGENTS)
        return self.USER_AGENTS[0]
    
    def _setup_page_handlers(self):
        """Setup page event handlers."""
        if not self.page:
            return
        
        # Handle dialogs
        self.page.on("dialog", lambda dialog: dialog.dismiss())
        
        # Handle console messages (for debugging)
        # self.page.on("console", lambda msg: print(f"[Browser Console] {msg.type}: {msg.text}"))
    
    # ============ Navigation ============
    
    def go(self, url: str, wait_until: str = "domcontentloaded", timeout: int = None):
        """Navigate to URL.
        
        Args:
            url: Target URL
            wait_until: What to wait for - "load", "domcontentloaded", "networkidle"
            timeout: Timeout in seconds
        """
        timeout = timeout or self.config.default_timeout
        
        if self.page:
            self.page.goto(url, wait_until=wait_until, timeout=timeout * 1000)
            self._apply_stealth_js()
        else:
            self.driver.get(url)
            self._apply_stealth_js_selenium()
        
        # Human-like delay
        time.sleep(random.uniform(0.5, 1.5))
    
    def _apply_stealth_js(self):
        """Apply stealth JavaScript to page."""
        if not self.page:
            return
        
        # Override webdriver property
        self.page.evaluate("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        # Add plugins
        self.page.evaluate("""
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
        """)
        
        # Add languages
        self.page.evaluate("""
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
        """)
    
    def _apply_stealth_js_selenium(self):
        """Apply stealth JavaScript via Selenium."""
        if not self.driver:
            return
        
        self.driver.execute_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
    
    def refresh(self):
        """Refresh page."""
        if self.page:
            self.page.reload()
        else:
            self.driver.refresh()
        time.sleep(random.uniform(0.3, 0.8))
    
    def back(self):
        """Go back in history."""
        if self.page:
            self.page.go_back()
        else:
            self.driver.back()
        time.sleep(random.uniform(0.3, 0.8))
    
    def forward(self):
        """Go forward in history."""
        if self.page:
            self.page.go_forward()
        else:
            self.driver.forward()
        time.sleep(random.uniform(0.3, 0.8))
    
    # ============ Interaction ============
    
    def click(self, selector: str, timeout: int = None):
        """Click element.
        
        Args:
            selector: CSS selector or XPath
            timeout: Timeout in seconds
        """
        timeout = timeout or self.config.default_timeout
        
        if self.page:
            element = self.page.wait_for_selector(selector, timeout=timeout * 1000)
            
            if self.config.human_click:
                # Human-like click with random offset
                box = element.bounding_box
                if box:
                    x = box["x"] + box["width"] / 2 + random.randint(-5, 5)
                    y = box["y"] + box["height"] / 2 + random.randint(-5, 5)
                    
                    # Random mouse movement
                    if self.config.random_mouse_movements:
                        self._human_mouse_move(x, y)
                    
                    self.page.mouse.click(x, y)
            else:
                element.click()
        else:
            element = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
            element.click()
        
        time.sleep(random.uniform(0.1, 0.3))
    
    def _human_mouse_move(self, target_x: int, target_y: int):
        """Move mouse in human-like manner."""
        if not self.page:
            return
        
        # Start from random position
        current = self.page.mouse.position
        start_x, start_y = current["x"], current["y"]
        
        # Add intermediate points
        steps = random.randint(5, 15)
        for i in range(steps):
            progress = (i + 1) / steps
            x = start_x + (target_x - start_x) * progress + random.randint(-10, 10)
            y = start_y + (target_y - start_y) * progress + random.randint(-10, 10)
            self.page.mouse.move(x, y)
            time.sleep(random.uniform(0.01, 0.03))
    
    def type(self, selector: str, text: str, clear_first: bool = True, timeout: int = None):
        """Type text into element.
        
        Args:
            selector: CSS selector
            text: Text to type
            clear_first: Clear input before typing
            timeout: Timeout in seconds
        """
        timeout = timeout or self.config.default_timeout
        
        if self.page:
            element = self.page.wait_for_selector(selector, timeout=timeout * 1000)
            
            if clear_first:
                element.fill("")
            
            if self.config.human_typing_speed:
                # Type character by character with random delays
                for char in text:
                    element.type(char, delay=random.randint(50, 150))
            else:
                element.fill(text)
        else:
            element = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
            if clear_first:
                element.clear()
            element.send_keys(text)
        
        time.sleep(random.uniform(0.1, 0.3))
    
    def press(self, key: str):
        """Press keyboard key.
        
        Args:
            key: Key name (e.g., "Enter", "Tab", "Escape")
        """
        if self.page:
            self.page.keyboard.press(key)
        else:
            from selenium.webdriver.common.keys import Keys
            key_map = {"Enter": Keys.RETURN, "Tab": Keys.TAB, "Escape": Keys.ESCAPE}
            self.driver.switch_to.active_element.send_keys(key_map.get(key, key))
        
        time.sleep(random.uniform(0.1, 0.2))
    
    def select(self, selector: str, value: str):
        """Select option in dropdown.
        
        Args:
            selector: CSS selector
            value: Value to select
        """
        if self.page:
            self.page.select_option(selector, value)
        else:
            from selenium.webdriver.support.ui import Select
            element = self.driver.find_element(By.CSS_SELECTOR, selector)
            Select(element).select_by_value(value)
        
        time.sleep(random.uniform(0.1, 0.3))
    
    def hover(self, selector: str):
        """Hover over element."""
        if self.page:
            self.page.hover(selector)
        else:
            element = self.driver.find_element(By.CSS_SELECTOR, selector)
            from selenium.webdriver.common.action_chains import ActionChains
            ActionChains(self.driver).move_to_element(element).perform()
        
        time.sleep(random.uniform(0.2, 0.5))
    
    def scroll(self, x: int = 0, y: int = 500):
        """Scroll page.
        
        Args:
            x: Horizontal scroll
            y: Vertical scroll
        """
        if self.page:
            self.page.mouse.wheel(x, y)
        else:
            self.driver.execute_script(f"window.scrollBy({x}, {y})")
        
        time.sleep(random.uniform(0.3, 0.8))
    
    def scroll_to_bottom(self, steps: int = 5):
        """Scroll to bottom of page in steps."""
        for _ in range(steps):
            self.scroll(0, random.randint(300, 800))
    
    # ============ Extraction ============
    
    def text(self, selector: str = None) -> str:
        """Get text content.
        
        Args:
            selector: CSS selector (None = entire page)
        """
        if selector:
            if self.page:
                return self.page.text_content(selector)
            else:
                element = self.driver.find_element(By.CSS_SELECTOR, selector)
                return element.text
        else:
            if self.page:
                return self.page.content()
            else:
                return self.driver.page_source
    
    def html(self, selector: str = None) -> str:
        """Get HTML content."""
        if selector:
            if self.page:
                return self.page.inner_html(selector)
            else:
                element = self.driver.find_element(By.CSS_SELECTOR, selector)
                return element.get_attribute("innerHTML")
        else:
            if self.page:
                return self.page.content()
            else:
                return self.driver.page_source
    
    def attr(self, selector: str, attr: str) -> Optional[str]:
        """Get element attribute."""
        if self.page:
            return self.page.get_attribute(selector, attr)
        else:
            element = self.driver.find_element(By.CSS_SELECTOR, selector)
            return element.get_attribute(attr)
    
    def value(self, selector: str) -> str:
        """Get input value."""
        return self.attr(selector, "value")
    
    def href(self, selector: str) -> str:
        """Get link href."""
        return self.attr(selector, "href")
    
    def src(self, selector: str) -> str:
        """Get image src."""
        return self.attr(selector, "src")
    
    def find(self, selector: str) -> List:
        """Find all matching elements."""
        if self.page:
            return self.page.query_selector_all(selector)
        else:
            return self.driver.find_elements(By.CSS_SELECTOR, selector)
    
    # ============ Waiting ============
    
    def wait_for(self, selector: str, timeout: int = None) -> bool:
        """Wait for element to appear.
        
        Returns:
            True if element found, False if timeout
        """
        timeout = timeout or self.config.default_timeout
        
        if self.page:
            try:
                self.page.wait_for_selector(selector, timeout=timeout * 1000)
                return True
            except:
                return False
        else:
            try:
                WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                return True
            except:
                return False
    
    def wait_for_navigation(self, timeout: int = None):
        """Wait for navigation to complete."""
        timeout = timeout or self.config.default_timeout
        
        if self.page:
            self.page.wait_for_load_state("networkidle", timeout=timeout * 1000)
        else:
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
    
    def wait_for_url(self, pattern: str, timeout: int = None) -> bool:
        """Wait for URL to match pattern.
        
        Args:
            pattern: URL pattern (string or regex)
            timeout: Timeout in seconds
        """
        timeout = timeout or self.config.default_timeout
        
        if self.page:
            try:
                self.page.wait_for_url(pattern, timeout=timeout * 1000)
                return True
            except:
                return False
        else:
            import re
            start = time.time()
            while time.time() - start < timeout:
                if re.search(pattern, self.driver.current_url):
                    return True
                time.sleep(0.1)
            return False
    
    # ============ Screenshot & Debugging ============
    
    def screenshot(self, path: str = None, selector: str = None) -> Optional[bytes]:
        """Take screenshot.
        
        Args:
            path: File path to save (None = return bytes)
            selector: Element to screenshot (None = entire page)
        """
        if self.page:
            if selector:
                element = self.page.query_selector(selector)
                if element:
                    return element.screenshot(path=path)
            return self.page.screenshot(path=path)
        else:
            if selector:
                element = self.driver.find_element(By.CSS_SELECTOR, selector)
                return element.screenshot_as_png
            return self.driver.get_screenshot_as_png()
    
    def console(self) -> List[Dict[str, str]]:
        """Get console messages."""
        if not self.page:
            return []
        # This would need to capture console on page event
        return []
    
    # ============ Session Management ============
    
    def cookies(self) -> List[Dict]:
        """Get all cookies."""
        if self.page:
            return self.context.cookies()
        else:
            return [{"name": c["name"], "value": c["value"]} 
                    for c in self.driver.get_cookies()]
    
    def set_cookie(self, name: str, value: str, domain: str = None, **kwargs):
        """Set cookie."""
        cookie = {"name": name, "value": value}
        if domain:
            cookie["domain"] = domain
        cookie.update(kwargs)
        
        if self.page:
            self.context.add_cookies([cookie])
        else:
            self.driver.add_cookie(cookie)
    
    def delete_cookie(self, name: str):
        """Delete cookie."""
        if self.page:
            self.context.clear_cookies()
        else:
            self.driver.delete_cookie(name)
    
    def clear_cookies(self):
        """Clear all cookies."""
        if self.page:
            self.context.clear_cookies()
        else:
            self.driver.delete_all_cookies()
    
    # ============ Session Persistence ============
    
    def save_session(self, path: str):
        """Save session (cookies, localStorage, sessionStorage) to file.
        
        Args:
            path: File path to save session
        """
        session_data = {
            "cookies": self.cookies(),
            "url": self.url,
            "title": self.title,
            "localStorage": None,
            "sessionStorage": None,
        }
        
        # Try to get storage
        if self.page:
            try:
                session_data["localStorage"] = self.page.evaluate("() => JSON.stringify(localStorage)")
                session_data["sessionStorage"] = self.page.evaluate("() => JSON.stringify(sessionStorage)")
            except:
                pass
        
        with open(path, "w") as f:
            json.dump(session_data, f, indent=2)
    
    def load_session(self, path: str):
        """Load session from file.
        
        Args:
            path: File path to load session from
        """
        with open(path, "r") as f:
            session_data = json.load(f)
        
        # Restore cookies
        if session_data.get("cookies"):
            if self.page:
                self.context.add_cookies(session_data["cookies"])
            else:
                for cookie in session_data["cookies"]:
                    self.driver.add_cookie(cookie)
        
        # Restore storage
        if self.page:
            if session_data.get("localStorage"):
                try:
                    self.page.evaluate(f"() => {{ localStorage = {session_data['localStorage']}; }}")
                except:
                    pass
            
            if session_data.get("sessionStorage"):
                try:
                    self.page.evaluate(f"() => {{ sessionStorage = {session_data['sessionStorage']}; }}")
                except:
                    pass
    
    # ============ Navigation & Frames ============
    
    def switch_to_frame(self, selector: str = None, index: int = None):
        """Switch to frame."""
        if self.page:
            if selector:
                frame = self.page.frame(name=selector) or self.page.frame(url=selector)
            elif index is not None:
                frame = self.page.frames[index]
        else:
            if selector:
                self.driver.switch_to.frame(selector)
            elif index is not None:
                self.driver.switch_to.frame(index)
    
    def switch_to_default(self):
        """Switch back to main document."""
        if self.page:
            pass  # Playwright handles this automatically
        else:
            self.driver.switch_to.default_content()
    
    # ============ JavaScript ============
    
    def eval(self, script: str):
        """Execute JavaScript."""
        if self.page:
            return self.page.evaluate(script)
        else:
            return self.driver.execute_script(script)
    
    def execute(self, script: str):
        """Execute JavaScript (alias for eval)."""
        return self.eval(script)
    
    # ============ Captcha ============
    
    def solve_captcha(self, provider: str = "2captcha", **kwargs) -> Optional[str]:
        """Solve captcha on current page.
        
        Args:
            provider: "2captcha" or "anticaptcha"
            **kwargs: Additional provider-specific options
        
        Returns:
            Solution string or None
        """
        # Import here to avoid circular dependency
        from .captcha import CaptchaSolver
        
        solver = CaptchaSolver(provider=provider, **kwargs)
        
        # Try to find and solve reCAPTCHA
        iframes = self.find("iframe[src*='recaptcha']")
        if iframes:
            # Get sitekey
            sitekey = self.eval("""
                document.querySelector('[data-sitekey]')?.dataset.sitekey ||
                document.querySelector('[src*="recaptcha"]')?.closest('form')?.querySelector('[data-sitekey]')?.dataset.sitekey
            """)
            if sitekey:
                return solver.solve_recaptcha(sitekey, self.url)
        
        # Try hCaptcha
        hiframes = self.find("iframe[src*='hcaptcha']")
        if hiframes:
            sitekey = self.attr("[data-sitekey]", "data-sitekey")
            if sitekey:
                return solver.solve_hcaptcha(sitekey, self.url)
        
        # Try image captcha
        captcha_img = self.find("img[src*='captcha']")
        if captcha_img:
            # Download and solve
            img_url = self.attr(captcha_img[0], "src")
            if img_url:
                return solver.solve_image_url(img_url)
        
        return None
    
    # ============ Properties ============
    
    @property
    def url(self) -> str:
        """Get current URL."""
        if self.page:
            return self.page.url
        return self.driver.current_url
    
    @property
    def title(self) -> str:
        """Get page title."""
        if self.page:
            return self.page.title()
        return self.driver.title
    
    # ============ Cleanup ============
    
    def close(self):
        """Close browser."""
        if self.page:
            self.page.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        if self.driver:
            self.driver.quit()
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()
