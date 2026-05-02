"""
Job AutoPilot — Main Orchestrator
Run this file to start the overnight job search automation.

Usage:
    python src/main.py
    python src/main.py --dry-run      # Test without opening browser
    python src/main.py --resume-only  # Only generate tailored resumes
"""

import asyncio
import sys
import os
from datetime import datetime
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table
import click

from src.job_searcher import JobSearcher
from src.resume_builder import ResumeBuilder
from src.cover_letter_gen import CoverLetterGenerator
from src.form_filler import FormFiller
from src.tracker import ApplicationTracker
from src.utils import load_config, setup_logging, notify_done

load_dotenv()
console = Console()


@click.command()
@click.option("--dry-run", is_flag=True, help="Search and generate docs only, no browser form filling")
@click.option("--resume-only", is_flag=True, help="Only generate tailored resumes, no browsing")
@click.option("--limit", default=None, type=int, help="Override daily limit from config")
@click.option("--platform", default=None, help="Only search one platform: linkedin/indeed/glassdoor/dice")
@click.option("--config", default="config/config.yaml", help="Path to config file")
def main(dry_run, resume_only, limit, platform, config):
    """
    🤖 Job AutoPilot — Overnight Job Application Automation
    """
    asyncio.run(run(dry_run=dry_run, resume_only=resume_only, 
                    limit_override=limit, platform_filter=platform, 
                    config_path=config))


async def run(dry_run=False, resume_only=False, limit_override=None, 
              platform_filter=None, config_path="config/config.yaml"):
    
    # ── Banner ──────────────────────────────────────────────
    console.print(Panel.fit(
        "[bold cyan]🤖 Job AutoPilot[/bold cyan]\n"
        "[dim]Claude-powered overnight job application automation[/dim]",
        border_style="cyan"
    ))
    
    start_time = datetime.now()
    log = setup_logging()
    
    # ── Load Config ─────────────────────────────────────────
    cfg = load_config(config_path)
    daily_limit = limit_override or cfg["job_search"]["daily_limit"]
    daily_limit = min(daily_limit, 50)  # Hard cap at 50
    
    # ── Validate API Key ────────────────────────────────────
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        console.print("[bold red]❌ ANTHROPIC_API_KEY not found in .env[/bold red]")
        console.print("Get your key at: [link]https://console.anthropic.com[/link]")
        sys.exit(1)

    # ── Check Base Resume ───────────────────────────────────
    base_resume_path = ROOT / "config" / "base_resume.pdf"
    if not base_resume_path.exists():
        console.print("[bold red]❌ base_resume.pdf not found at config/base_resume.pdf[/bold red]")
        console.print("Place your master resume PDF there and re-run.")
        sys.exit(1)

    # ── Initialize Components ───────────────────────────────
    tracker = ApplicationTracker(cfg)
    searcher = JobSearcher(cfg, platform_filter=platform_filter)
    resume_builder = ResumeBuilder(cfg, api_key)
    cover_letter_gen = CoverLetterGenerator(cfg, api_key)

    # ── Check Daily Limit ───────────────────────────────────
    applied_today = tracker.count_today()
    remaining = daily_limit - applied_today
    
    console.print(f"\n[green]✓[/green] Daily limit: [bold]{daily_limit}[/bold] | "
                  f"Applied today: [bold]{applied_today}[/bold] | "
                  f"Remaining: [bold cyan]{remaining}[/bold cyan]")
    
    if remaining <= 0:
        console.print("[yellow]⚠️  Daily limit already reached. Try again tomorrow.[/yellow]")
        return

    # ── Step 1: Search for Jobs ──────────────────────────────
    console.print("\n[bold]Step 1/4 — 🔍 Searching for jobs...[/bold]")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("Scanning job boards...", total=None)
        jobs = await searcher.search_all(max_results=remaining * 2)  # Get extra to filter
        progress.update(task, description=f"Found {len(jobs)} matching jobs")
    
    if not jobs:
        console.print("[yellow]No new jobs found. Try broadening your search keywords.[/yellow]")
        return

    # Filter out already-applied
    if cfg["job_search"].get("skip_applied"):
        jobs = [j for j in jobs if not tracker.already_applied(j["url"])]
    
    # Trim to remaining limit
    jobs = jobs[:remaining]
    
    _print_jobs_table(jobs[:10])  # Preview first 10
    console.print(f"\n[cyan]Processing [bold]{len(jobs)}[/bold] jobs...[/cyan]")

    # ── Step 2: Generate Tailored Resumes & Cover Letters ────
    console.print("\n[bold]Step 2/4 — 📄 Generating tailored resumes & cover letters...[/bold]")
    
    prepared_jobs = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console
    ) as progress:
        task = progress.add_task("Building resumes...", total=len(jobs))
        
        for job in jobs:
            progress.update(task, description=f"Tailoring for {job['company']} — {job['title']}")
            
            try:
                # Generate tailored resume
                resume_path = await resume_builder.create_tailored_resume(
                    job_description=job["description"],
                    company=job["company"],
                    title=job["title"],
                    base_resume_path=str(base_resume_path)
                )
                
                # Generate cover letter
                cover_letter_path = await cover_letter_gen.generate(
                    job_description=job["description"],
                    company=job["company"],
                    title=job["title"]
                )
                
                job["resume_path"] = resume_path
                job["cover_letter_path"] = cover_letter_path
                prepared_jobs.append(job)
                log.info(f"✓ Prepared docs for {job['company']} - {job['title']}")
                
            except Exception as e:
                log.error(f"Failed to prepare {job['company']}: {e}")
                console.print(f"[red]  ⚠ Skipped {job['company']}: {e}[/red]")
            
            progress.advance(task)

    console.print(f"[green]✓[/green] Generated docs for [bold]{len(prepared_jobs)}[/bold] jobs")
    
    if resume_only:
        console.print("\n[yellow]--resume-only flag set. Skipping browser automation.[/yellow]")
        _print_summary(prepared_jobs, start_time, tracker)
        return

    # ── Step 3: Open Chrome & Fill Forms ────────────────────
    console.print("\n[bold]Step 3/4 — 🌐 Opening Chrome and filling application forms...[/bold]")
    console.print("[dim]Chrome will open. Do not click anything — let it work.[/dim]\n")
    
    if dry_run:
        console.print("[yellow]--dry-run flag set. Skipping browser automation.[/yellow]")
    else:
        filler = FormFiller(cfg)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=console
        ) as progress:
            task = progress.add_task("Filling forms...", total=len(prepared_jobs))
            
            for job in prepared_jobs:
                progress.update(task, description=f"Opening {job['company']} — {job['title']}")
                
                try:
                    result = await filler.fill_application(job)
                    job["form_status"] = result["status"]
                    job["tab_index"] = result.get("tab_index")
                    tracker.log_application(job)
                    log.info(f"✓ Form filled: {job['company']}")
                    
                except Exception as e:
                    log.error(f"Failed to fill form for {job['company']}: {e}")
                    job["form_status"] = f"error: {e}"
                    console.print(f"[red]  ⚠ Form error at {job['company']}: {e}[/red]")
                
                progress.advance(task)
        
        await filler.done()  # Keep tabs open, show summary

    # ── Step 4: Summary ──────────────────────────────────────
    console.print("\n[bold]Step 4/4 — ✅ Done![/bold]")
    _print_summary(prepared_jobs, start_time, tracker)
    
    # Optional notification
    try:
        notify_done(len(prepared_jobs), cfg)
    except Exception:
        pass


def _print_jobs_table(jobs):
    table = Table(title="Jobs Found", border_style="cyan", show_lines=True)
    table.add_column("Company", style="bold white")
    table.add_column("Title", style="cyan")
    table.add_column("Platform", style="dim")
    table.add_column("Location", style="dim")
    
    for job in jobs:
        table.add_row(
            job.get("company", "—"),
            job.get("title", "—"),
            job.get("platform", "—"),
            job.get("location", "Remote")
        )
    
    console.print(table)


def _print_summary(jobs, start_time, tracker):
    elapsed = datetime.now() - start_time
    minutes = int(elapsed.total_seconds() / 60)
    
    console.print(Panel(
        f"[bold green]✅ Run Complete[/bold green]\n\n"
        f"  Jobs processed:   [bold]{len(jobs)}[/bold]\n"
        f"  Time elapsed:     [bold]{minutes}m[/bold]\n"
        f"  Total applied:    [bold]{tracker.count_today()}[/bold] today\n"
        f"  Output folder:    [bold cyan]output/[/bold cyan]\n\n"
        f"[dim]Chrome tabs are open — review each form and click Submit.[/dim]",
        border_style="green",
        title="Job AutoPilot Summary"
    ))


if __name__ == "__main__":
    main()
