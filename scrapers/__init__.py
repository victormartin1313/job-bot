"""Scraper orchestrator — run_all_scrapers() calls every source."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    pass

console = Console()


def run_all_scrapers(config: dict) -> int:
    """Run all scrapers and return total new jobs saved."""
    from scrapers.linkedin import scrape_linkedin
    from scrapers.indeed import scrape_indeed
    from scrapers.handshake import scrape_handshake
    from scrapers.firms import run_firm_scrapers

    total = 0

    sources = [
        ("LinkedIn", scrape_linkedin),
        ("Indeed", scrape_indeed),
        ("Handshake", scrape_handshake),
        ("Firm career pages", run_firm_scrapers),
    ]

    for name, fn in sources:
        console.print(f"[bold cyan]→ Scraping {name}…[/bold cyan]")
        try:
            count = fn(config)
            console.print(f"  [green]✓ {name}: {count} jobs saved[/green]")
            total += count
        except Exception as exc:
            console.print(f"  [red]✗ {name} failed: {exc}[/red]")
        time.sleep(2)

    return total
