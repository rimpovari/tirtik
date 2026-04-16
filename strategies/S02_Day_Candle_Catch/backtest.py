"""
strategies/S02_Day_Candle_Catch/backtest.py
=======================================
S02 Day Candle Catch Stratejisi - tek sembol / tek parametre seti.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from core.data_loader import load_data
from core.order_simulator import Trade, simulate_trades, compute_stats
from core.excel_exporter import export_results

# Varsayilan parametreler
DEFAULT_LTF    = "H1"
DEFAULT_MIN_RR = 2.0


def _swing_lows_idx(df: pd.DataFrame) -> list[int]:
    lows = []
    for i in range(1, len(df) - 1):
        if df["low"].iloc[i] < df["low"].iloc[i - 1] and \
           df["low"].iloc[i] < df["low"].iloc[i + 1]:
            lows.append(i)
    return lows


def _swing_highs_idx(df: pd.DataFrame) -> list[int]:
    highs = []
    for i in range(1, len(df) - 1):
        if df["high"].iloc[i] > df["high"].iloc[i - 1] and \
           df["high"].iloc[i] > df["high"].iloc[i + 1]:
            highs.append(i)
    return highs


def scan_for_mss(ltf_window: pd.DataFrame, direction: str) -> dict | None:
    """
    LTF penceresinde Market Structure Shift (MSS) arar.
    direction == "bull" (PDL temasindan sonra Long alinacak):
        Beklenti: fiyat swepten dondukten sonra bir onceki LTF swing high'in ustunde kapanis yapsin.
    direction == "bear" (PDH temasindan sonra Short alinacak):
        Beklenti: fiyat swepten dondukten sonra bir onceki LTF swing low'un altinda kapanis yapsin.
    """
    if len(ltf_window) < 5:
        return None

    if direction == "bull":
        highs = _swing_highs_idx(ltf_window)
        if not highs:
            return None
        last_high_idx = highs[-1]
        last_high_price = ltf_window["high"].iloc[last_high_idx]
        
        post = ltf_window.iloc[last_high_idx + 1:]
        
        # Sonrasindaki the extreme low (belki de gunun dibi)
        if len(post) < 1:
            return None
            
        sweep_extreme = ltf_window["low"].min()

        # Last high kirildi mi
        for _, row in post.iterrows():
            if row["close"] > last_high_price:
                # MSS oldu, o baring kapanisinda isleme gir
                return {
                    "mss_time": row.name,
                    "entry_price": row["close"],
                    "sweep_extreme": sweep_extreme
                }

    else: # bear
        lows = _swing_lows_idx(ltf_window)
        if not lows:
            return None
        last_low_idx = lows[-1]
        last_low_price = ltf_window["low"].iloc[last_low_idx]
        
        post = ltf_window.iloc[last_low_idx + 1:]
        
        if len(post) < 1:
            return None
            
        sweep_extreme = ltf_window["high"].max()

        # Last low kirildi mi
        for _, row in post.iterrows():
            if row["close"] < last_low_price:
                # MSS oldu
                return {
                    "mss_time": row.name,
                    "entry_price": row["close"],
                    "sweep_extreme": sweep_extreme
                }

    return None


def run_single(
    symbol: str,
    ltf: str = DEFAULT_LTF,
    min_rr: float = DEFAULT_MIN_RR,
    verbose: bool = False,
) -> tuple[list[Trade], dict]:
    
    try:
        daily_raw = load_data(symbol, "D1")
        ltf_raw   = load_data(symbol, ltf)
    except FileNotFoundError:
        return [], {}

    if len(daily_raw) < 5 or len(ltf_raw) < 20:
        return [], {}

    daily_raw["date"] = daily_raw.index.date
    ltf_raw["date"]   = ltf_raw.index.date

    # Her gun icin onceki gunun high/low bilgisini ekleyelim
    daily_raw["pdh"] = daily_raw["high"].shift(1)
    daily_raw["pdl"] = daily_raw["low"].shift(1)

    signals: list[Trade] = []
    
    # Gun gun gezelim
    unique_dates = daily_raw["date"].dropna().unique()
    for current_date in unique_dates:
        d_row = daily_raw[daily_raw["date"] == current_date].iloc[0]
        pdh = d_row["pdh"]
        pdl = d_row["pdl"]
        
        if pd.isna(pdh) or pd.isna(pdl):
            continue
            
        current_ltf = ltf_raw[ltf_raw["date"] == current_date]
        if current_ltf.empty:
            continue
            
        touched_level = None # "pdh" veya "pdl"
        touch_idx = None
        
        for k, (ts, row) in enumerate(current_ltf.iterrows()):
            if row["high"] >= pdh:
                touched_level = "pdh"
                touch_idx = k
                break
            elif row["low"] <= pdl:
                touched_level = "pdl"
                touch_idx = k
                break
                
        if touched_level is None or touch_idx is None:
            continue
            
        # Temastan sonra gun sonuna kadar olan kisimda bir mss var mi bakalim
        window_after = current_ltf.iloc[max(0, touch_idx - 10) :] 
        # Biraz oncesini de aliyoruz ki temas anindaki veya oncesindeki swing tepe/dipleri gorebilelim
        
        if touched_level == "pdl":
            # Long arayisi
            setup = scan_for_mss(window_after, "bull")
            if setup:
                entry = setup["entry_price"]
                sl = setup["sweep_extreme"] * 0.9995  # Biraz tolerans
                risk = entry - sl
                if risk > 0:
                    tp = entry + risk * min_rr
                    signals.append(Trade(
                        entry_time=setup["mss_time"],
                        direction="long",
                        entry_price=entry,
                        sl=sl,
                        tp=tp,
                        size=1.0
                    ))
        else:
            # Short arayisi (pdh temasi)
            setup = scan_for_mss(window_after, "bear")
            if setup:
                entry = setup["entry_price"]
                sl = setup["sweep_extreme"] * 1.0005
                risk = sl - entry
                if risk > 0:
                    tp = entry - risk * min_rr
                    signals.append(Trade(
                        entry_time=setup["mss_time"],
                        direction="short",
                        entry_price=entry,
                        sl=sl,
                        tp=tp,
                        size=1.0
                    ))

    if not signals:
        return [], {}

    trades = simulate_trades(signals, ltf_raw)
    stats  = compute_stats(trades)

    if verbose:
        print(f"  {symbol} LTF: {ltf} RR{min_rr}: "
              f"{stats.get('total_trades',0)} islem | "
              f"WR {stats.get('win_rate',0):.0%} | "
              f"R {stats.get('total_r',0)}")

    return trades, stats


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Day Candle Catch - tek sembol backtesti")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--ltf",    default=DEFAULT_LTF)
    parser.add_argument("--rr",     type=float, default=DEFAULT_MIN_RR)
    args = parser.parse_args()

    print(f"\n{'='*55}")
    print(f"  Day Candle Catch - {args.symbol}")
    print(f"  LTF: {args.ltf}  Min RR: {args.rr}")
    print(f"{'='*55}\n")

    trades, stats = run_single(args.symbol, args.ltf, args.rr, verbose=True)

    if not stats:
        print("Sinyal uretilmedi.")
        return

    print(f"\n{'-'*40}")
    print(f"  Toplam Islem    : {stats['total_trades']}")
    print(f"  Kazanan         : {stats['wins']}  Kaybeden: {stats['losses']}")
    print(f"  Kazanma Orani   : {stats['win_rate']:.1%}")
    print(f"  Toplam R        : {stats['total_r']}")
    print(f"  Profit Factor   : {stats['profit_factor']}")
    print(f"  Beklenti (R)    : {stats['expectancy_r']}")
    print(f"  Maks. Dusus (R) : {stats['max_drawdown_r']}")
    print(f"{'-'*40}\n")

    out_path = Path(__file__).parent / f"results/{args.symbol}_{args.ltf}_RR{args.rr}.xlsx"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    export_results(
        trades=trades,
        stats=stats,
        strategy_name=f"Day Candle Catch {args.ltf} RR{args.rr}",
        symbol=args.symbol,
        output_path=out_path,
    )


if __name__ == "__main__":
    _cli()
