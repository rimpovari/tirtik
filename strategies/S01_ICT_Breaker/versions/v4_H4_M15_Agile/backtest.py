"""
V4 - H4 / M15 Agile
=====================
Base strateji üzerine yapılan tek değişiklik:
Varsayılan zaman dilimleri H4 (HTF) ve M15 (LTF) olarak ayarlandı.
Tüm sinyal üretme ve simülasyon mantığı base ile aynı.

Base'den farklı olan: DEFAULT_HTF, DEFAULT_LTF
Base'den değişmeyen: Her şey
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

# Base'den run_single'ı import et, sadece varsayılanları değiştir
from strategies.S01_ICT_Breaker.backtest import run_single as _base_run_single

VERSION = "V4_H4_M15_Agile"

DEFAULT_HTF = "H4"
DEFAULT_LTF = "M15"


def run_single(
    symbol: str,
    htf: str = DEFAULT_HTF,   # ← H4
    ltf: str = DEFAULT_LTF,   # ← M15
    min_rr: float = 2.0,
    verbose: bool = False,
) -> tuple:
    trades, stats = _base_run_single(symbol, htf, ltf, min_rr, verbose=False)

    if verbose and stats:
        print(f"  [{VERSION}] {symbol} {htf}/{ltf} RR{min_rr}: "
              f"{stats.get('total_trades', 0)} islem | "
              f"WR {stats.get('win_rate', 0):.0%} | "
              f"R {stats.get('total_r', 0)}")

    return trades, stats
