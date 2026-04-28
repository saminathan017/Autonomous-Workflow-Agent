#!/usr/bin/env python3
"""
Manual one-shot workflow execution.

Usage:
    cd autonomous_workflow_agent
    python scripts/run_once.py [--emails N] [--no-report]
"""
import asyncio
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from autonomous_workflow_agent.app.utils.logging import configure_logging
from autonomous_workflow_agent.app.workflows.engine import get_workflow_engine
from autonomous_workflow_agent.app.workflows.state_store import get_state_store

console = Console()
configure_logging("INFO")


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run one workflow execution")
    parser.add_argument("--emails", type=int, default=10, help="Max emails to process")
    parser.add_argument("--no-report", action="store_true", help="Skip report generation")
    args = parser.parse_args()

    store = get_state_store()
    await store.initialize()

    console.print(Panel.fit(
        f"[bold cyan]Autonomous Workflow Agent[/] · [dim]OpenAI gpt-4o-mini[/]\n"
        f"Max emails: [yellow]{args.emails}[/]   "
        f"Generate report: [yellow]{not args.no_report}[/]",
        title="[bold]Manual Run",
        border_style="cyan",
    ))

    engine = get_workflow_engine()

    with console.status("[cyan]Running workflow…[/]", spinner="dots"):
        run = await engine.execute_workflow(
            max_emails=args.emails,
            generate_report=not args.no_report,
        )

    success = run.status.value == "COMPLETED"
    colour = "green" if success else "red"

    table = Table(box=box.ROUNDED, border_style="dim", show_header=False)
    table.add_column("Field", style="dim", no_wrap=True)
    table.add_column("Value", style="white")

    table.add_row("Run ID", run.run_id)
    table.add_row("Status", f"[{colour}]{run.status.value}[/]")
    table.add_row("Emails", str(run.emails_processed))
    if run.report_path:
        table.add_row("Report", run.report_path.split("/")[-1])
    if run.error_message:
        table.add_row("[red]Error[/]", run.error_message)
    if run.completed_at and run.started_at:
        elapsed = (run.completed_at - run.started_at).total_seconds()
        table.add_row("Duration", f"{elapsed:.1f}s")

    console.print(table)

    if run.steps:
        console.print("\n[dim]Step details:[/]")
        for step in run.steps:
            ok = step.status.value == "COMPLETED"
            icon = "[green]✓[/]" if ok else "[red]✗[/]"
            console.print(f"  {icon}  {step.step_name:<25} {step.status.value}")
            if step.error_message:
                console.print(f"     [red dim]{step.error_message}[/]")

    await store.close()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
