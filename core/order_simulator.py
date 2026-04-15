"""
core/order_simulator.py
-----------------------
Sanal alım/satım işlemlerini simüle eder.
Her strateji bir sinyal listesi üretir; bu modül o sinyalleri gerçek
işlemlere dönüştürür ve istatistikleri hesaplar.
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Trade:
    entry_time: pd.Timestamp
    direction: Literal["long", "short"]
    entry_price: float
    sl: float          # Stop Loss
    tp: float          # Take Profit
    size: float = 1.0  # Pozisyon büyüklüğü (lot / birim)

    exit_time: pd.Timestamp | None = None
    exit_price: float | None = None
    result: Literal["win", "loss", "open"] = "open"
    pnl_r: float = 0.0   # Risk'e göre PnL (R katı)
    pnl_pips: float = 0.0


def simulate_trades(signals: list[Trade], price_data: pd.DataFrame) -> list[Trade]:
    """
    Her Trade sinyalini price_data üzerinde çalıştırır.
    SL veya TP'ye önce hangisi değerse o çıkışı kabul eder.

    Parametre:
        signals    : Trade listesi (exit_time=None olanlar)
        price_data : OHLC DataFrame (LTF zaman dilimi önerilir)

    Döndürür:
        Doldurulmuş Trade listesi
    """
    closed: list[Trade] = []

    for trade in signals:
        future = price_data[price_data.index > trade.entry_time]
        risk = abs(trade.entry_price - trade.sl)
        if risk == 0:
            continue

        result = _scan_candles(trade, future, risk)
        closed.append(result)

    return closed


def _scan_candles(trade: Trade, future: pd.DataFrame, risk: float) -> Trade:
    for ts, row in future.iterrows():
        if trade.direction == "long":
            if row["low"] <= trade.sl:
                trade.exit_time = ts
                trade.exit_price = trade.sl
                trade.result = "loss"
                trade.pnl_r = -1.0 * trade.size
                trade.pnl_pips = (trade.sl - trade.entry_price) * trade.size
                break
            if row["high"] >= trade.tp:
                trade.exit_time = ts
                trade.exit_price = trade.tp
                trade.result = "win"
                trade.pnl_r = (trade.tp - trade.entry_price) / risk * trade.size
                trade.pnl_pips = (trade.tp - trade.entry_price) * trade.size
                break
        else:  # short
            if row["high"] >= trade.sl:
                trade.exit_time = ts
                trade.exit_price = trade.sl
                trade.result = "loss"
                trade.pnl_r = -1.0 * trade.size
                trade.pnl_pips = (trade.entry_price - trade.sl) * trade.size
                break
            if row["low"] <= trade.tp:
                trade.exit_time = ts
                trade.exit_price = trade.tp
                trade.result = "win"
                trade.pnl_r = (trade.entry_price - trade.tp) / risk * trade.size
                trade.pnl_pips = (trade.entry_price - trade.tp) * trade.size
                break

    if trade.result == "open":
        last = future.iloc[-1] if len(future) > 0 else None
        if last is not None:
            trade.exit_time = future.index[-1]
            trade.exit_price = last["close"]
            trade.result = "open"
            delta = (last["close"] - trade.entry_price) if trade.direction == "long" \
                    else (trade.entry_price - last["close"])
            trade.pnl_r = delta / risk * trade.size
            trade.pnl_pips = delta * trade.size

    return trade


def compute_stats(trades: list[Trade]) -> dict:
    """Tamamlanmış Trade listesinden performans istatistikleri üretir."""
    closed = [t for t in trades if t.result != "open"]
    if not closed:
        return {}

    wins = [t for t in closed if t.result == "win"]
    losses = [t for t in closed if t.result == "loss"]

    total_r = sum(t.pnl_r for t in closed)
    gross_profit = sum(t.pnl_r for t in wins) if wins else 0
    gross_loss = abs(sum(t.pnl_r for t in losses)) if losses else 0

    r_curve = np.cumsum([t.pnl_r for t in closed])
    peak = np.maximum.accumulate(r_curve)
    drawdown = r_curve - peak
    max_dd = drawdown.min()

    return {
        "total_trades": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(closed),
        "total_r": round(total_r, 2),
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else float("inf"),
        "avg_win_r": round(gross_profit / len(wins), 2) if wins else 0,
        "avg_loss_r": round(-gross_loss / len(losses), 2) if losses else 0,
        "max_drawdown_r": round(max_dd, 2),
        "expectancy_r": round(total_r / len(closed), 2),
    }
