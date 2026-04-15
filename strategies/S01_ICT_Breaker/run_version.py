# -*- coding: utf-8 -*-
"""
strategies/S01_ICT_Breaker/run_version.py
==========================================
Belirli bir versiyonu 6 ana parite × tüm TF setleri × tüm RR değerleri
üzerinde çalıştırır ve Excel çıktısı üretir.

Kullanım:
    python strategies/S01_ICT_Breaker/run_version.py --version v1
    python strategies/S01_ICT_Breaker/run_version.py --version v2 --symbols EURUSD XAUUSD
    python strategies/S01_ICT_Breaker/run_version.py --version all

Versiyon isimleri:
    base  → orijinal backtest.py (değiştirilmez)
    v1    → V1_Killzones
    v2    → V2_FVG_Confirmation
    v3    → V3_Dynamic_Management
    v4    → V4_H4_M15_Agile
    all   → tüm versiyonlar sırayla
"""

from __future__ import annotations

import argparse
import importlib
import io
import sys
from pathlib import Path

# Windows terminalinde UTF-8 zorla
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from core.excel_exporter import export_results

# ── Sabitler ────────────────────────────────────────────────────────────────

SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "EURGBP", "GBPJPY"]

TF_SETS = [
    ("W1",  "D1"),
    ("D1",  "H4"),
    ("D1",  "H1"),
    ("D1",  "M15"),
    ("H4",  "H1"),
    ("H4",  "M15"),
    ("H1",  "M15"),
]

RR_VALUES = [2.0, 3.0, 4.0, 5.0, 6.0]

VERSIONS = {
    "base": "strategies.S01_ICT_Breaker.backtest",
    "v1":   "strategies.S01_ICT_Breaker.versions.v1_Killzones.backtest",
    "v2":   "strategies.S01_ICT_Breaker.versions.v2_FVG_Confirmation.backtest",
    "v3":   "strategies.S01_ICT_Breaker.versions.v3_Dynamic_Management.backtest",
    "v4":   "strategies.S01_ICT_Breaker.versions.v4_H4_M15_Agile.backtest",
}


# ── Çalıştırıcı ─────────────────────────────────────────────────────────────

def run_version(version_key: str, symbols: list[str]) -> None:
    module_path = VERSIONS[version_key]
    mod = importlib.import_module(module_path)
    version_name = getattr(mod, "VERSION", version_key.upper())

    print(f"\n{'='*60}")
    print(f"  VERSİYON : {version_name}")
    print(f"  Pariteler: {', '.join(symbols)}")
    print(f"  TF Seti  : {len(TF_SETS)} set × {len(RR_VALUES)} RR = "
          f"{len(TF_SETS) * len(RR_VALUES)} kombinasyon/parite")
    print(f"{'='*60}\n")

    results_dir = Path(__file__).parent / "results" / version_key
    results_dir.mkdir(parents=True, exist_ok=True)

    total_combos = len(symbols) * len(TF_SETS) * len(RR_VALUES)
    done = 0

    for symbol in symbols:
        symbol_trades_all = []

        for htf, ltf in TF_SETS:
            # V4 sadece H4/M15 destekler; diğer TF setlerini atla
            if version_key == "v4" and (htf, ltf) != ("H4", "M15"):
                done += len(RR_VALUES)
                continue

            for rr in RR_VALUES:
                done += 1
                trades, stats = mod.run_single(symbol, htf, ltf, rr, verbose=False)

                if stats:
                    symbol_trades_all.append((htf, ltf, rr, trades, stats))
                    print(f"  [{done:3}/{total_combos}] {symbol} {htf}/{ltf} RR{rr}: "
                          f"{stats['total_trades']} islem | "
                          f"WR {stats['win_rate']:.0%} | "
                          f"R {stats['total_r']}")
                else:
                    print(f"  [{done:3}/{total_combos}] {symbol} {htf}/{ltf} RR{rr}: — sinyal yok")

        # Parite Excel'i
        if symbol_trades_all:
            best = max(symbol_trades_all, key=lambda x: x[4].get("total_r", -999))
            htf_b, ltf_b, rr_b, trades_b, stats_b = best
            out_path = results_dir / f"{symbol}.xlsx"
            export_results(
                trades=trades_b,
                stats=stats_b,
                strategy_name=f"{version_name} {htf_b}/{ltf_b} RR{rr_b}",
                symbol=symbol,
                output_path=out_path,
            )
            print(f"\n  >> {symbol}.xlsx kaydedildi "
                  f"(en iyi: {htf_b}/{ltf_b} RR{rr_b}, R={stats_b['total_r']})\n")

    print(f"\n{'='*60}")
    print(f"  Tamamlandı. Sonuçlar: {results_dir}")
    print(f"{'='*60}\n")


# ── CLI ─────────────────────────────────────────────────────────────────────

def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="ICT Breaker — versiyon bazlı backtest çalıştırıcı"
    )
    parser.add_argument(
        "--version", default="base",
        choices=list(VERSIONS.keys()) + ["all"],
        help="Çalıştırılacak versiyon (base/v1/v2/v3/v4/all)"
    )
    parser.add_argument(
        "--symbols", nargs="+", default=SYMBOLS,
        help="Test edilecek pariteler (varsayılan: 6 ana parite)"
    )
    args = parser.parse_args()

    if args.version == "all":
        for key in VERSIONS:
            run_version(key, args.symbols)
    else:
        run_version(args.version, args.symbols)


if __name__ == "__main__":
    _cli()
