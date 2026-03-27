import aiohttp
import asyncio
from dataclasses import dataclass
from typing import Optional


BINANCE_PRICE_URL = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
POLY_MARKETS_URL = "https://gamma-api.polymarket.com/markets"


@dataclass
class SpotPrice:
    price: float
    source: str


@dataclass
class PolyMarket:
    question: str
    condition_id: str
    yes_price: float
    no_price: float
    volume: float
    end_date: str
    active: bool

    @property
    def implied_threshold(self) -> Optional[float]:
        """Extract BTC price threshold from question if present."""
        import re
        m = re.search(r"\$([0-9,]+(?:\.[0-9]+)?)[kK]?", self.question)
        if not m:
            return None
        raw = m.group(1).replace(",", "")
        val = float(raw)
        # handle "$90k" style
        if "k" in self.question[m.start():m.end()].lower():
            val *= 1000
        return val

    @property
    def spread_vs_spot(self) -> Optional[float]:
        """Implied BTC price from YES probability (naive: midpoint * threshold / 0.5)."""
        t = self.implied_threshold
        if t is None or self.yes_price <= 0:
            return None
        # rough implied price: if yes_price=0.5 → spot≈threshold
        # implied_spot ≈ threshold * (yes_price / 0.5)  [linear approx]
        return t * (self.yes_price / 0.5)


DEMO_MARKETS = [
    PolyMarket("Will Bitcoin (BTC) exceed $90,000 by April 30, 2026?", "demo-1", 0.42, 0.58, 2_500_000, "2026-04-30", True),
    PolyMarket("Will Bitcoin (BTC) exceed $85,000 by March 31, 2026?", "demo-2", 0.61, 0.39, 1_800_000, "2026-03-31", True),
    PolyMarket("Will Bitcoin (BTC) exceed $100,000 by June 30, 2026?", "demo-3", 0.28, 0.72, 3_100_000, "2026-06-30", True),
    PolyMarket("Will Bitcoin (BTC) exceed $80,000 by March 31, 2026?", "demo-4", 0.88, 0.12, 980_000, "2026-03-31", True),
    PolyMarket("Will Bitcoin (BTC) exceed $95,000 by May 31, 2026?", "demo-5", 0.35, 0.65, 1_200_000, "2026-05-31", True),
]


async def fetch_spot(session: aiohttp.ClientSession) -> Optional[SpotPrice]:
    # Try Binance first, then CoinGecko as fallback
    for url, parser in [
        (BINANCE_PRICE_URL, lambda d: float(d["price"])),
        ("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd",
         lambda d: float(d["bitcoin"]["usd"])),
    ]:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                if r.status == 200:
                    data = await r.json()
                    return SpotPrice(price=parser(data), source="Binance" if "binance" in url else "CoinGecko")
        except Exception:
            continue
    return None


async def fetch_poly_btc_markets(session: aiohttp.ClientSession) -> list[PolyMarket]:
    params = {
        "tag_slug": "crypto",
        "active": "true",
        "closed": "false",
        "limit": "100",
    }
    markets = []
    try:
        async with session.get(POLY_MARKETS_URL, params=params, timeout=aiohttp.ClientTimeout(total=8)) as r:
            if r.status != 200:
                return markets
            data = await r.json()
    except Exception:
        return markets

    for m in data:
        q = m.get("question", "")
        if "bitcoin" not in q.lower() and "btc" not in q.lower():
            continue
        outcomes = m.get("outcomePrices", [])
        try:
            yes_p = float(outcomes[0]) if outcomes else 0.0
            no_p = float(outcomes[1]) if len(outcomes) > 1 else 1 - yes_p
        except (ValueError, IndexError):
            yes_p, no_p = 0.0, 1.0
        markets.append(PolyMarket(
            question=q,
            condition_id=m.get("conditionId", ""),
            yes_price=yes_p,
            no_price=no_p,
            volume=float(m.get("volume", 0) or 0),
            end_date=m.get("endDateIso", "")[:10] if m.get("endDateIso") else "?",
            active=bool(m.get("active", False)),
        ))

    markets.sort(key=lambda x: x.volume, reverse=True)
    return markets[:10]


async def fetch_all(demo: bool = False):
    async with aiohttp.ClientSession() as session:
        spot, poly = await asyncio.gather(
            fetch_spot(session),
            fetch_poly_btc_markets(session),
        )
    if demo or (spot is None and not poly):
        # Fall back to demo data when network is unavailable
        spot = spot or SpotPrice(price=87_342.0, source="Demo")
        poly = poly or DEMO_MARKETS
    return spot, poly
