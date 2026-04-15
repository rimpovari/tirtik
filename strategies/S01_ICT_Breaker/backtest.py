"""
strategies/S01_ICT_Breaker/backtest.py
=======================================
ICT Dual Timeframe Breaker Stratejisi — tek sembol / tek parametre seti.

Dogrudan calistirmak icin:
    python strategies/S01_ICT_Breaker/backtest.py --symbol XAUUSD
    python strategies/S01_ICT_Breaker/backtest.py --symbol EURUSD --htf D1 --ltf H1 --rr 3.0

run_all.py tarafindan import edildiginde:
    from strategies.S01_ICT_Breaker.backtest import run_single
    trades, stats = run_single("XAUUSD", "D1", "H1", 2.0)
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

# Varsayilan parametreler (CLI icin)
DEFAULT_HTF    = "D1"
DEFAULT_LTF    = "H1"
DEFAULT_MIN_RR = 2.0
OB_TOUCH_TOL   = 0.10   # OB yuksekliginin %10'u kadar tolerans
WEEKLY_SIZE_MULT = 1.5  # W1 + HTF trend hizalandigi durumda pozisyon buyuklugu


# ============================================================
#  HTF ANALIZI
# ============================================================

def find_swing_points(df: pd.DataFrame) -> pd.DataFrame:
    """3-mum sistemi: orta mum en yuksek/en dusukse swing noktasidir."""
    df = df.copy()
    h = df["high"].values
    l = df["low"].values
    sh = np.zeros(len(df), dtype=bool)
    sl = np.zeros(len(df), dtype=bool)
    for i in range(1, len(df) - 1):
        if h[i] > h[i - 1] and h[i] > h[i + 1]:
            sh[i] = True
        if l[i] < l[i - 1] and l[i] < l[i + 1]:
            sl[i] = True
    df["swing_high"] = sh
    df["swing_low"]  = sl
    return df


def detect_msb(df: pd.DataFrame) -> pd.DataFrame:
    """
    Market Structure Break:
    - Kapanis onceki Swing High ustunde  -> msb_bull = True
    - Kapanis onceki Swing Low  altinda  -> msb_bear = True
    """
    df = df.copy()
    msb_bull  = np.zeros(len(df), dtype=bool)
    msb_bear  = np.zeros(len(df), dtype=bool)
    msb_level = np.full(len(df), np.nan)

    last_sh = np.nan
    last_sl = np.nan

    for i in range(len(df)):
        c = df.iloc[i]
        if not np.isnan(last_sh) and c["close"] > last_sh:
            msb_bull[i]  = True
            msb_level[i] = last_sh
            last_sh      = np.nan
        if not np.isnan(last_sl) and c["close"] < last_sl:
            msb_bear[i]  = True
            msb_level[i] = last_sl
            last_sl      = np.nan
        if c["swing_high"]:
            last_sh = c["high"]
        if c["swing_low"]:
            last_sl = c["low"]

    df["msb_bull"]  = msb_bull
    df["msb_bear"]  = msb_bear
    df["msb_level"] = msb_level
    return df


def find_order_blocks(df: pd.DataFrame) -> list[dict]:
    """
    Bullish OB : bullish MSB'den onceki son bearish mum.
    Bearish OB : bearish MSB'den onceki son bullish mum.
    """
    obs = []
    for i in range(1, len(df)):
        row = df.iloc[i]
        if row["msb_bull"]:
            for j in range(i - 1, max(i - 10, 0), -1):
                c = df.iloc[j]
                if c["close"] < c["open"]:
                    obs.append({"time": c.name, "ob_type": "bull",
                                "high": c["high"], "low": c["low"], "used": False})
                    break
        if row["msb_bear"]:
            for j in range(i - 1, max(i - 10, 0), -1):
                c = df.iloc[j]
                if c["close"] > c["open"]:
                    obs.append({"time": c.name, "ob_type": "bear",
                                "high": c["high"], "low": c["low"], "used": False})
                    break
    return obs


def _get_range(df: pd.DataFrame, idx: int) -> tuple[float, float]:
    """idx'e kadar son Swing Low -> Swing High araligini dondurur."""
    sub = df.iloc[: idx + 1]
    sh_rows = sub[sub["swing_high"]]
    sl_rows = sub[sub["swing_low"]]
    if sh_rows.empty or sl_rows.empty:
        return np.nan, np.nan
    return sl_rows.iloc[-1]["low"], sh_rows.iloc[-1]["high"]


def _htf_bias(df: pd.DataFrame, idx: int) -> str:
    """Son MSB yonune gore 'bull' | 'bear' | 'neutral' dondurur."""
    sub = df.iloc[: idx + 1]
    bull_idx = sub.index[sub["msb_bull"]]
    bear_idx = sub.index[sub["msb_bear"]]
    if len(bull_idx) == 0 and len(bear_idx) == 0:
        return "neutral"
    if len(bull_idx) == 0:
        return "bear"
    if len(bear_idx) == 0:
        return "bull"
    return "bull" if bull_idx[-1] > bear_idx[-1] else "bear"


# ============================================================
#  LTF ANALIZI — BREAKER KURULUMU
# ============================================================

def _swing_lows_idx(ltf: pd.DataFrame) -> list[int]:
    lows = []
    for i in range(1, len(ltf) - 1):
        if ltf["low"].iloc[i] < ltf["low"].iloc[i - 1] and \
           ltf["low"].iloc[i] < ltf["low"].iloc[i + 1]:
            lows.append(i)
    return lows


def _swing_highs_idx(ltf: pd.DataFrame) -> list[int]:
    highs = []
    for i in range(1, len(ltf) - 1):
        if ltf["high"].iloc[i] > ltf["high"].iloc[i - 1] and \
           ltf["high"].iloc[i] > ltf["high"].iloc[i + 1]:
            highs.append(i)
    return highs


def scan_ltf_for_breaker(ltf_window: pd.DataFrame, direction: str) -> dict | None:
    """
    LTF penceresi icinde Breaker kurulumu arar.

    Bullish (long):
      1. Swing Low olusur
      2. O low'un altina sweep
      3. Sweep oncesi high'in ustunde kapanis (MSS)
      4. Giris: sweep oncesi son bearish mum (Breaker Block)

    Bearish (short): tersi.

    Dondurur: {entry_high, entry_low, sweep_extreme, mss_time} veya None.
    """
    if len(ltf_window) < 6:
        return None

    if direction == "bull":
        for sl_idx in _swing_lows_idx(ltf_window):
            sl_price = ltf_window["low"].iloc[sl_idx]
            post     = ltf_window.iloc[sl_idx + 1:]
            if len(post) < 2:
                continue
            bounce_high = ltf_window.iloc[sl_idx]["high"]

            sweep_pos = None
            sweep_low = None
            for k, (_, row) in enumerate(post.iterrows()):
                if row["low"] < sl_price:
                    sweep_pos = k
                    sweep_low = row["low"]
                    break
            if sweep_pos is None:
                continue

            mss_time = None
            for _, row in post.iloc[sweep_pos + 1:].iterrows():
                if row["close"] > bounce_high:
                    mss_time = row.name
                    break
            if mss_time is None:
                continue

            pre = ltf_window.iloc[: sl_idx + sweep_pos + 1]
            for j in range(len(pre) - 1, max(len(pre) - 8, -1), -1):
                c = pre.iloc[j]
                if c["close"] < c["open"]:
                    return {"entry_high": c["high"], "entry_low": c["low"],
                            "sweep_extreme": sweep_low, "mss_time": mss_time}

    else:  # bear
        for sh_idx in _swing_highs_idx(ltf_window):
            sh_price   = ltf_window["high"].iloc[sh_idx]
            post       = ltf_window.iloc[sh_idx + 1:]
            if len(post) < 2:
                continue
            bounce_low = ltf_window.iloc[sh_idx]["low"]

            sweep_pos  = None
            sweep_high = None
            for k, (_, row) in enumerate(post.iterrows()):
                if row["high"] > sh_price:
                    sweep_pos  = k
                    sweep_high = row["high"]
                    break
            if sweep_pos is None:
                continue

            mss_time = None
            for _, row in post.iloc[sweep_pos + 1:].iterrows():
                if row["close"] < bounce_low:
                    mss_time = row.name
                    break
            if mss_time is None:
                continue

            pre = ltf_window.iloc[: sh_idx + sweep_pos + 1]
            for j in range(len(pre) - 1, max(len(pre) - 8, -1), -1):
                c = pre.iloc[j]
                if c["close"] > c["open"]:
                    return {"entry_high": c["high"], "entry_low": c["low"],
                            "sweep_extreme": sweep_high, "mss_time": mss_time}
    return None


# ============================================================
#  ANA BACKTEST FONKSIYONU
# ============================================================

def run_single(
    symbol: str,
    htf: str = DEFAULT_HTF,
    ltf: str = DEFAULT_LTF,
    min_rr: float = DEFAULT_MIN_RR,
    verbose: bool = False,
) -> tuple[list[Trade], dict]:
    """
    Tek sembol / tek parametre seti icin backtest calistirir.

    Dondurur:
        (trades, stats) — bos liste/dict olabilir.
    """
    # ── Veri yukle ───────────────────────────────────────────────────────
    try:
        htf_raw = load_data(symbol, htf)
        ltf_raw = load_data(symbol, ltf)
    except FileNotFoundError:
        return [], {}

    try:
        weekly_raw = load_data(symbol, "W1")
        has_weekly = True
    except FileNotFoundError:
        has_weekly = False

    if len(htf_raw) < 20 or len(ltf_raw) < 20:
        return [], {}

    # ── HTF analizi ──────────────────────────────────────────────────────
    htf_df = find_swing_points(htf_raw)
    htf_df = detect_msb(htf_df)
    order_blocks = find_order_blocks(htf_df)

    if not order_blocks:
        return [], {}

    # ── Haftalik trend ───────────────────────────────────────────────────
    weekly_bias = "neutral"
    if has_weekly and len(weekly_raw) >= 10:
        w = find_swing_points(weekly_raw)
        w = detect_msb(w)
        weekly_bias = _htf_bias(w, len(w) - 1)

    # ── Her OB icin LTF taramasi ─────────────────────────────────────────
    signals: list[Trade] = []

    for ob in order_blocks:
        ob_range = ob["high"] - ob["low"]
        if ob_range <= 0:
            continue
        tolerance = ob_range * OB_TOUCH_TOL

        ob_idx = htf_df.index.get_loc(ob["time"])
        r_low, r_high = _get_range(htf_df, ob_idx)
        if np.isnan(r_low) or np.isnan(r_high):
            continue
        r_mid = (r_low + r_high) / 2

        daily_bias = _htf_bias(htf_df, ob_idx)

        # Premium/Discount filtresi
        if ob["ob_type"] == "bull" and ob["low"] > r_mid:
            continue
        if ob["ob_type"] == "bear" and ob["high"] < r_mid:
            continue

        ltf_after = ltf_raw[ltf_raw.index > ob["time"]]
        ob_touched  = False
        touch_time  = None

        for ts, row in ltf_after.iterrows():
            in_ob = (
                row["low"]  <= ob["high"] + tolerance and
                row["high"] >= ob["low"]  - tolerance
            ) if ob["ob_type"] == "bull" else (
                row["high"] >= ob["low"]  - tolerance and
                row["low"]  <= ob["high"] + tolerance
            )

            if in_ob and not ob_touched:
                ob_touched = True
                touch_time = ts

            if not ob_touched:
                continue

            ltf_win = ltf_raw[
                (ltf_raw.index >= touch_time) &
                (ltf_raw.index <= ts)
            ].iloc[-40:]

            breaker = scan_ltf_for_breaker(ltf_win, ob["ob_type"])
            if breaker is None:
                continue

            # Giris hesapla
            if ob["ob_type"] == "bull":
                entry = breaker["entry_high"]
                sl    = breaker["sweep_extreme"] * 0.9995
                risk  = entry - sl
                if risk <= 0:
                    continue
                tp        = entry + risk * min_rr
                direction = "long"
            else:
                entry = breaker["entry_low"]
                sl    = breaker["sweep_extreme"] * 1.0005
                risk  = sl - entry
                if risk <= 0:
                    continue
                tp        = entry - risk * min_rr
                direction = "short"

            if abs(tp - entry) / risk < min_rr:
                continue

            size = 1.0
            if has_weekly and daily_bias == ob["ob_type"] and weekly_bias == ob["ob_type"]:
                size = WEEKLY_SIZE_MULT

            signals.append(Trade(
                entry_time=breaker["mss_time"],
                direction=direction,
                entry_price=entry,
                sl=sl,
                tp=tp,
                size=size,
            ))
            ob["used"] = True
            ob_touched = False
            break

    if not signals:
        return [], {}

    trades = simulate_trades(signals, ltf_raw)
    stats  = compute_stats(trades)

    if verbose:
        print(f"  {symbol} {htf}/{ltf} RR{min_rr}: "
              f"{stats.get('total_trades',0)} islem | "
              f"WR {stats.get('win_rate',0):.0%} | "
              f"R {stats.get('total_r',0)}")

    return trades, stats


# ============================================================
#  CLI — tek sembol testi
# ============================================================

def _cli() -> None:
    parser = argparse.ArgumentParser(description="ICT Breaker - tek sembol backtesti")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--htf",    default=DEFAULT_HTF)
    parser.add_argument("--ltf",    default=DEFAULT_LTF)
    parser.add_argument("--rr",     type=float, default=DEFAULT_MIN_RR)
    args = parser.parse_args()

    print(f"\n{'='*55}")
    print(f"  ICT Breaker - {args.symbol}")
    print(f"  HTF: {args.htf}  LTF: {args.ltf}  Min RR: {args.rr}")
    print(f"{'='*55}\n")

    trades, stats = run_single(args.symbol, args.htf, args.ltf, args.rr, verbose=True)

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

    out_path = Path(__file__).parent / f"results/{args.symbol}_{args.htf}_{args.ltf}_RR{args.rr}.xlsx"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    export_results(
        trades=trades,
        stats=stats,
        strategy_name=f"ICT Breaker {args.htf}/{args.ltf} RR{args.rr}",
        symbol=args.symbol,
        output_path=out_path,
    )


if __name__ == "__main__":
    _cli()
