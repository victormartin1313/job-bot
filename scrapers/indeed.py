"""Indeed scraper — Playwright for JS-rendered pages."""

from __future__ import annotations

import random
import time

from db import upsert_job, init_db
from matcher import score_job, should_store

SEARCH_QUERIES = [
    "IT audit entry level",
    "accounting information systems associate",
    "technology risk entry level",
    "IT advisory entry level",
    "GRC analyst entry level",
    "systems auditor associate",
]


def _delay(lo: float = 3.0, hi: float = 6.0) -> None:
    time.sleep(random.uniform(lo, hi))


def scrape_indeed(config: dict) -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return 0

    init_db()
    prefs = config.get("preferences", {})
    target_locations = prefs.get("locations", [])
    remote_ok = prefs.get("remote", True)
    location_str = target_locations[0].split(",")[0] if target_locations else ""

    saved = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()

        for query in SEARCH_QUERIES:
            from urllib.parse import urlencode
            params = {"q": query, "l": location_str, "fromage": "14", "sort": "date"}
            url = "https://www.indeed.com/jobs?" + urlencode(params)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
                _delay(3, 5)

                # Dismiss any popups
                try:
                    page.keyboard.press("Escape")
                except Exception:
                    pass

                # Extract job cards
                jobs = page.evaluate("""() => {
                    const cards = document.querySelectorAll('[data-jk], .job_seen_beacon');
                    return Array.from(cards).map(card => {
                        const titleEl = card.querySelector('h2.jobTitle a, a.jcs-JobTitle, [data-testid="job-title"] a');
                        const companyEl = card.querySelector('[data-testid="company-name"], .companyName');
                        const locationEl = card.querySelector('[data-testid="text-location"], .companyLocation');
                        if (!titleEl) return null;
                        const href = titleEl.href || titleEl.getAttribute('href') || '';
                        return {
                            title: titleEl.innerText.trim(),
                            company: companyEl ? companyEl.innerText.trim() : '',
                            location: locationEl ? locationEl.innerText.trim() : '',
                            url: href.startsWith('http') ? href : 'https://www.indeed.com' + href
                        };
                    }).filter(Boolean);
                }""")

                for job in jobs:
                    if not job.get("url") or not job.get("title"):
                        continue
                    # Fetch description
                    desc = ""
                    try:
                        page.goto(job["url"], wait_until="domcontentloaded", timeout=15000)
                        _delay(2, 3)
                        desc = page.evaluate("""() => {
                            const el = document.querySelector('#jobDescriptionText, .jobsearch-jobDescriptionText');
                            return el ? el.innerText.trim() : '';
                        }""") or ""
                    except Exception:
                        pass

                    sc = score_job(job["title"], desc, job["location"], target_locations, remote_ok, job.get("company", ""))
                    if should_store(sc):
                        upsert_job(
                            source="indeed",
                            title=job["title"],
                            company=job["company"],
                            url=job["url"],
                            score=sc,
                            location=job["location"],
                            description=desc,
                        )
                        saved += 1
                    _delay(2, 4)

                # Go back to results for next query
            except Exception as exc:
                print(f"  Indeed query '{query}' failed: {exc}")
            _delay(4, 7)

        browser.close()
    return saved
