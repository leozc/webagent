"""Network monitoring and request capture for browser."""
import json
import time
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from urllib.parse import urlparse


@dataclass
class NetworkRequest:
    """Captured network request."""
    id: str
    url: str
    method: str
    headers: Dict[str, str]
    post_data: str = None
    timestamp: float = field(default_factory=time.time)
    response_status: int = None
    response_body: str = None
    response_headers: Dict[str, str] = None
    duration_ms: float = None
    error: str = None


@dataclass 
class NetworkLog:
    """Complete network log for a page load."""
    requests: List[NetworkRequest] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    _file_handle = None
    _stream_to_file: bool = False
    _max_memory_requests: int = 100  # Keep last N in memory
    
    def get_by_url(self, pattern: str) -> List[NetworkRequest]:
        """Get requests matching URL pattern."""
        return [r for r in self.requests if pattern in r.url]
    
    def get_by_method(self, method: str) -> List[NetworkRequest]:
        """Get requests by HTTP method."""
        return [r for r in self.requests if r.method.upper() == method.upper()]
    
    def get_api_calls(self) -> List[NetworkRequest]:
        """Get likely API calls (XHR/fetch)."""
        api_patterns = ["/api", "/ajax", "/graphql", ".json", "xhr"]
        return [r for r in self.requests 
                if any(p in r.url.lower() for p in api_patterns)]
    
    def get_form_posts(self) -> List[NetworkRequest]:
        """Get form submission POST requests."""
        return self.get_by_method("POST")
    
    def stream_to_file(self, path: str, append: bool = True):
        """Stream requests to file instead of memory.
        
        Use this for long-running monitoring - keeps context light.
        """
        mode = "a" if append else "w"
        self._file_handle = open(path, mode)
        self._stream_to_file = True
        
        # Write header if new file
        if not append:
            self._file_handle.write('{"requests": [\n')
        elif append:
            self._file_handle.seek(0, 2)  # End of file
            # Check if needs comma
            if self._file_handle.tell() > 10:
                self._file_handle.write(',\n')
    
    def _add_request(self, req: NetworkRequest):
        """Add request with memory management."""
        if self._stream_to_file and self._file_handle:
            # Write directly to file
            import json
            self._file_handle.write(json.dumps({
                "id": req.id,
                "url": req.url,
                "method": req.method,
                "headers": req.headers,
                "post_data": req.post_data,
                "timestamp": req.timestamp,
                "response_status": req.response_status,
                "response_body": req.response_body[:1000] if req.response_body else None,
                "response_headers": req.response_headers,
                "duration_ms": req.duration_ms,
            }))
            self._file_handle.write(',\n')
            self._file_handle.flush()
        else:
            # In-memory with limit
            self.requests.append(req)
            if len(self.requests) > self._max_memory_requests:
                # Remove oldest
                self.requests.pop(0)
    
    def close(self):
        """Close file handle if streaming."""
        if self._file_handle:
            self._file_handle.write(']}\n')
            self._file_handle.close()
            self._file_handle = None
    
    def set_max_memory(self, n: int):
        """Set max requests to keep in memory."""
        self._max_memory_requests = n
        if len(self.requests) > n:
            self.requests = self.requests[-n:]
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary without full payloads - safe for context."""
        return {
            "total_requests": len(self.requests),
            "api_calls": len(self.get_api_calls()),
            "post_requests": len(self.get_form_posts()),
            "endpoints": list(set(urlparse(r.url).path for r in self.requests[:50])),
            "unique_domains": list(set(urlparse(r.url).netloc for r in self.requests[:50])),
        }
    
    def export_json(self, path: str):
        """Export to JSON file."""
        # Close streaming first
        self.close()
        
        data = {
            "start_time": self.start_time,
            "summary": self.get_summary(),
            "requests": [
                {
                    "id": r.id,
                    "url": r.url,
                    "method": r.method,
                    "headers": r.headers,
                    "post_data": r.post_data,
                    "response_status": r.response_status,
                    "response_body": r.response_body[:5000] if r.response_body else None,
                    "response_headers": r.response_headers,
                    "duration_ms": r.duration_ms,
                }
                for r in self.requests
            ]
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)


class NetworkMonitor:
    """Monitor and capture network requests.
    
    Usage:
        monitor = NetworkMonitor()
        
        # Enable in browser
        browser.page.route("**/*", monitor.handler())
        
        # Or capture after the fact if using CDP
        # monitor.capture_from_browser(browser)
    """
    
    def __init__(self):
        self.log = NetworkLog()
        self._request_id = 0
        self._pending: Dict[str, NetworkRequest] = {}
        self._on_request: Callable[[NetworkRequest], None] = None
        self._on_response: Callable[[NetworkRequest], None] = None
    
    def handler(self):
        """Get Playwright route handler."""
        from playwright.sync_api import Route, Request
        
        def handle(route: Route):
            request = route.request
            
            # Create request log
            req_id = f"req_{self._request_id}"
            self._request_id += 1
            
            post_data = None
            if request.post_data_buffer:
                try:
                    post_data = request.post_data_buffer.decode()
                except:
                    pass
            
            network_req = NetworkRequest(
                id=req_id,
                url=request.url,
                method=request.method,
                headers=dict(request.headers),
                post_data=post_data,
            )
            
            self._pending[req_id] = network_req
            
            # Continue request
            route.continue_()
        
        return handle
    
    def response_handler(self):
        """Get Playwright response handler."""
        from playwright.sync_api import Response, Request
        
        def handle(response: Response):
            request = response.request
            req_id = None
            
            # Find matching request
            for rid, req in self._pending.items():
                if req.url == request.url:
                    req_id = rid
                    break
            
            if req_id and req_id in self._pending:
                req = self._pending.pop(req_id)
                req.response_status = response.status
                req.response_headers = dict(response.headers)
                req.duration_ms = (time.time() - req.timestamp) * 1000
                
                # Try to get body (limited for large responses)
                try:
                    body = response.body()
                    if len(body) < 100000:  # Skip large responses
                        try:
                            req.response_body = body.decode("utf-8")
                        except:
                            req.response_body = body.hex()
                except:
                    pass
                
                self.log._add_request(req)
                
                if self._on_response:
                    self._on_response(req)
        
        return handle
    
    def request_handler(self):
        """Get Playwright request handler."""
        from playwright.sync_api import Request
        
        def handle(request: Request):
            req_id = f"req_{self._request_id}"
            self._request_id += 1
            
            post_data = None
            if request.post_data_buffer:
                try:
                    post_data = request.post_data_buffer.decode()
                except:
                    pass
            
            network_req = NetworkRequest(
                id=req_id,
                url=request.url,
                method=request.method,
                headers=dict(request.headers),
                post_data=post_data,
            )
            
            self._pending[req_id] = network_req
            
            if self._on_request:
                self._on_request(network_req)
        
        return handle
    
    def capture_from_browser(self, browser):
        """Capture network requests from existing browser session.
        
        Note: This requires browser to be started with monitoring enabled.
        For existing browsers, use route() handlers instead.
        """
        if not browser.page:
            raise ValueError("Browser must be Playwright-based")
        
        # Setup handlers
        browser.page.on("request", self.request_handler())
        browser.page.on("response", self.response_handler())
    
    def on_request(self, callback: Callable[[NetworkRequest], None]):
        """Set callback for each request."""
        self._on_request = callback
    
    def on_response(self, callback: Callable[[NetworkRequest], None]):
        """Set callback for each response."""
        self._on_response = callback
    
    def clear(self):
        """Clear captured requests."""
        self.log = NetworkLog()
        self._pending.clear()
        self._request_id = 0
    
    def generate_client_code(self) -> str:
        """Generate Python code to replicate captured API calls.
        
        Analyzes captured requests and generates a client class.
        """
        api_calls = self.log.get_api_calls()
        posts = self.log.get_form_posts()
        
        code = '''"""Auto-generated API client from network capture."""
import requests
from urllib.parse import urljoin

BASE_URL = ""  # Set this

session = requests.Session()

# Captured headers:
headers = {
    # Add headers from capture
}

'''
        
        # Generate methods for POST requests
        for req in posts[:10]:
            parsed = urlparse(req.url)
            endpoint = parsed.path
            method_name = endpoint.replace("/", "_").strip("_") or "submit"
            
            code += f'''
def {method_name}(data: dict) -> requests.Response:
    """{req.method} {endpoint}"""
    url = urljoin(BASE_URL, "{endpoint}")
    return session.post(url, data=data, headers=headers)

'''
        
        # Generate API methods
        for req in api_calls[:10]:
            parsed = urlparse(req.url)
            endpoint = parsed.path
            method_name = endpoint.replace("/", "_").strip("_") or "api_call"
            
            code += f'''
def {method_name}() -> dict:
    """GET {endpoint}"""
    url = urljoin(BASE_URL, "{endpoint}")
    resp = session.get(url, headers=headers)
    return resp.json()

'''
        
        code += "\nif __name == '__main__':\n    pass\n"
        
        return code


# Extend StealthBrowser with network monitoring
def enable_network_monitoring(browser):
    """Enable network monitoring on a browser instance.
    
    Args:
        browser: StealthBrowser instance
    
    Returns:
        NetworkMonitor instance
    """
    monitor = NetworkMonitor()
    
    if browser.page:
        browser.page.on("request", monitor.request_handler())
        browser.page.on("response", monitor.response_handler())
    else:
        raise ValueError("Browser must use Playwright (page-based)")
    
    browser._network_monitor = monitor
    return monitor
