"""
scripts/fetch_historical_data.py
---------------------------------
MetaTrader 5'ten geçmiş veri çeker ve data/ klasörüne parquet olarak kaydeder.

Kullanım:
    python scripts/fetch_historical_data.py

MT5'in açık olması ve Python API'nin kurulu olması gerekir:
    pip install MetaTrader5
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

# ── Veri çekilecek enstrümanlar ve zaman dilimleri ──────────────────────────

SYMBOLS = [
    # Major Forex (7)
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD",
    # Metal (2)
    "XAUUSD", "XAGUSD",
    # EUR Cross (6)
    "EURGBP", "EURJPY", "EURCAD", "EURCHF", "EURAUD", "EURNZD",
    # GBP Cross (5)
    "GBPJPY", "GBPCHF", "GBPCAD", "GBPAUD", "GBPNZD",
    # AUD Cross (4)
    "AUDJPY", "AUDNZD", "AUDCAD", "AUDCHF",
    # Other Cross (6)
    "CADJPY", "CADCHF", "CHFJPY", "NZDJPY", "NZDCAD", "NZDCHF",
]  # Toplam: 30 parite

# M5 broker tarafindan desteklenmiyor, listede yok
TIMEFRAMES_MT5 = {
    "M15": None,
    "H1" : None,
    "H4" : None,
    "D1" : None,
    "W1" : None,
}

START_DATE = datetime(2025, 1, 1)
END_DATE   = datetime(2026, 4, 1)
DATA_DIR   = Path(__file__).parent.parent / "data"


def fetch_all() -> None:
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("[Hata] MetaTrader5 kütüphanesi bulunamadı.")
        print("  pip install MetaTrader5")
        sys.exit(1)

    if not mt5.initialize():
        print(f"[Hata] MT5 başlatılamadı: {mt5.last_error()}")
        sys.exit(1)

    # Zaman dilimi sabitlerini eşleştir
    tf_map = {
        "M5" : mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "H1" : mt5.TIMEFRAME_H1,
        "H4" : mt5.TIMEFRAME_H4,
        "D1" : mt5.TIMEFRAME_D1,
        "W1" : mt5.TIMEFRAME_W1,
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    total = len(SYMBOLS) * len(tf_map)
    done  = 0

    for symbol in SYMBOLS:
        for tf_name, tf_const in tf_map.items():
            done += 1
            stem = f"{symbol}_{tf_name}"
            out  = DATA_DIR / f"{stem}.parquet"

            mt5.symbol_select(symbol, True)
            rates = mt5.copy_rates_range(symbol, tf_const, START_DATE, END_DATE)

            if rates is None or len(rates) == 0:
                print(f"  [{done}/{total}] {stem:20s} - VERI YOK, atlandi")
                continue

            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s")
            df.set_index("time", inplace=True)
            df.rename(columns={
                "open": "open", "high": "high",
                "low": "low",  "close": "close",
            }, inplace=True)
            df = df[["open", "high", "low", "close"]]
            df.to_parquet(out)

            print(f"  [{done}/{total}] {stem:20s} - {len(df):>7,} mum -> {out.name}")

    mt5.shutdown()
    print(f"\n[Tamamlandi] Veriler '{DATA_DIR}' klasorune kaydedildi.")


if __name__ == "__main__":
    fetch_all()
