"""
core/data_loader.py
-------------------
Parquet ve CSV formatındaki geçmiş fiyat verilerini okur.
Tüm stratejiler bu modülü kullanır.
"""

import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

REQUIRED_COLUMNS = {"open", "high", "low", "close"}


def load_data(symbol: str, timeframe: str) -> pd.DataFrame:
    """
    data/ klasöründen belirtilen sembol ve zaman dilimine ait veriyi okur.

    Parametre:
        symbol    : "XAUUSD", "EURUSD" gibi sembol adı
        timeframe : "H1", "D1", "M15" gibi zaman dilimi

    Döndürür:
        DatetimeIndex'li, sütunları küçük harfle ('open','high','low','close')
        normalize edilmiş bir DataFrame.
    """
    stem = f"{symbol}_{timeframe}"

    for ext in (".parquet", ".csv"):
        path = DATA_DIR / (stem + ext)
        if path.exists():
            df = _read_file(path)
            return _normalize(df)

    raise FileNotFoundError(
        f"'{stem}.parquet' veya '{stem}.csv' dosyası '{DATA_DIR}' içinde bulunamadı.\n"
        "Veriyi önce scripts/fetch_historical_data.py ile indirin."
    )


def _read_file(path: Path) -> pd.DataFrame:
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path, parse_dates=True, index_col=0)


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.lower() for c in df.columns]
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Veri dosyasında eksik sütunlar: {missing}")
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    df.sort_index(inplace=True)
    df = df[["open", "high", "low", "close"]].copy()
    return df
