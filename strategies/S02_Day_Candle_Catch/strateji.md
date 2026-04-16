# S02 — Day Candle Catch Stratejisi

## Özet
Bir paritenin, bir önceki günün en yüksek (PDH) veya en düşük (PDL) seviyesini süpürüp (sweep) asıl yönüne dönmesi varsayımına dayanır. Fiyat, gün açılışından sonra kendine en yakın olan dünkü tepe veya dip seviyesini hedefler. Bu seviyeye ulaştıktan sonra alt zaman diliminde (LTF - örn. H1 veya M15) bir dönüş onayı (Market Structure Shift vb.) aranır ve işleme girilir.

---

## Zaman Dilimleri
| Rol     | Zaman Dilimi | Kullanım                                |
|---------|--------------|-----------------------------------------|
| HTF     | Daily (D1)   | Önceki Günün Yükseği (PDH) ve Düşüğü (PDL) tespiti |
| LTF     | H1 / M15     | PDH/PDL teması sonrası dönüş (reversal) onayı |

---

## Kural Seti

### 1. HTF Seviyelerinin Belirlenmesi
- Her yeni işlem gününde, **bir önceki günün** (Previous Day) en yüksek seviyesi (PDH) ve en düşük seviyesi (PDL) referans alınır.
- Fiyat, bu iki seviyeden hangisine daha yakınsa gün içinde önce o seviyeyi test etme eğilimindedir. (Ancak strateji gereği her test edilen seviye bir potansiyel dönüş noktasıdır).

### 2. Temas (Sweep) ve Beklenti
- **Fiyat PDH'yi test ederse (yukarı yönlü sweep):** Paritenin günlük zirvesini yapıp aşağı döneceği varsayılır. Bu durumda **Short (Satış)** fırsatı aranır.
- **Fiyat PDL'yi test ederse (aşağı yönlü sweep):** Paritenin günlük dibini yapıp yukarı döneceği varsayılır. Bu durumda **Long (Alış)** fırsatı aranır.

### 3. LTF Giriş Kurulumu (Dönüş Onayı)
Fiyat HTF'de ilgili seviyeye ulaştıktan sonra, doğrudan işleme girilmez. Fiyatın döndüğünü teyit etmek için LTF'de bir onay aranır:

**Bullish Reversal (PDL temasından sonra Long için):**
1. Fiyat PDL'nin altına sarkar (Likidite süpürülür - Sweep).
2. LTF'de, fiyat son oluşturduğu *Swing High* seviyesinin üzerinde kapanış yapar. (Market Structure Shift - MSS).
3. **Giriş**: MSS oluştuktan sonra, geri çekilmede (örneğin hareketin başladığı mum veya kırılım seviyesi) işleme girilir. (Bu backtest modülünde, kırılımı yapan mum yakınlarından uygun bir FVG veya Breaker Block aranabilir).

**Bearish Reversal (PDH temasından sonra Short için):**
1. Fiyat PDH'nin üstüne çıkar (Likidite süpürülür).
2. LTF'de, fiyat son oluşturduğu *Swing Low* seviyesinin altında kapanış yapar. (MSS).
3. **Giriş**: MSS onayı sonrası geri çekilmede işleme girilir.

---

## Risk Yönetimi
| Parametre    | Değer / Kural                                         |
|--------------|-------------------------------------------------------|
| Stop Loss    | Günün oluşturduğu yeni Dip (Long) / yeni Tepe (Short) bölgesinin hemen altı/üstü. |
| Take Profit  | Karşı likidite noktası veya sabit Min RR hedefine ulaşıldığında. |
| Min RR       | 2:1 veya 3:1 (varsayılan, ayarlanabilir)              |
| Pozisyon     | 1.0 standart birim risk.                              |

---

## Çalıştırma
```bash
# Kök dizinden tek sembol test etmek için
python strategies/S02_Day_Candle_Catch/backtest.py --symbol XAUUSD --ltf H1

# Tüm semboller ve parametre kombinasyonları için
python strategies/S02_Day_Candle_Catch/run_all.py
```
