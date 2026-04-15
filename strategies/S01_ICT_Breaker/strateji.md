# S01 — ICT Dual Timeframe Breaker Stratejisi

## Özet
İki zaman dilimi kullanan, ICT konseptlerine dayalı mekanik bir giriş sistemi.
Daily grafikte likidite ve yapı analizi; H1 grafikte hassas giriş arayan bir Truva Atı yaklaşımı.

---

## Zaman Dilimleri
| Rol     | Zaman Dilimi | Kullanım                          |
|---------|--------------|-----------------------------------|
| HTF     | Daily (D1)   | Trend, MSB, Order Block, Zone     |
| LTF     | H1           | Giriş, Breaker tespiti            |
| Destek  | Weekly (W1)  | Haftalık trend → dinamik boyut    |

---

## Kural Seti

### 1. HTF Swing Analizi (3-Mum Sistemi)
- Orta mum komşularından yüksekse → **Swing High**
- Orta mum komşularından düşükse → **Swing Low**

### 2. Market Structure Break (MSB)
- Kapanış, önceki Swing High'ın üstünde → **Bullish MSB**
- Kapanış, önceki Swing Low'un altında → **Bearish MSB**

### 3. Order Block (OB)
- **Bullish OB**: Bullish MSB'yi oluşturan hareket öncesi son bearish (düşüş) mumu
- **Bearish OB**: Bearish MSB'yi oluşturan hareket öncesi son bullish (yükseliş) mumu

### 4. Premium / Discount Zonu
```
Range = Güncel Swing Low → Swing High
Mid   = (Range Low + Range High) / 2

Sadece Discount'ta (Mid altı) → Long ara
Sadece Premium'da   (Mid üstü) → Short ara
```

### 5. Breaker Giriş Kurulumu (LTF — H1)
Fiyat HTF OB bölgesine çekilince LTF'de aşağıdaki 3 adım aranır:

**Bullish Breaker:**
1. LTF'de Swing Low oluşur (Engineered Liquidity)
2. Fiyat o Swing Low'un altına sweep yapar (Liquidity Grab)
3. Sweep'e yol açan High'ın üzerinde kapanış → Market Structure Shift (MSS)
4. **Giriş**: Sweep öncesi son bearish mumun yüksekliği (Breaker Block high)

**Bearish Breaker:**
1. LTF'de Swing High oluşur
2. Fiyat o Swing High'ın üstüne sweep yapar
3. Sweep'e yol açan Low'un altında kapanış → MSS
4. **Giriş**: Sweep öncesi son bullish mumun düşüklüğü (Breaker Block low)

---

## Risk Yönetimi
| Parametre    | Değer / Kural                                         |
|--------------|-------------------------------------------------------|
| Stop Loss    | Sweep Low'un biraz altı (Long) / Sweep High üstü (Short) |
| Take Profit  | HTF External Range Liquidity (önceki Swing High/Low)  |
| Min RR       | 2:1 (varsayılan, ayarlanabilir)                       |
| Pozisyon     | 1.0 standart; Weekly + Daily trend hizalandığında 1.5x |

---

## Çalıştırma
```bash
# Kök dizinden
python strategies/S01_ICT_Breaker/backtest.py --symbol XAUUSD
python strategies/S01_ICT_Breaker/backtest.py --symbol EURUSD
```

Çıktı: `strategies/S01_ICT_Breaker/sonuclar.xlsx`
