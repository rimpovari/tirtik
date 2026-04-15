"""
V3 - Dynamic Management (Trailing SL & Partial)
================================================
Base strateji üzerine eklenen tek değişiklik:
Fiyat 1:1 RR hedefine ulaştığında SL başabaş (entry) seviyesine çekilir.
Ardından orijinal TP hedeflenmeye devam edilir.

Sonuç tipleri:
  "win"       → TP'ye ulaştı
  "breakeven" → SL başabaşa çekildi, sonra entry'de kesildi (0R)
  "loss"      → SL başabaşa çekilmeden kesildi (-1R)

Base'den farklı olan: simulate_trades_be (breakeven SL mekanizması)
Base'den değişmeyen: HTF analizi, OB tespiti, breaker taraması
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

import numpy as np

ROOT = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from strategies.S01_ICT_Breaker.backtest import (
    find_swing_points, detect_msb, find_order_blocks,
    _get_range, _htf_bias, scan_ltf_for_breaker,
    DEFAULT_HTF, DEFAULT_LTF, DEFAULT_MIN_RR, OB_TOUCH_TOL, WEEKLY_SIZE_MULT,
)
from core.data_loader import load_data
from core.order_simulator import Trade, compute_stats

VERSION = "V3_Dynamic_Management"


def _scan_candles_be(trade: Trade, future, risk: float) -> Trade:
    """
    1:1 RR'ye ulaşıldığında SL'i entry'e çeker (breakeven).
    Sonrasında TP'ye ulaşırsa win, entry'ye dönerse breakeven kaydeder.
    """
    be_active = False
    current_sl = trade.sl

    for ts, row in future.iterrows():
        if trade.direction == "long":
            # 1:1 seviyesine ulaştı → BE aktif
            if not be_active and row["high"] >= trade.entry_price + risk:
                be_active = True
                current_sl = trade.entry_price

            if row["low"] <= current_sl:
                trade.exit_time = ts
                trade.exit_price = current_sl
                if be_active:
                    trade.result = "breakeven"
                    trade.pnl_r = 0.0
                    trade.pnl_pips = 0.0
                else:
                    trade.result = "loss"
                    trade.pnl_r = -1.0 * trade.size
                    trade.pnl_pips = (current_sl - trade.entry_price) * trade.size
                break

            if row["high"] >= trade.tp:
                trade.exit_time = ts
                trade.exit_price = trade.tp
                trade.result = "win"
                trade.pnl_r = (trade.tp - trade.entry_price) / risk * trade.size
                trade.pnl_pips = (trade.tp - trade.entry_price) * trade.size
                break

        else:  # short
            if not be_active and row["low"] <= trade.entry_price - risk:
                be_active = True
                current_sl = trade.entry_price

            if row["high"] >= current_sl:
                trade.exit_time = ts
                trade.exit_price = current_sl
                if be_active:
                    trade.result = "breakeven"
                    trade.pnl_r = 0.0
                    trade.pnl_pips = 0.0
                else:
                    trade.result = "loss"
                    trade.pnl_r = -1.0 * trade.size
                    trade.pnl_pips = (trade.entry_price - current_sl) * trade.size
                break

            if row["low"] <= trade.tp:
                trade.exit_time = ts
                trade.exit_price = trade.tp
                trade.result = "win"
                trade.pnl_r = (trade.entry_price - trade.tp) / risk * trade.size
                trade.pnl_pips = (trade.entry_price - trade.tp) * trade.size
                break

    if trade.result == "open":
        if len(future) > 0:
            last = future.iloc[-1]
            trade.exit_time = future.index[-1]
            trade.exit_price = last["close"]
            delta = (last["close"] - trade.entry_price) if trade.direction == "long" \
                    else (trade.entry_price - last["close"])
            trade.pnl_r = delta / risk * trade.size
            trade.pnl_pips = delta * trade.size

    return trade


def simulate_trades_be(signals: list[Trade], price_data) -> list[Trade]:
    closed = []
    for trade in signals:
        future = price_data[price_data.index > trade.entry_time]
        risk = abs(trade.entry_price - trade.sl)
        if risk == 0:
            continue
        closed.append(_scan_candles_be(trade, future, risk))
    return closed


def compute_stats_be(trades: list[Trade]) -> dict:
    """
    Breakeven sonuçlarını da destekleyen istatistik hesabı.
    Breakeven işlemler: win sayılmaz, loss sayılmaz — ayrı gösterilir.
    """
    closed = [t for t in trades if t.result != "open"]
    if not closed:
        return {}

    wins = [t for t in closed if t.result == "win"]
    losses = [t for t in closed if t.result == "loss"]
    bes = [t for t in closed if t.result == "breakeven"]

    total_r = sum(t.pnl_r for t in closed)
    gross_profit = sum(t.pnl_r for t in wins) if wins else 0
    gross_loss = abs(sum(t.pnl_r for t in losses)) if losses else 0

    decisive = wins + losses  # BE işlemler win rate hesabına katılmaz
    win_rate = len(wins) / len(decisive) if decisive else 0

    import numpy as np
    r_curve = np.cumsum([t.pnl_r for t in closed])
    peak = np.maximum.accumulate(r_curve)
    drawdown = r_curve - peak

    return {
        "total_trades": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "breakevens": len(bes),
        "win_rate": win_rate,
        "total_r": round(total_r, 2),
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else float("inf"),
        "avg_win_r": round(gross_profit / len(wins), 2) if wins else 0,
        "avg_loss_r": round(-gross_loss / len(losses), 2) if losses else 0,
        "max_drawdown_r": round(drawdown.min(), 2),
        "expectancy_r": round(total_r / len(closed), 2),
    }


def run_single(
    symbol: str,
    htf: str = DEFAULT_HTF,
    ltf: str = DEFAULT_LTF,
    min_rr: float = DEFAULT_MIN_RR,
    verbose: bool = False,
) -> tuple[list[Trade], dict]:
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

    htf_df = find_swing_points(htf_raw)
    htf_df = detect_msb(htf_df)
    order_blocks = find_order_blocks(htf_df)
    if not order_blocks:
        return [], {}

    weekly_bias = "neutral"
    if has_weekly and len(weekly_raw) >= 10:
        w = find_swing_points(weekly_raw)
        w = detect_msb(w)
        weekly_bias = _htf_bias(w, len(w) - 1)

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

        if ob["ob_type"] == "bull" and ob["low"] > r_mid:
            continue
        if ob["ob_type"] == "bear" and ob["high"] < r_mid:
            continue

        ltf_after = ltf_raw[ltf_raw.index > ob["time"]]
        ob_touched = False
        touch_time = None

        for ts, row in ltf_after.iterrows():
            in_ob = (
                row["low"] <= ob["high"] + tolerance and
                row["high"] >= ob["low"] - tolerance
            ) if ob["ob_type"] == "bull" else (
                row["high"] >= ob["low"] - tolerance and
                row["low"] <= ob["high"] + tolerance
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

            if ob["ob_type"] == "bull":
                entry = breaker["entry_high"]
                sl = breaker["sweep_extreme"] * 0.9995
                risk = entry - sl
                if risk <= 0:
                    continue
                tp = entry + risk * min_rr
                direction = "long"
            else:
                entry = breaker["entry_low"]
                sl = breaker["sweep_extreme"] * 1.0005
                risk = sl - entry
                if risk <= 0:
                    continue
                tp = entry - risk * min_rr
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

    trades = simulate_trades_be(signals, ltf_raw)   # ← versiyona özel simülasyon
    stats = compute_stats_be(trades)

    if verbose:
        print(f"  [{VERSION}] {symbol} {htf}/{ltf} RR{min_rr}: "
              f"{stats.get('total_trades', 0)} islem | "
              f"WR {stats.get('win_rate', 0):.0%} | "
              f"BE {stats.get('breakevens', 0)} | "
              f"R {stats.get('total_r', 0)}")

    return trades, stats
