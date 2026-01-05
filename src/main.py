"""CLI interface using Typer."""

import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from src.config import Config
from src.core.orchestrator import Orchestrator
from src.utils.logging_config import configure_logging

app = typer.Typer(
    name="browser-agent",
    help="🧠 Intelligent Browser Automation Learning Agent",
    add_completion=False,
)
console = Console()


@app.command()
def learn(
    url: str = typer.Argument(..., help="URL to learn from"),
    headless: bool = typer.Option(False, "--headless", "-h", help="Run browser in headless mode"),
    max_iterations: int = typer.Option(100, "--max-iterations", "-n", help="Maximum learning iterations"),
    confidence: float = typer.Option(0.85, "--confidence", "-c", help="Confidence threshold (0-1)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
    notification_email: Optional[str] = typer.Option(None, "--email", "-e", help="Email for notifications"),
) -> None:
    """Start learning a new website.
    
    The agent will explore the site, interact with elements, and learn
    patterns until it reaches the confidence threshold.
    
    Example:
        browser-agent learn https://example.com --headless -n 50
    """
    configure_logging(verbose)

    console.print(Panel.fit(
        f"[bold blue]🧠 Browser Learning Agent[/bold blue]\n"
        f"Target: [green]{url}[/green]",
        title="Starting Learning Session",
    ))

    # Build config with CLI overrides
    config = Config(
        headless=headless,
        max_iterations=max_iterations,
        confidence_threshold=confidence,
    )
    if notification_email:
        config.notification_email = notification_email

    orchestrator = Orchestrator(config)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Learning in progress...", total=None)

        result = asyncio.run(orchestrator.learn(url))

        progress.remove_task(task)

    # Display results
    if result.success:
        console.print("\n[bold green]✅ Learning Complete![/bold green]\n")
        
        table = Table(title="Session Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Session ID", result.session.session_id)
        table.add_row("Total Actions", str(len(result.session.actions)))
        table.add_row("Success Rate", f"{result.metrics.success_rate:.0%}")
        table.add_row("Coverage", f"{result.metrics.coverage_score:.0%}")
        table.add_row("Confidence", f"{result.metrics.weighted_score:.0%}")
        table.add_row("Duration", f"{result.session.duration_seconds:.0f}s")
        
        console.print(table)
        
        if result.report:
            console.print(Panel(result.report, title="Learning Report"))
    else:
        console.print(f"\n[bold red]❌ Learning Failed[/bold red]\n{result.message}")
        raise typer.Exit(1)


@app.command()
def resume(
    session_id: str = typer.Argument(..., help="Session ID to resume"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
) -> None:
    """Resume a previously saved learning session.
    
    Example:
        browser-agent resume abc123
    """
    configure_logging(verbose)

    console.print(f"[yellow]Resuming session: {session_id}[/yellow]")

    config = Config()
    orchestrator = Orchestrator(config)

    result = asyncio.run(orchestrator.resume(session_id))

    if result.success:
        console.print("[bold green]✅ Session resumed and completed![/bold green]")
    else:
        console.print(f"[bold red]❌ Resume failed: {result.message}[/bold red]")
        raise typer.Exit(1)


@app.command()
def report(
    session_id: str = typer.Argument(..., help="Session ID to generate report for"),
    format: str = typer.Option("text", "--format", "-f", help="Output format: text, json, html"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file path"),
) -> None:
    """Generate a report for a completed session.
    
    Example:
        browser-agent report abc123 --format html -o report.html
    """
    from src.core.session import Session

    config = Config()

    try:
        session = Session.load(session_id, config.sessions_dir)
    except FileNotFoundError:
        console.print(f"[red]Session '{session_id}' not found[/red]")
        raise typer.Exit(1)

    if format == "json":
        import json
        report_content = json.dumps(session.to_dict(), indent=2)
    else:
        report_content = f"""
Session Report: {session.session_id}
====================================
Target URL: {session.target_url}
Status: {session.status}
Created: {session.created_at}
Actions: {len(session.actions)}
Success Rate: {session.success_rate:.0%}
Confidence: {session.confidence_score:.0%}
        """

    if output:
        output.write_text(report_content)
        console.print(f"[green]Report saved to {output}[/green]")
    else:
        console.print(report_content)


@app.command()
def sessions(
    limit: int = typer.Option(10, "--limit", "-n", help="Number of sessions to show"),
) -> None:
    """List recent learning sessions.
    
    Example:
        browser-agent sessions -n 5
    """
    import json

    config = Config()

    if not config.sessions_dir.exists():
        console.print("[yellow]No sessions found[/yellow]")
        return

    session_files = sorted(config.sessions_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)

    if not session_files:
        console.print("[yellow]No sessions found[/yellow]")
        return

    table = Table(title="Recent Sessions")
    table.add_column("ID", style="cyan")
    table.add_column("URL", style="blue")
    table.add_column("Status", style="green")
    table.add_column("Actions", style="yellow")
    table.add_column("Created", style="dim")

    for filepath in session_files[:limit]:
        with open(filepath) as f:
            data = json.load(f)
        
        status_color = "green" if data["status"] == "completed" else "red" if data["status"] == "failed" else "yellow"
        
        table.add_row(
            data["session_id"],
            data["target_url"][:40] + "..." if len(data["target_url"]) > 40 else data["target_url"],
            f"[{status_color}]{data['status']}[/{status_color}]",
            str(len(data.get("actions", []))),
            data["created_at"][:10],
        )

    console.print(table)


@app.command("auth-gmail")
def auth_gmail() -> None:
    """Authenticate with Gmail OAuth for email notifications.
    
    This will open a browser window to authenticate with your Google account.
    Required scopes: gmail.send
    
    Example:
        python -m src.main auth-gmail
    """
    import pickle
    from pathlib import Path
    
    from google_auth_oauthlib.flow import InstalledAppFlow
    
    config = Config()
    config.ensure_directories()
    
    SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
    
    # Build client config from environment
    client_config = {
        "installed": {
            "client_id": config.gmail_client_id,
            "client_secret": config.gmail_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost:8080/"],
        }
    }
    
    if not config.gmail_client_id or not config.gmail_client_secret:
        console.print("[red]❌ Gmail credentials not configured![/red]")
        console.print("Set GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET in your .env file")
        raise typer.Exit(1)
    
    console.print("[yellow]Opening browser for Gmail authentication...[/yellow]")
    
    try:
        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
        creds = flow.run_local_server(port=8080)
        
        # Save credentials
        token_path = Path(config.data_dir) / "gmail_token.pickle"
        with open(token_path, "wb") as token:
            pickle.dump(creds, token)
        
        console.print("[bold green]✅ Gmail authentication successful![/bold green]")
        console.print(f"Token saved to: {token_path}")
        
    except Exception as e:
        console.print(f"[red]❌ Authentication failed: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
