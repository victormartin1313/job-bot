"""Handshake scraper — Playwright with user credentials."""

from __future__ import annotations

import random
import time

from db import upsert_job, init_db
from matcher import score_job, should_store

HANDSHAKE_BASE = "https://app.joinhandshake.com"

SEARCH_TERMS = [
    "IT audit",
    "accounting information systems",
    "technology risk",
    "IT advisory",
]


def _random_delay(lo: float = 3.0, hi: float = 6.0) -> None:
    time.sleep(random.uniform(lo, hi))


def _login(page, email: str, password: str) -> bool:
    try:
        page.goto(f"{HANDSHAKE_BASE}/login", wait_until="domcontentloaded", timeout=20000)
        _random_delay(2, 3)
        page.fill("input[name='email'], input[type='email']", email)
        _random_delay(1, 2)
        page.fill("input[name='password'], input[type='password']", password)
        _random_delay(1, 2)
        page.click("button[type='submit']")
        page.wait_for_load_state("networkidle", timeout=15000)
        return True
    except Exception as exc:
        print(f"Handshake login failed: {exc}")
        return False


def _extract_jobs(page) -> list[dict]:
    jobs = []
    cards = page.query_selector_all("div[data-hook='job-card'], li.job-listing-card")
    for card in cards:
        try:
            title_el = card.query_selector("a[data-hook='job-title'], a.job-title")
            company_el = card.query_selector("span[data-hook='employer-name'], .employer-name")
            location_el = card.query_selector("span[data-hook='location'], .location")
            if not title_el:
                continue
            title = title_el.inner_text().strip()
            company = company_el.inner_text().strip() if company_el else ""
            location = location_el.inner_text().strip() if location_el else ""
            href = title_el.get_attribute("href") or ""
            if href and not href.startswith("http"):
                href = HANDSHAKE_BASE + href
            if not href:
                continue
            jobs.append({"title": title, "company": company,
                         "location": location, "url": href, "description": ""})
        except Exception:
            continue
    return jobs


def _get_description(page, url: str) -> str:
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
        _random_delay(2, 3)
        el = page.query_selector("div[data-hook='job-description'], .job-description")
        return el.inner_text().strip() if el else ""
    except Exception:
        return ""


def scrape_handshake(config: dict) -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return 0

    init_db()
    platforms = config.get("platforms", {})
    email = platforms.get("handshake_email", "")
    password = platforms.get("handshake_password", "")
    prefs = config.get("preferences", {})
    target_locations = prefs.get("locations", [])
    remote_ok = prefs.get("remote", True)

    if not email or not password:
        print("Handshake credentials not configured — skipping.")
        return 0

    saved = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        if not _login(page, email, password):
            browser.close()
            return 0

        for term in SEARCH_TERMS:
            search_url = (
                f"{HANDSHAKE_BASE}/jobs?query={term.replace(' ', '%20')}"
                "&job_type%5B%5D=full_time&employment_type_names%5B%5D=Entry+Level"
            )
            try:
                page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
                _random_delay(3, 5)
                # Scroll to load more
                for _ in range(2):
                    page.evaluate("window.scrollBy(0, 1000)")
                    _random_delay(1, 2)

                jobs = _extract_jobs(page)
                for job in jobs:
                    desc = _get_description(page, job["url"])
                    job["description"] = desc
                    sc = score_job(
                        job["title"], desc, job["location"],
                        target_locations, remote_ok
                    )
                    if should_store(sc):
                        upsert_job(
                            source="handshake",
                            title=job["title"],
                            company=job["company"],
                            url=job["url"],
                            score=sc,
                            location=job["location"],
                            description=desc,
                        )
                        saved += 1
                    _random_delay(3, 5)
            except Exception as exc:
                print(f"Handshake query '{term}' failed: {exc}")
            _random_delay(5, 8)

        browser.close()

    return saved
