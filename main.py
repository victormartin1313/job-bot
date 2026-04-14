#!/usr/bin/env python3
"""Job Discovery Bot — CLI entry point.

Usage:
    python3 main.py setup      Interactive first-run wizard
    python3 main.py discover   Scrape all sources, score jobs, email digest
    python3 main.py review     Browse and triage the discovery queue
    python3 main.py saved      List jobs you saved
    python3 main.py status     Show counts by status
"""

from __future__ import annotations

import sys
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config() -> dict:
    import yaml
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f) or {}


def save_config(cfg: dict) -> None:
    import yaml
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def cmd_setup() -> None:
    from rich.console import Console
    from rich.prompt import Prompt, Confirm
    console = Console()
    console.print("\n[bold blue]Job Discovery Bot — Setup[/bold blue]\n")

    cfg = load_config() or {"profile": {}, "preferences": {}, "email": {}, "platforms": {}}
    profile = cfg.setdefault("profile", {})
    prefs = cfg.setdefault("preferences", {})
    email_cfg = cfg.setdefault("email", {})
    platforms = cfg.setdefault("platforms", {})

    def ask(label: str, obj: dict, key: str, default: str = "") -> None:
        current = obj.get(key, default) or default
        obj[key] = Prompt.ask(label, default=str(current))

    console.print("[bold]Profile[/bold]")
    ask("Your name", profile, "name")
    ask("University", profile, "university")

    console.print("\n[bold]Job Preferences[/bold]")
    loc_str = Prompt.ask(
        "Target cities (comma-separated, blank = anywhere)",
        default=", ".join(prefs.get("locations", [])),
    )
    prefs["locations"] = [l.strip() for l in loc_str.split(",") if l.strip()]
    prefs["remote"] = Confirm.ask("Include remote roles?", default=prefs.get("remote", True))
    prefs["min_score"] = int(Prompt.ask("Min score to show in review (0–100)", default=str(prefs.get("min_score", 60))))

    if not prefs.get("roles"):
        prefs["roles"] = [
            "IT Audit", "Technology Risk", "IT Advisory",
            "Accounting Information Systems", "ERP Consultant",
            "Cybersecurity Assurance", "Systems Auditor",
        ]

    console.print("\n[bold]Email (job digest)[/bold]")
    console.print("[dim]Used to send you new job matches after each discover run.[/dim]")
    console.print("[dim]iCloud: generate an app-specific password at appleid.apple.com → Security.[/dim]")
    ask("SMTP host", email_cfg, "smtp_host", "smtp.mail.me.com")
    ask("SMTP port", email_cfg, "smtp_port", "587")
    ask("SMTP username (your email)", email_cfg, "smtp_user", "vamartin@me.com")
    smtp_pw = Prompt.ask("SMTP password / app-specific password", password=True,
                         default=email_cfg.get("smtp_password", ""))
    if smtp_pw:
        email_cfg["smtp_password"] = smtp_pw

    console.print("\n[bold]Platform Credentials (for scraping)[/bold]")
    console.print("[dim]LinkedIn: provide your Chrome user-data-dir to reuse your existing session.[/dim]")
    ask("LinkedIn Chrome profile path (optional)", platforms, "linkedin_profile_path")
    ask("Handshake email (optional)", platforms, "handshake_email")
    hs_pw = Prompt.ask("Handshake password (optional, stored locally only)", password=True, default="")
    if hs_pw:
        platforms["handshake_password"] = hs_pw

    save_config(cfg)
    from db import init_db
    init_db()

    console.print("\n[green]✓ Setup complete.[/green]")
    console.print("  [bold]python3 main.py discover[/bold]  — find jobs")
    console.print("  [bold]python3 main.py review[/bold]    — triage results")


# ---------------------------------------------------------------------------
# Discover
# ---------------------------------------------------------------------------

def cmd_discover() -> None:
    from rich.console import Console
    console = Console()
    config = load_config()

    from db import init_db, get_pending
    init_db()

    from scrapers import run_all_scrapers
    console.print("[bold blue]Scraping jobs…[/bold blue]\n")
    total = run_all_scrapers(config)
    console.print(f"\n[bold green]{total} jobs saved.[/bold green]")

    # Email all jobs above threshold (regardless of status)
    min_score = config.get("preferences", {}).get("min_score", 60)
    from matcher import ALL_ACCOUNTING_FIRMS
    from db import get_conn
    with get_conn() as _conn:
        all_jobs = _conn.execute(
            "SELECT * FROM jobs WHERE score >= ? ORDER BY score DESC",
            (min_score,)
        ).fetchall()
        # Also include accounting firm jobs at lower threshold
        firm_jobs = _conn.execute(
            "SELECT * FROM jobs WHERE score >= 45 AND score < ?",
            (min_score,)
        ).fetchall()
        firm_jobs = [j for j in firm_jobs
                     if any(f in (j["company"] or "").lower() for f in ALL_ACCOUNTING_FIRMS)]
    seen_urls = {j["url"] for j in all_jobs}
    new_jobs = list(all_jobs) + [j for j in firm_jobs if j["url"] not in seen_urls]
    if new_jobs:
        smtp_cfg = config.get("email", {})
        console.print(f"[cyan]Emailing {len(new_jobs)} matches to vamartin@me.com…[/cyan]")
        from emailer import send_digest
        ok = send_digest(new_jobs, smtp_cfg)
        if ok:
            console.print("[green]✓ Email sent.[/green]")
        else:
            console.print("[yellow]Email not sent (check smtp_password in config.yaml).[/yellow]")
    else:
        console.print("[dim]No new matches above score threshold.[/dim]")

    console.print("Run [bold]python3 main.py review[/bold] to browse locally.")


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------

def cmd_review() -> None:
    config = load_config()
    from db import init_db
    init_db()
    from dashboard import run_dashboard
    run_dashboard(config)


# ---------------------------------------------------------------------------
# Saved
# ---------------------------------------------------------------------------

def cmd_saved() -> None:
    from rich.console import Console
    from rich.table import Table
    from rich import box
    console = Console()

    from db import init_db, get_saved
    init_db()
    jobs = get_saved()

    if not jobs:
        console.print("[yellow]No saved jobs yet. Use [bold]s[/bold] in the review dashboard to save jobs.[/yellow]")
        return

    table = Table(title=f"Saved Jobs ({len(jobs)})", box=box.ROUNDED, header_style="bold magenta")
    table.add_column("Score", width=6, justify="right")
    table.add_column("Title", min_width=32, max_width=44)
    table.add_column("Company", min_width=16, max_width=24)
    table.add_column("Location", min_width=16, max_width=24)
    table.add_column("Source", width=12)
    table.add_column("URL", min_width=30)

    for job in jobs:
        score = job["score"]
        score_style = "bold green" if score >= 80 else ("yellow" if score >= 65 else "dim")
        from rich.text import Text
        table.add_row(
            Text(f"{score:.0f}", style=score_style),
            job["title"][:44],
            job["company"][:24],
            (job["location"] or "")[:24],
            job["source"],
            job["url"],
        )

    console.print(table)


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def cmd_status() -> None:
    from rich.console import Console
    from rich.table import Table
    from rich import box
    console = Console()

    from db import init_db, get_stats
    init_db()
    stats = get_stats()

    if not stats:
        console.print("[yellow]No jobs tracked yet. Run [bold]python3 main.py discover[/bold].[/yellow]")
        return

    table = Table(title="Job Stats", box=box.ROUNDED, header_style="bold magenta")
    table.add_column("Status", min_width=12)
    table.add_column("Count", justify="right", style="bold")

    style_map = {"new": "cyan", "saved": "green", "rejected": "red", "skipped": "dim"}
    for status, count in sorted(stats.items(), key=lambda x: -x[1]):
        style = style_map.get(status, "white")
        table.add_row(f"[{style}]{status}[/{style}]", str(count))

    console.print(table)
    console.print(f"[bold]Total:[/bold] {sum(stats.values())}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

COMMANDS = {
    "setup": cmd_setup,
    "discover": cmd_discover,
    "review": cmd_review,
    "saved": cmd_saved,
    "status": cmd_status,
}

USAGE = """\
[bold]Usage:[/bold]
  python3 main.py [bold cyan]setup[/bold cyan]      First-run wizard
  python3 main.py [bold cyan]discover[/bold cyan]   Scrape all sources and score jobs
  python3 main.py [bold cyan]review[/bold cyan]     Browse and triage the discovery queue
  python3 main.py [bold cyan]saved[/bold cyan]      List saved jobs with URLs
  python3 main.py [bold cyan]status[/bold cyan]     Show counts by status
"""


def main() -> None:
    from rich.console import Console
    console = Console()

    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        console.print(USAGE)
        sys.exit(0 if len(sys.argv) < 2 else 1)

    cmd = sys.argv[1]

    if cmd != "setup" and not CONFIG_PATH.exists():
        console.print("[yellow]No config found — running setup first.[/yellow]\n")
        cmd_setup()
        console.print()

    COMMANDS[cmd]()


if __name__ == "__main__":
    main()
