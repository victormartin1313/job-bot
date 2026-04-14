"""Big 4 + regional firm career page scrapers using Playwright."""

from __future__ import annotations

import random
import time

from db import upsert_job, init_db
from matcher import score_job, should_store


def _delay(lo: float = 2.0, hi: float = 5.0) -> None:
    time.sleep(random.uniform(lo, hi))


# Each entry: (firm_name, source_key, search_url, job_card_selector, title_sel, location_sel)
FIRM_SEARCHES = [
    {
        "name": "Deloitte",
        "source": "deloitte",
        "url": "https://apply.deloitte.com/careers/SearchJobs/IT%20audit?listtype=1&in_iframe=1",
        "fallback_url": "https://apply.deloitte.com/careers/SearchJobs/technology%20risk?listtype=1&in_iframe=1",
    },
    {
        "name": "EY",
        "source": "ey",
        "url": "https://careers.ey.com/ey/search/?q=IT+audit+associate&alp=6252001&alp_location_id=6252001",
        "fallback_url": "https://careers.ey.com/ey/search/?q=technology+risk+associate&alp=6252001",
    },
    {
        "name": "PwC",
        "source": "pwc",
        "url": "https://jobs.us.pwc.com/search-jobs/IT%20audit/United%20States/932/1/2/6252001/39/-98/50/2",
        "fallback_url": "https://jobs.us.pwc.com/search-jobs/technology%20risk/United%20States/932",
    },
    {
        "name": "KPMG",
        "source": "kpmg",
        "url": "https://www.kpmgcareers.com/search-jobs?keywords=IT+audit&location=United+States",
        "fallback_url": "https://www.kpmgcareers.com/search-jobs?keywords=technology+risk",
    },
    {
        "name": "RSM",
        "source": "rsm",
        "url": "https://rsmus.com/careers/open-positions.html?keyword=IT+Audit",
        "fallback_url": "https://rsmus.com/careers/open-positions.html?keyword=technology+risk",
    },
    {
        "name": "Grant Thornton",
        "source": "grant_thornton",
        "url": "https://www.grantthornton.com/careers/search-jobs#q=IT%20audit&t=Jobs",
        "fallback_url": "https://www.grantthornton.com/careers/search-jobs#q=technology%20risk&t=Jobs",
    },
    {
        "name": "BDO",
        "source": "bdo",
        "url": "https://www.bdo.com/careers/find-your-role?keyword=IT+audit",
        "fallback_url": "https://www.bdo.com/careers/find-your-role?keyword=technology+risk",
    },
    {
        "name": "Moss Adams",
        "source": "moss_adams",
        "url": "https://www.mossadams.com/careers/search-results?keyword=IT+audit",
        "fallback_url": "https://www.mossadams.com/careers/search-results?keyword=advisory",
    },
    {
        "name": "CLA",
        "source": "cla",
        "url": "https://www.claconnect.com/en/careers/job-search?keyword=IT+audit",
        "fallback_url": "https://www.claconnect.com/en/careers/job-search?keyword=technology+risk",
    },
]


def _extract_jobs_generic(page, firm_name: str, base_url: str) -> list[dict]:
    """Generic job extraction using JavaScript — works across most career sites."""
    jobs = page.evaluate(f"""() => {{
        const firmName = {repr(firm_name)};
        const baseUrl = {repr(base_url.split('/careers')[0] if '/careers' in base_url else base_url.split('/jobs')[0] if '/jobs' in base_url else base_url)};

        // Try many common job card / link patterns
        const selectors = [
            'a[href*="/job/"]',
            'a[href*="/jobs/"]',
            'a[href*="/careers/"]',
            'a[href*="jobId"]',
            'a[href*="requisition"]',
            '.job-title a',
            '.jobTitle a',
            'h2 a',
            'h3 a',
            'li.job-result a',
            'div.job-listing a',
            '[data-automation="jobTitle"] a',
            'a[data-jk]',
        ];

        // Partial-match noise phrases (CTAs, nav links, marketing copy)
        const noisePhrases = [
            'talent community', 'bring your own', 'careers site', 'career site',
            'sign in', 'sign up', 'log in', 'log out', 'register',
            'cookie', 'privacy', 'terms of use', 'skip to', 'back to',
            'learn more', 'click here', 'join us', 'save job', 'apply now',
            'our culture', 'who we are', 'life at', 'work at', 'why join',
            'global careers', 'alternative access', 'accessibility',
        ];

        // A real job title must contain at least one of these role words
        const jobWords = [
            'audit', 'risk', 'advisory', 'analyst', 'consultant', 'associate',
            'staff', 'specialist', 'advisor', 'accountant', 'compliance',
            'governance', 'assurance', 'technology', 'information', 'systems',
            'accounting', 'finance', 'tax', 'control', 'security', 'digital',
            'data', 'cyber', 'erp', 'soc ', 'sox', 'manager', 'director',
        ];

        const seen = new Set();
        const results = [];

        for (const sel of selectors) {{
            const els = document.querySelectorAll(sel);
            for (const el of els) {{
                const title = el.innerText.trim();
                if (!title || title.length < 10 || title.length > 120) continue;

                const tl = title.toLowerCase();
                // Reject noise phrases
                if (noisePhrases.some(p => tl.includes(p))) continue;
                // Must contain a job-role word
                if (!jobWords.some(w => tl.includes(w))) continue;

                let href = el.href || el.getAttribute('href') || '';
                if (!href) continue;
                // Skip pure anchor/nav links
                if (href === '#' || href.endsWith('/careers') || href.endsWith('/jobs')) continue;
                if (!href.startsWith('http')) {{
                    href = baseUrl + (href.startsWith('/') ? '' : '/') + href;
                }}
                if (seen.has(href)) continue;
                seen.add(href);

                // Try to get location from nearby elements
                const parent = el.closest('li, div.job, article, tr') || el.parentElement;
                const locationEl = parent ? (
                    parent.querySelector('.location, .job-location, [class*="location"]') ||
                    parent.querySelector('span:last-child')
                ) : null;
                const location = locationEl ? locationEl.innerText.trim() : '';

                // Strip multiline junk (e.g. PwC "Save for Later\nMultiple Locations\n...")
                const nlIdx = title.indexOf(String.fromCharCode(10));
                const cleanTitle = (nlIdx > 0 ? title.slice(0, nlIdx) : title)
                    .replace(/(save for later|apply now|save)$/i, '').trim();
                if (!cleanTitle || cleanTitle.length < 10) continue;
                if (!jobWords.some(w => cleanTitle.toLowerCase().includes(w))) continue;
                results.push({{ title: cleanTitle, company: firmName, location, url: href }});
            }}
            if (results.length >= 20) break;
        }}
        return results;
    }}""")
    return jobs or []


def scrape_firm(page, firm: dict, target_locations: list, remote_ok: bool) -> int:
    saved = 0
    for url_key in ["url", "fallback_url"]:
        url = firm.get(url_key, "")
        if not url:
            continue
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            _delay(3, 5)
            # Scroll to trigger lazy loads
            page.evaluate("window.scrollBy(0, 600)")
            _delay(1, 2)

            jobs = _extract_jobs_generic(page, firm["name"], url)
            if jobs:
                for job in jobs:
                    # Quick description grab from current page if still on it
                    desc = ""
                    try:
                        page.goto(job["url"], wait_until="domcontentloaded", timeout=12000)
                        _delay(1, 2)
                        desc = page.evaluate("""() => {
                            const sels = [
                                '#jobDescriptionText', '.job-description',
                                '[class*="description"]', 'section.description',
                                'div.content', 'main'
                            ];
                            for (const s of sels) {
                                const el = document.querySelector(s);
                                if (el && el.innerText.trim().length > 100)
                                    return el.innerText.trim().slice(0, 3000);
                            }
                            return document.body.innerText.trim().slice(0, 2000);
                        }""") or ""
                    except Exception:
                        pass

                    sc = score_job(job["title"], desc, job["location"], target_locations, remote_ok, firm["name"])
                    if should_store(sc):
                        upsert_job(
                            source=firm["source"],
                            title=job["title"],
                            company=firm["name"],
                            url=job["url"],
                            score=sc,
                            location=job["location"],
                            description=desc,
                        )
                        saved += 1
                    _delay(1, 2)
                break  # got results from primary URL, skip fallback
        except Exception as exc:
            print(f"  {firm['name']} ({url_key}): {exc}")
        _delay(2, 4)
    return saved


def run_firm_scrapers(config: dict) -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return 0

    init_db()
    prefs = config.get("preferences", {})
    target_locations = prefs.get("locations", [])
    remote_ok = prefs.get("remote", True)

    total = 0
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

        for firm in FIRM_SEARCHES:
            print(f"  Scraping {firm['name']}…")
            try:
                n = scrape_firm(page, firm, target_locations, remote_ok)
                print(f"    → {n} jobs")
                total += n
            except Exception as exc:
                print(f"    ✗ {exc}")
            _delay(3, 5)

        browser.close()
    return total
