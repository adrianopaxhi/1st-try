#!/usr/bin/env python3
"""
BTC Arb Terminal — 5-minute refresh
Monitors spread between Binance spot BTC and Polymarket BTC prediction markets.
"""

import asyncio
import sys
import argparse
from datetime import datetime

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from fetcher import fetch_all, SpotPrice, PolyMarket
from signals import compute_signals, Signal

REFRESH_SECONDS = 300   # 5 minutes
console = Console()


def spot_panel(spot: SpotPrice | None) -> Panel:
    if spot is None:
        return Panel("[red]SPOT: unavailable[/red]", title="Spot BTC", border_style="red")
    content = Text(f"${spot.price:,.2f}", style="bold green", justify="center")
    return Panel(content, title=f"[bold]Spot BTC[/bold] via {spot.source}", border_style="green")


def markets_table(markets: list[PolyMarket], spot: SpotPrice | None, signals: list[Signal]) -> Table:
    sig_map = {s.market.condition_id: s for s in signals}

    tbl = Table(
        box=box.SIMPLE_HEAVY,
        show_lines=False,
        expand=True,
        title="[bold cyan]Polymarket BTC Markets[/bold cyan]",
    )
    tbl.add_column("Question", ratio=5, no_wrap=False)
    tbl.add_column("YES", justify="right", ratio=1)
    tbl.add_column("NO", justify="right", ratio=1)
    tbl.add_column("Volume", justify="right", ratio=1)
    tbl.add_column("Ends", justify="center", ratio=1)
    tbl.add_column("Signal", ratio=2)

    for m in markets:
        sig = sig_map.get(m.condition_id)
        if sig and sig.action == "BUY YES":
            action_txt = Text(f"▲ BUY YES  +{sig.edge_pct:.0%}", style="bold green")
        elif sig and sig.action == "BUY NO":
            action_txt = Text(f"▼ BUY NO   +{sig.edge_pct:.0%}", style="bold red")
        else:
            action_txt = Text("— watch", style="dim")

        yes_style = "green" if m.yes_price >= 0.5 else "yellow"
        no_style = "red" if m.no_price >= 0.5 else "yellow"

        tbl.add_row(
            m.question[:80],
            Text(f"{m.yes_price:.2%}", style=yes_style),
            Text(f"{m.no_price:.2%}", style=no_style),
            f"${m.volume:,.0f}",
            m.end_date,
            action_txt,
        )

    if not markets:
        tbl.add_row("[dim]No BTC markets found[/dim]", "", "", "", "", "")

    return tbl


def signals_panel(signals: list[Signal]) -> Panel:
    actionable = [s for s in signals if s.action != "WATCH"]
    if not actionable:
        return Panel("[dim]No actionable edges detected[/dim]", title="[bold yellow]Signals[/bold yellow]", border_style="yellow")

    lines = []
    for s in actionable[:5]:
        color = "green" if s.action == "BUY YES" else "red"
        lines.append(
            f"[{color}][bold]{s.action}[/bold][/{color}]  "
            f"[cyan]{s.market.question[:55]}[/cyan]\n"
            f"   {s.reason}  edge={s.edge_pct:.1%}"
        )
    return Panel("\n".join(lines), title="[bold yellow]Top Signals[/bold yellow]", border_style="yellow")


def footer(last_update: datetime, next_in: int) -> Text:
    return Text(
        f" Last update: {last_update.strftime('%H:%M:%S')}  |  "
        f"Next refresh in: {next_in}s  |  q=quit",
        style="dim",
    )


async def run(**kwargs):
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="top", size=5),
        Layout(name="markets"),
        Layout(name="signals", size=10),
        Layout(name="footer", size=1),
    )

    spot = None
    markets = []
    signals = []
    last_update = datetime.now()
    tick = 0
    use_demo = kwargs.get("demo", False)

    async def refresh():
        nonlocal spot, markets, signals, last_update
        s, m = await fetch_all(demo=use_demo)
        if s:
            spot = s
        markets = m
        signals = compute_signals(spot, markets) if spot else []
        last_update = datetime.now()

    await refresh()

    with Live(layout, console=console, refresh_per_second=1, screen=True):
        while True:
            layout["header"].update(Panel(
                "[bold white]BTC ARB TERMINAL[/bold white]  "
                "[dim]spot vs Polymarket prediction spread · 5-min auto-refresh[/dim]",
                border_style="blue",
            ))
            layout["top"].update(spot_panel(spot))
            layout["markets"].update(markets_table(markets, spot, signals))
            layout["signals"].update(signals_panel(signals))
            layout["footer"].update(footer(last_update, REFRESH_SECONDS - (tick % REFRESH_SECONDS)))

            await asyncio.sleep(1)
            tick += 1

            if tick % REFRESH_SECONDS == 0:
                await refresh()


def main():
    parser = argparse.ArgumentParser(description="BTC Arb Terminal")
    parser.add_argument("--demo", action="store_true", help="Use demo data (no network needed)")
    parser.add_argument("--refresh", type=int, default=300, metavar="SECONDS", help="Refresh interval (default: 300)")
    args = parser.parse_args()

    global REFRESH_SECONDS
    REFRESH_SECONDS = args.refresh

    try:
        asyncio.run(run(demo=args.demo))
    except KeyboardInterrupt:
        console.print("\n[dim]Exited.[/dim]")
        sys.exit(0)


if __name__ == "__main__":
    main()
