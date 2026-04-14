"""Rich CLI review dashboard — browse and triage discovered jobs."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich import box
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

from db import get_pending, update_status

console = Console()

HELP_TEXT = (
    "[bold]Commands:[/bold]  "
    "[green]s[/green]=save  "
    "[red]r[/red]=reject  "
    "[yellow]k[/yellow]=skip  "
    "[blue]v[/blue]=view description  "
    "[dim]o[/dim]=open in browser  "
    "[dim]q[/dim]=quit"
)


def _build_table(jobs: list) -> Table:
    table = Table(box=box.ROUNDED, show_header=True, header_style="bold magenta", highlight=True)
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Score", width=6, justify="right")
    table.add_column("Title", min_width=30, max_width=42)
    table.add_column("Company", min_width=16, max_width=24)
    table.add_column("Location", min_width=16, max_width=24)
    table.add_column("Source", width=12)

    for i, job in enumerate(jobs, 1):
        score = job["score"]
        if score >= 80:
            score_style = "bold green"
        elif score >= 65:
            score_style = "yellow"
        else:
            score_style = "dim"

        table.add_row(
            str(i),
            Text(f"{score:.0f}", style=score_style),
            job["title"][:42],
            job["company"][:24],
            (job["location"] or "")[:24],
            job["source"],
        )
    return table


def _show_description(job: dict) -> None:
    desc = job.get("description") or "(No description available)"
    content = (
        f"[bold]{job['title']}[/bold] @ [cyan]{job['company']}[/cyan]\n"
        f"[dim]{job.get('location', '')}[/dim]\n"
        f"[link={job['url']}]{job['url']}[/link]\n\n"
        f"{desc[:4000]}"
    )
    console.print(Panel(content, title="Job Description", expand=True))
    Prompt.ask("[dim]Press Enter to continue[/dim]")


def _open_browser(url: str) -> None:
    import subprocess, sys
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", url])
        elif sys.platform == "linux":
            subprocess.Popen(["xdg-open", url])
        else:
            subprocess.Popen(["start", url], shell=True)
        console.print(f"[dim]Opened {url}[/dim]")
    except Exception as exc:
        console.print(f"[red]Could not open browser: {exc}[/red]")


def run_dashboard(config: dict) -> None:
    prefs = config.get("preferences", {})
    min_score = prefs.get("min_score", 60)

    while True:
        jobs = get_pending(min_score)
        if not jobs:
            console.print("[green]No pending jobs — all caught up![/green]")
            break

        console.clear()
        console.print(Panel(
            f"[bold]Job Discovery Queue[/bold]  ·  {len(jobs)} new  ·  min score: {min_score}",
            style="bold blue",
        ))
        console.print(_build_table(jobs))
        console.print()
        console.print(HELP_TEXT)
        console.print()

        raw = Prompt.ask("Enter job # + command (e.g. [bold]1s[/bold], [bold]2v[/bold], [bold]q[/bold])")
        raw = raw.strip().lower()

        if raw == "q":
            break

        num_str = "".join(c for c in raw if c.isdigit())
        cmd = "".join(c for c in raw if c.isalpha())

        if not num_str:
            console.print("[red]Enter a job number + command, e.g. '1s'.[/red]")
            Prompt.ask("[dim]Press Enter[/dim]")
            continue

        try:
            idx = int(num_str) - 1
            job = dict(jobs[idx])
        except (ValueError, IndexError):
            console.print("[red]Invalid job number.[/red]")
            Prompt.ask("[dim]Press Enter[/dim]")
            continue

        if cmd == "s":
            update_status(job["id"], "saved")
            console.print(f"[green]✓ Saved: {job['title']} @ {job['company']}[/green]")
            Prompt.ask("[dim]Press Enter[/dim]")
        elif cmd == "r":
            update_status(job["id"], "rejected")
            console.print(f"[red]✗ Rejected: {job['title']}[/red]")
            Prompt.ask("[dim]Press Enter[/dim]")
        elif cmd == "k":
            update_status(job["id"], "skipped")
            console.print(f"[yellow]→ Skipped (will resurface next run)[/yellow]")
            Prompt.ask("[dim]Press Enter[/dim]")
        elif cmd == "v":
            _show_description(job)
        elif cmd == "o":
            _open_browser(job["url"])
            Prompt.ask("[dim]Press Enter[/dim]")
        else:
            console.print("[red]Unknown command.[/red]")
            Prompt.ask("[dim]Press Enter[/dim]")
