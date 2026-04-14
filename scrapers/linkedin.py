"""LinkedIn scraper — Playwright with persistent session (login once, reuse forever)."""

from __future__ import annotations

import random
import time
from pathlib import Path

from db import upsert_job, init_db
from matcher import score_job, should_store

SESSION_DIR = str(Path(__file__).parent.parent / ".linkedin_session")

# Firm-specific searches by LinkedIn company ID — accounting firms only
FIRM_SEARCHES = [
    ("Deloitte",       "https://www.linkedin.com/jobs/search/?keywords=IT+audit+associate+entry+level&f_C=1038&f_E=2&f_TPR=r2592000"),
    ("EY",             "https://www.linkedin.com/jobs/search/?keywords=IT+audit+associate+entry+level&f_C=2784&f_E=2&f_TPR=r2592000"),
    ("PwC",            "https://www.linkedin.com/jobs/search/?keywords=IT+audit+associate+entry+level&f_C=3127&f_E=2&f_TPR=r2592000"),
    ("KPMG",           "https://www.linkedin.com/jobs/search/?keywords=IT+audit+associate+entry+level&f_C=2364&f_E=2&f_TPR=r2592000"),
    ("RSM",            "https://www.linkedin.com/jobs/search/?keywords=IT+audit+associate+entry+level&f_C=3302&f_E=2&f_TPR=r2592000"),
    ("Grant Thornton", "https://www.linkedin.com/jobs/search/?keywords=IT+audit+associate+entry+level&f_C=3014&f_E=2&f_TPR=r2592000"),
    ("BDO",            "https://www.linkedin.com/jobs/search/?keywords=IT+audit+associate+entry+level&f_C=3299&f_E=2&f_TPR=r2592000"),
    ("Baker Tilly",    "https://www.linkedin.com/jobs/search/?keywords=IT+audit+associate+entry+level&f_C=4793&f_E=2&f_TPR=r2592000"),
]


def _delay(lo: float = 2.0, hi: float = 4.0) -> None:
    time.sleep(random.uniform(lo, hi))


def _login(page, email: str, password: str) -> bool:
    page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=15000)
    _delay(2, 3)
    page.fill("#username", email)
    page.fill("#password", password)
    page.click("button[type='submit']")
    _delay(4, 5)
    return "feed" in page.url or "jobs" in page.url


def _extract_jobs(page) -> list[dict]:
    return page.evaluate(r"""() => {
        const cards = document.querySelectorAll('li[data-occludable-job-id]');
        const noise = /alumni|alum|connections|promoted|benefit|verification/i;
        return Array.from(cards).map(card => {
            const linkEl = card.querySelector('a[href*="/jobs/view/"]');
            if (!linkEl) return null;
            const url = (linkEl.href || '').split('?')[0];
            const titleEl = card.querySelector('span[aria-hidden="true"]');
            const title = titleEl ? titleEl.innerText.trim() : '';
            if (!title) return null;
            const infoSpans = Array.from(
                card.querySelectorAll('span:not([aria-hidden="true"]):not(.visually-hidden)')
            ).map(s => s.innerText.trim()).filter(t => t && t.length > 1 && !noise.test(t));
            const company = infoSpans[0] || '';
            const location = infoSpans.find(t =>
                /,[ ]*[A-Z]{2}|remote|hybrid|on.site/i.test(t) && t !== company
            ) || infoSpans[1] || '';
            return {title, company, location, url};
        }).filter(Boolean);
    }""") or []


def _get_description(page, url: str) -> str:
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=10000)
        _delay(1.5, 2.5)
        return page.evaluate(r"""() => {
            const el = document.querySelector('#job-details, .jobs-description__content');
            return el ? el.innerText.trim().slice(0, 4000) : '';
        }""") or ""
    except Exception:
        return ""


def _scrape_url(page, url: str, label: str,
                target_locations: list, remote_ok: bool,
                company_hint: str = "") -> int:
    saved = 0
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=12000)
        _delay(2, 3)
        page.evaluate("window.scrollBy(0, 800)")
        _delay(1, 1.5)
        jobs = _extract_jobs(page)
        if jobs:
            print(f"    {len(jobs)} cards — ", end="", flush=True)
        for job in jobs:
            company = job["company"] or company_hint
            pre = score_job(job["title"], "", job["location"], target_locations, remote_ok, company)
            if pre == 0:
                continue
            desc = _get_description(page, job["url"]) if pre >= 30 else ""
            sc = score_job(job["title"], desc, job["location"], target_locations, remote_ok, company)
            if should_store(sc):
                upsert_job(source="linkedin", title=job["title"], company=company,
                           url=job["url"], score=sc, location=job["location"], description=desc)
                print(f"[{sc:.0f}]{job['title'][:30]} ", end="", flush=True)
                saved += 1
        if jobs:
            print()
    except Exception as exc:
        print(f"    skip: {exc}")
    return saved


def scrape_linkedin(config: dict) -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return 0

    init_db()
    prefs = config.get("preferences", {})
    target_locations = prefs.get("locations", [])
    remote_ok = prefs.get("remote", False)
    platforms = config.get("platforms", {})
    email = platforms.get("linkedin_email", "")
    password = platforms.get("linkedin_password", "")

    saved = 0
    with sync_playwright() as p:
        # Use persistent context so session is saved between runs
        browser = p.chromium.launch_persistent_context(
            SESSION_DIR,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = browser.new_page()

        # Check if already logged in
        page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=12000)
        _delay(2, 3)
        if "feed" not in page.url:
            print("  Logging in to LinkedIn…")
            if not _login(page, email, password):
                print("  Login failed. Check credentials or complete verification in the browser.")
                _delay(20, 30)  # pause for manual verification if needed
                if "feed" not in page.url:
                    browser.close()
                    return 0

        # Firm searches — accounting firms only, by company ID
        for firm_name, url in FIRM_SEARCHES:
            print(f"  {firm_name}: ", end="", flush=True)
            saved += _scrape_url(page, url, firm_name, target_locations, remote_ok,
                                 company_hint=firm_name)
            _delay(3, 5)

        browser.close()
    return saved
