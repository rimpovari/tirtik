# Ticaret Stratejileri Backtest Altyapısı — Güncel Plan

## Proje Durumu
- Çekirdek altyapı (data_loader, order_simulator, excel_exporter) tamamlandı.
- S01_ICT_Breaker stratejisi kodlandı ve XAUUSD üzerinde doğrulandı.
- Sonraki adım: 6 ana parite × çoklu zaman dilimi seti × çoklu RR değeri.
- Strateji keskinleştikten sonra 30 pariteye genişlenecek (bkz. `data/pariteler_tam_liste.txt`).

---

## Klasör Yapısı

```text
tirtik/
├── data/                              # MT5'ten çekilen parquet dosyaları
│   ├── XAUUSD_H1.parquet
│   ├── EURUSD_D1.parquet
│   └── ...  (6 ana parite × 5 zaman dilimi = 30 dosya)
├── core/
│   ├── data_loader.py
│   ├── order_simulator.py
│   └── excel_exporter.py
├── strategies/
│   └── S01_ICT_Breaker/
│       ├── strateji.md
│       ├── backtest.py               # Tek sembol / tek parametre seti (CLI)
│       ├── run_all.py                # 6 parite × tüm TF seti × tüm RR -> Excel
│       └── results/
│           ├── XAUUSD.xlsx           # Her parite: 1 dosya, ayrı sayfa/parametre
│           ├── EURUSD.xlsx
│           └── ...
│           └── OZET_TUM.xlsx         # Tüm sonuçlar — matris + sıralama
├── scripts/
│   └── fetch_historical_data.py
└── requirements.txt
```

---

## 6 Ana Parite (Geliştirme Aşaması)

> Strateji keskinleştikten sonra 30 pariteye geçilecek. Tam liste: `data/pariteler_tam_liste.txt`

| # | Sembol  | Kategori    | Seçilme Nedeni                          |
|---|---------|-------------|-----------------------------------------|
| 1 | EURUSD  | Major Forex | En likit, dar spread, referans parite   |
| 2 | GBPUSD  | Major Forex | Volatil, ICT için ideal hareket         |
| 3 | USDJPY  | Major Forex | Trend odaklı, temiz yapı                |
| 4 | XAUUSD  | Metal       | Yüksek volatilite, güçlü OB reaksiyonu |
| 5 | EURGBP  | EUR Cross   | EUR ve GBP'yi birlikte gözlemler        |
| 6 | GBPJPY  | GBP Cross   | Hızlı hareket, keskin Breaker setupleri |

---

## Zaman Dilimi Setleri (HTF / LTF)

| Set | HTF  | LTF  | Yorum                       |
|-----|------|------|-----------------------------|
| 1   | W1   | D1   | Makro trend / günlük giriş  |
| 2   | D1   | H4   | Günlük trend / 4h giriş     |
| 3   | D1   | H1   | Günlük trend / saatlik giriş (varsayılan) |
| 4   | D1   | M15  | Günlük trend / 15dk giriş   |
| 5   | H4   | H1   | 4h trend / saatlik giriş    |
| 6   | H4   | M15  | 4h trend / 15dk giriş       |
| 7   | H1   | M15  | Saatlik trend / 15dk giriş  |

> M5 verisi broker tarafından bu tarih aralığı için sağlanamamaktadır; listeden çıkarılmıştır.

---

## RR Değerleri (Min Risk/Ödül)

| # | Min RR | Açıklama                         |
|---|--------|----------------------------------|
| 1 | 2.0    | 1R risk → 2R ödül               |
| 2 | 3.0    | 1R risk → 3R ödül               |
| 3 | 4.0    | 1R risk → 4R ödül               |
| 4 | 5.0    | 1R risk → 5R ödül               |
| 5 | 6.0    | 1R risk → 6R ödül               |

**Toplam kombinasyon:** 6 parite × 7 TF seti × 5 RR = **210 backtest**
*(Tam liste ile: 30 × 7 × 5 = 1.050 backtest)*

---

## Test Parametreleri

- **Dönem:** 2025-01-01 → 2026-04-01
- **Strateji:** ICT Breaker (Dual Timeframe — swing, MSB, OB, Premium/Discount, Breaker)
- **Dinamik boyutlandırma:** W1 + HTF trendi hizalandığında 1.5x pozisyon

---

## Excel Çıktı Yapısı

### Per-Parite Excel (`results/{SEMBOL}.xlsx`)
- **"Ozet"** sayfası: Tüm TF seti × RR kombinasyonları (satır) ve metrikler (sütun)
- **"{HTF}\_{LTF}\_RR{X}"** sayfaları: Her kombinasyonun bireysel işlem listesi

### Master Özet Excel (`results/OZET_TUM.xlsx`)
- **"Tum_Sonuclar"**: Tüm 1050 kombinasyonun düz tablosu
- **"WinRate_Matrix"**: Sembol × Kombinasyon pivot tablosu (kazanma oranı)
- **"TotalR_Matrix"**: Sembol × Kombinasyon pivot tablosu (toplam R)
- **"PF_Matrix"**: Sembol × Kombinasyon pivot tablosu (profit factor)
- **"En_Iyi_30"**: Toplam R'ye göre sıralanmış en iyi 30 kombinasyon

---

## Aşamalar

- [x] **Aşama 1**: Çekirdek altyapı (`core/` modülleri)
- [x] **Aşama 2**: Strateji kodu (`S01_ICT_Breaker/backtest.py`) ve doğrulama
- [ ] **Aşama 3**: 6 ana parite için veri çekimi (`scripts/fetch_historical_data.py`)
- [ ] **Aşama 4**: Çoklu parametre testi (`run_all.py`) — 210 kombinasyon
- [ ] **Aşama 5**: Sonuç analizi ve en iyi parametrelerin belirlenmesi

---
**Not:** Her yeni strateji için `strategies/S0X_IsimStratejisi/` şablonu kopyalanıp özelleştirilecektir.
