# Açık İşler

> Bekleyen, **karar ya da donanım gerektiren** işler. Biri kapanınca buradan silinir
> (gerekiyorsa ayrıntısı CLAUDE.md'ye yazılır). Son güncelleme: 22.09.2026.

## 1. E-Stop'ta tilt park etsin mi, olduğu yerde mi donsun? — *ekip kararı*
- `kontrol.py` E-Stop'ta tilt'i **0° park** konumuna indiriyor (CLAUDE.md §5.1).
- `kapi_testleri.test_estopta_iki_eksen_de_oldugu_yerde_donar` ve `mock_esp32.py` testi
  **iki eksenin de olduğu yerde donmasını** bekliyor → **tek kırmızı kapı testi bu (25/26).**
- Şartname Yetenek 3: *"hareket ederken E-Stop → sistem durur"*. Park etmek de bir hareket,
  videoda "durmadı" gibi görünebilir.
- ⚠ Karar verilmeden kodu teste ya da testi koda uydurmayın.

## 2. Dikey eksenin dişli oranı ölçülmedi — *mekanik ölçüm*
- `protokol.py` testi `TILT_STEP_DER = 17.778` (1:1) bekliyor, sabit **8.889** (2:1;
  firmware `TILT_GEAR_RATIO = 0.5`) → `python app/protokol.py` kırmızı.
- Gerçek oran ölçülmeden test de sabit de düzeltilmemeli. Yanlışsa **bütün tilt açıları yanlış.**
- Değişecek iki yer: `protokol.py` ve firmware `TILT_GEAR_RATIO`.

## 3. Firmware karta yeniden yüklenmeli — *fiziksel adım*
- Dikey tavan 21.09'da 180 → **60°** oldu (fiziksel −30…+30). `protokol.py` ve `.ino` güncel.
- Yüklenene kadar kart eski 180'i bildirir, arayüz **"firmware uyumsuz"** uyarısı verir (kasıtlı).
- Kurulum adımları README'de (ESP32S3 Dev Module, USB CDC On Boot **kapalı**).

## 4. Yasak alan düğmeleri Otonom modda görünmüyor — *arayüz kararı*
- Atışa/Harekete Yasak kapsülleri yalnız Manuel panelde. Kurallar Otonom'da **da işliyor**,
  ama operatör Otonom'dayken göremiyor ve değiştiremiyor.
- Otonom panele de konulsun mu? Karar verilmeli.

## 5. Windows'ta dahili kamera harici sanılabilir — *sahada kontrol*
- `app/kamera.py` kameraları **isimden** eliyor. Bazı Windows laptopların dahili kamerası
  USB kamerayla aynı adla görünür (ör. "USB2.0 HD UVC WebCam").
- Yarışma laptopunda denenmeli. Yanlış kamera açılırsa adı `HARICI_DEGIL` listesine tek satır eklenir.

## 6. Donanımda hiç denenmeyenler
- Motor hareketi (P/T komutları) gerçek mekanikte · hız kademelerinde adım kaçırma sınırı.
- Lazerin fiziksel tetiklenmesi: PWM frekansı (1 kHz varsayım), 3.3 V / 5 V mantık seviyesi,
  GPIO 18'e **10 kΩ pull-down**.
- Otonom takibin gerçek kamera ve gimbal ile akıcılığı (`NISAN_MESGUL_ORANI` ayarı).
- Gamepad (DualSense) ile uçtan uca deneme.
- E-Stop butonu **NO → NC** geçişi (kablo koparsa NO buton E-Stop'u sessizce devre dışı bırakır).

## 7. Yazılımda eksik kalanlar
- **Balon sınıfı modelde yok** → nişan maket gövdesine düşüyor. Sıradaki eğitimin 1 numaralı işi.
- **Dwell** (lazeri balonun üstünde tutma) mantığı yok.
- **Aşama-1 zarf sırası** bağlanmadı: sürükle-sırala kartların sırasını hiçbir yer okumuyor.
- **Homing** (limit switch) yok. `home()` şimdilik yalnız "0°'a dön" demek.
- Tur sayacı yalnız gösterge, gerçek tur ilerleme mantığı yok.
