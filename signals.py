from dataclasses import dataclass
from typing import Optional
from fetcher import SpotPrice, PolyMarket


@dataclass
class Signal:
    market: PolyMarket
    action: str          # "BUY YES" | "BUY NO" | "WATCH"
    edge_pct: float      # % mispricing
    reason: str


EDGE_THRESHOLD = 0.03   # 3% minimum edge to flag


def compute_signals(spot: SpotPrice, markets: list[PolyMarket]) -> list[Signal]:
    signals = []
    for m in markets:
        threshold = m.implied_threshold
        if threshold is None:
            continue

        # "above X" markets: probability = P(spot > threshold)
        # Use a simple binary model: if spot > threshold → fair YES ≈ 0.5 + lean
        # We just compare spot-implied direction to market price
        spot_above = spot.price > threshold
        fair_yes = 0.65 if spot_above else 0.35   # crude prior from spot alone

        edge = fair_yes - m.yes_price
        edge_pct = abs(edge) / max(m.yes_price, 1e-6)

        if edge_pct < EDGE_THRESHOLD:
            action = "WATCH"
        elif edge > 0:
            action = "BUY YES"
        else:
            action = "BUY NO"

        signals.append(Signal(
            market=m,
            action=action,
            edge_pct=edge_pct,
            reason=(
                f"Spot ${spot.price:,.0f} {'>' if spot_above else '<'} "
                f"${threshold:,.0f} threshold | "
                f"fair≈{fair_yes:.0%} vs market {m.yes_price:.0%}"
            ),
        ))

    signals.sort(key=lambda s: s.edge_pct, reverse=True)
    return signals
