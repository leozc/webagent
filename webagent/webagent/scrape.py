"""Background scraper for long-running tasks.

Runs as a separate process/agent to avoid blocking the main conversation
and filling up context window. Results are saved to files.
"""
import os
import sys
import json
import time
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class ScrapedItem:
    """Single scraped item."""
    id: str
    data: Dict[str, Any]
    timestamp: float


@dataclass
class ScrapeJob:
    """Scraping job configuration."""
    name: str
    url: str
    config: Dict[str, Any]
    max_pages: int = 10
    rate_limit: float = 1.0  # seconds between requests
    output_dir: str = "./scraped_data"
    proxy: str = None


class BackgroundScraper:
    """Run scraping jobs in background, save results to files.
    
    Usage:
        scraper = BackgroundScraper()
        
        # Start a job
        job = ScrapeJob(
            name="products",
            url="https://site.com/products",
            config={"selector": ".product"},
            max_pages=50,
        )
        scraper.run(job)
        
        # Results saved to output_dir/name/timestamp/
    """
    
    def __init__(self, output_dir: str = "./scraped_data"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def run(self, job: ScrapeJob) -> Path:
        """Run scraping job and save results.
        
        Returns:
            Path to results directory
        """
        from webagent import StealthClient
        from bs4 import BeautifulSoup
        
        # Setup output
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        job_dir = self.output_dir / job.name / timestamp
        job_dir.mkdir(parents=True, exist_ok=True)
        
        items_file = job_dir / "items.jsonl"
        meta_file = job_dir / "metadata.json"
        
        # Metadata
        meta = {
            "name": job.name,
            "url": job.url,
            "started_at": timestamp,
            "max_pages": job.max_pages,
            "config": job.config,
        }
        
        client = StealthClient()
        
        if job.proxy:
            client.config.proxy = job.proxy
        
        # Setup rate limiting
        last_request = 0
        
        items_scraped = 0
        errors = []
        
        try:
            for page in range(1, job.max_pages + 1):
                # Rate limit
                elapsed = time.time() - last_request
                if elapsed < job.rate_limit:
                    time.sleep(job.rate_limit - elapsed)
                
                last_request = time.time()
                
                # Build URL
                page_url = job.url
                if "?" in page_url:
                    page_url += f"&page={page}"
                else:
                    page_url += f"?page={page}"
                
                try:
                    resp = client.get(page_url)
                    resp.raise_for_status()
                    
                    soup = BeautifulSoup(resp.text, "html.parser")
                    
                    # Extract items based on config
                    selector = job.config.get("selector", ".item")
                    elements = soup.select(selector)
                    
                    if not elements:
                        # Try to find pagination
                        break
                    
                    for i, elem in enumerate(elements):
                        item = {
                            "page": page,
                            "position": i,
                            "html": str(elem)[:5000],  # Limit size
                            "text": elem.get_text(strip=True)[:2000],
                        }
                        
                        # Extract specific fields if configured
                        for field in job.config.get("fields", []):
                            field_elem = elem.select_one(field["selector"])
                            item[field["name"]] = field_elem.get_text(strip=True) if field_elem else None
                        
                        # Save to JSONL
                        with open(items_file, "a") as f:
                            f.write(json.dumps(item) + "\n")
                        
                        items_scraped += 1
                    
                    print(f"Page {page}: {len(elements)} items")
                    
                except Exception as e:
                    error = {"page": page, "error": str(e)}
                    errors.append(error)
                    print(f"Page {page} error: {e}")
                    
                    if job.config.get("stop_on_error"):
                        break
                    
                    time.sleep(5)  # Back off on error
            
            # Save final metadata
            meta.update({
                "completed_at": datetime.now().isoformat(),
                "items_scraped": items_scraped,
                "pages_completed": page,
                "errors": errors[:10],  # Keep first 10 errors
                "status": "completed" if items_scraped > 0 else "failed",
            })
            
        except KeyboardInterrupt:
            meta["status"] = "interrupted"
            meta["items_scraped"] = items_scraped
        
        # Write metadata
        with open(meta_file, "w") as f:
            json.dump(meta, f, indent=2)
        
        print(f"\nDone! Scraped {items_scraped} items to {job_dir}")
        
        return job_dir


def run_cli():
    """CLI entry point for background scraping.
    
    Usage:
        python -m webagent.scrape --url https://site.com --name products \
            --selector ".product" --pages 50 --rate-limit 2
    """
    parser = argparse.ArgumentParser(description="Background web scraper")
    parser.add_argument("--url", required=True, help="Base URL to scrape")
    parser.add_argument("--name", required=True, help="Job name for output")
    parser.add_argument("--selector", default=".item", help="CSS selector for items")
    parser.add_argument("--pages", type=int, default=10, help="Max pages")
    parser.add_argument("--rate-limit", type=float, default=1.0, help="Seconds between requests")
    parser.add_argument("--output", default="./scraped_data", help="Output directory")
    parser.add_argument("--proxy", help="Proxy URL")
    parser.add_argument("--field", action="append", help="Fields to extract (name:selector)")
    
    args = parser.parse_args()
    
    # Parse fields
    fields = []
    if args.field:
        for f in args.field:
            if ":" in f:
                name, selector = f.split(":", 1)
                fields.append({"name": name, "selector": selector})
    
    job = ScrapeJob(
        name=args.name,
        url=args.url,
        config={
            "selector": args.selector,
            "fields": fields,
        },
        max_pages=args.pages,
        rate_limit=args.rate_limit,
        output_dir=args.output,
        proxy=args.proxy,
    )
    
    scraper = BackgroundScraper(output_dir=args.output)
    result_dir = scraper.run(job)
    
    print(f"\nResults: {result_dir}")


# Quick function to spawn background scrape
def scrape_background(url: str, name: str, **kwargs) -> str:
    """Spawn background scrape job.
    
    Returns path where results will be saved.
    """
    import uuid
    
    job = ScrapeJob(
        name=name,
        url=url,
        config=kwargs.get("config", {}),
        max_pages=kwargs.get("max_pages", 10),
        rate_limit=kwargs.get("rate_limit", 1.0),
        output_dir=kwargs.get("output_dir", "./scraped_data"),
        proxy=kwargs.get("proxy"),
    )
    
    # Save job config
    job_id = str(uuid.uuid4())[:8]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    job_dir = Path(job.output_dir) / job.name / timestamp
    job_dir.mkdir(parents=True, exist_ok=True)
    
    job_file = job_dir / "job.json"
    with open(job_file, "w") as f:
        json.dump({
            "job_id": job_id,
            "config": asdict(job),
            "created_at": datetime.now().isoformat(),
        }, f, indent=2)
    
    # Run in background (this would be subprocess in real usage)
    # For now return the path where results will go
    return str(job_dir)


# Example for the AI to use - spawns sub-agent for long running
def spawn_scrape_agent(url: str, instructions: str, name: str = None) -> str:
    """Spawn a sub-agent to handle long-running scrape.
    
    The AI should use this for scraping tasks that would otherwise
    block the conversation for many turns.
    
    Returns:
        Session key for the spawned agent
    """
    # This would integrate with OpenClaw's sessions_spawn
    # Placeholder for the concept
    return f"scraper_{name or url[:20]}"
