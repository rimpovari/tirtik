"""
V2 - FVG Confirmation (Displacement Check)
============================================
Base strateji üzerine eklenen tek değişiklik:
MSS hareketinde gerçek bir displacement kanıtı olarak Fair Value Gap (FVG)
aranır. FVG yoksa kurulum geçersiz sayılır.

FVG tanımı:
  Bullish FVG: candle[i-1].high < candle[i+1].low  (yukarı boşluk)
  Bearish FVG: candle[i-1].low  > candle[i+1].high (aşağı boşluk)

Base'den farklı olan: scan_ltf_for_breaker (FVG kontrolü eklendi)
Base'den değişmeyen: HTF analizi, OB tespiti, giriş/çıkış mantığı
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from strategies.S01_ICT_Breaker.backtest import (
    find_swing_points, detect_msb, find_order_blocks,
    _get_range, _htf_bias, _swing_lows_idx, _swing_highs_idx,
    DEFAULT_HTF, DEFAULT_LTF, DEFAULT_MIN_RR, OB_TOUCH_TOL, WEEKLY_SIZE_MULT,
)
from core.data_loader import load_data
from core.order_simulator import Trade, simulate_trades, compute_stats

VERSION = "V2_FVG_Confirmation"


def _has_fvg(candles, direction: str) -> bool:
    """
    Verilen mum penceresi içinde en az bir FVG var mı kontrol eder.
    direction='bull' → bullish FVG arar, direction='bear' → bearish FVG.
    """
    if len(candles) < 3:
        return False
    for i in range(1, len(candles) - 1):
        prev = candles.iloc[i - 1]
        nxt  = candles.iloc[i + 1]
        if direction == "bull" and prev["high"] < nxt["low"]:
            return True
        if direction == "bear" and prev["low"] > nxt["high"]:
            return True
    return False


def scan_ltf_for_breaker(ltf_window, direction: str) -> dict | None:
    """
    Base ile aynı mantık; fark: sweep → MSS arası mumlar arasında
    ilgili yönde bir FVG zorunludur.
    """
    if len(ltf_window) < 6:
        return None

    if direction == "bull":
        for sl_idx in _swing_lows_idx(ltf_window):
            sl_price = ltf_window["low"].iloc[sl_idx]
            post = ltf_window.iloc[sl_idx + 1:]
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
            mss_idx  = None
            for k2, (ts, row) in enumerate(post.iloc[sweep_pos + 1:].iterrows()):
                if row["close"] > bounce_high:
                    mss_time = ts
                    mss_idx  = sweep_pos + 1 + k2
                    break
            if mss_time is None:
                continue

            # Sweep → MSS arası mumlar: FVG kontrolü
            displacement_candles = post.iloc[sweep_pos: mss_idx + 1]
            if not _has_fvg(displacement_candles, "bull"):   # ← FVG FİLTRESİ
                continue

            pre = ltf_window.iloc[: sl_idx + sweep_pos + 1]
            for j in range(len(pre) - 1, max(len(pre) - 8, -1), -1):
                c = pre.iloc[j]
                if c["close"] < c["open"]:
                    return {"entry_high": c["high"], "entry_low": c["low"],
                            "sweep_extreme": sweep_low, "mss_time": mss_time}

    else:  # bear
        for sh_idx in _swing_highs_idx(ltf_window):
            sh_price = ltf_window["high"].iloc[sh_idx]
            post = ltf_window.iloc[sh_idx + 1:]
            if len(post) < 2:
                continue
            bounce_low = ltf_window.iloc[sh_idx]["low"]

            sweep_pos = None
            sweep_high = None
            for k, (_, row) in enumerate(post.iterrows()):
                if row["high"] > sh_price:
                    sweep_pos = k
                    sweep_high = row["high"]
                    break
            if sweep_pos is None:
                continue

            mss_time = None
            mss_idx  = None
            for k2, (ts, row) in enumerate(post.iloc[sweep_pos + 1:].iterrows()):
                if row["close"] < bounce_low:
                    mss_time = ts
                    mss_idx  = sweep_pos + 1 + k2
                    break
            if mss_time is None:
                continue

            displacement_candles = post.iloc[sweep_pos: mss_idx + 1]
            if not _has_fvg(displacement_candles, "bear"):   # ← FVG FİLTRESİ
                continue

            pre = ltf_window.iloc[: sh_idx + sweep_pos + 1]
            for j in range(len(pre) - 1, max(len(pre) - 8, -1), -1):
                c = pre.iloc[j]
                if c["close"] > c["open"]:
                    return {"entry_high": c["high"], "entry_low": c["low"],
                            "sweep_extreme": sweep_high, "mss_time": mss_time}
    return None


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

            breaker = scan_ltf_for_breaker(ltf_win, ob["ob_type"])  # ← versiyona özel
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

    trades = simulate_trades(signals, ltf_raw)
    stats = compute_stats(trades)

    if verbose:
        print(f"  [{VERSION}] {symbol} {htf}/{ltf} RR{min_rr}: "
              f"{stats.get('total_trades', 0)} islem | "
              f"WR {stats.get('win_rate', 0):.0%} | "
              f"R {stats.get('total_r', 0)}")

    return trades, stats
