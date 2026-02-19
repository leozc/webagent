# WebAgent

AI agent browser automation toolkit with stealth capabilities.

## Installation

```bash
pip install -e .
```

## Environment Variables

```bash
# Search (choose one or more)
GOOGLE_CS_API_KEY=your_google_api_key      # Free 100/day - https://developers.google.com/custom-search/v1/overview
GOOGLE_CS_CX=your_search_engine_id         # From https://programmablesearchengine.google.com/
SERPAPI_KEY=your_serpapi_key               # Paid ~$50/month - https://serpapi.com/
BING_API_KEY=your_bing_key                 # Free 1000/month - https://www.microsoft.com/bing/apis/

# Captcha Solving
TWOCAPTCHA_KEY=your_2captcha_key           # https://2captcha.com/
ANTICAPTCHA_KEY=your_anticaptcha_key       # https://anti-captcha.com/

# Browser (optional)
UNDETECTED_DRIVER=1  # Use undetected-chromedriver
```

## Quick Start

### Search (get Google-like results without browser)

```python
from webagent.search import search

# Auto-detect best available backend
results = search("python tutorials", num=10)

# Or specify provider
results = search("python tutorials", provider="serpapi", num=10)
```

### Browser Automation

```python
from webagent.browser import StealthBrowser

browser = StealthBrowser()
browser.go("https://example.com")

# Interact
browser.click("#submit-button")
browser.type("#search", "query")
browser.solve_captcha()  # Uses 2Captcha
```

### Captcha Solving

```python
from webagent.captcha import CaptchaSolver

solver = CaptchaSolver(provider="2captcha")
solver.solve_image("captcha.png")
solver.solve_recaptcha("sitekey", "https://site.com")
```

## Search Backends

| Provider | Cost | Reliability | Notes |
|----------|------|-------------|-------|
| SerpAPI | Paid | ⭐⭐⭐⭐⭐ | Best results, handles blocking |
| Google CS | Free (100/day) | ⭐⭐⭐⭐ | Requires setup |
| Bing API | Free (1000/month) | ⭐⭐⭐⭐ | Good alternative |
| DuckDuckGo | Free | ⭐⭐ | Unreliable lately |

## Modules

- `webagent.search` - Search backends (Google, SerpAPI, Bing, DuckDuckGo)
- `webagent.browser` - Browser automation with stealth features
- `webagent.captcha` - Captcha solving (reCAPTCHA, hCaptcha, image)
- `webagent.utils` - Helper functions
