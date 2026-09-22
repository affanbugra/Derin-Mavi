# Bu firmware artık Derin Mavi tarafından da sürülüyor

Bu klasördeki firmware (`esp32_ws_test`) ve `keyboard_control.py` değişmedi.
Yanına, görüntü işlemeden gelen **otomatik hedef takibi** eklendi:

    ../Derin-Mavi   (dal: tilt-takip)

Derin Mavi, arayüzde seçilen hedefi **dikey eksende** takip eder ve bu karta
aynı seri protokolle (`E` / `H` / `G<derece>` / `X`, `STATE3`) komut gönderir.
Firmware'e **hiç dokunulmadı**.

## Sıra önemli

1. **Kalibrasyon burada yapılır, bir kez.** Derin Mavi kalibrasyon yapmaz —
   yalnızca `STATE3`'teki `cal` bitine bakar. `K` komutu karttaki tabloyu
   sileceği için otonom uygulamanın içine konmadı.

   ```bash
   python keyboard_control.py --port COM3
   ```

   Kol fiziksel olarak en altta iken kalibrasyona başla, 60° ile tamamla.
   Ayrıntı: `README_TR.md`.

2. **Bu uygulamayı kapat.** Aynı seri portu iki uygulama açamaz; firmware zaten
   ikinci porttan gelen komutu `OTHER_PORT_ACTIVE` ile reddeder.

3. **Derin Mavi'yi başlat:**

   ```bash
   cd ../Derin-Mavi && set DERINMAVI_TILT=COM3 && python app/arayuz_qt.py
   ```

   Donanımsız denemek için `DERINMAVI_TILT=mock`.

## Bilinen sınır — takibi asıl kısıtlayan şey

`motion_core.h`'de tek bekleme yuvası var: hareket hâlindeyken gelen hedef
sıraya girer, kart **önce mevcut hedefe gider**, sonra bekleyene yönelir.
Takipte bu "önce eski hedefe kadar git, sonra geri dön" demek olurdu.

Şimdilik PC tarafında çözüldü: komutlar kart boştayken gönderiliyor, beklerken
"en yenisi kazanır" kuyruğunda tutuluyor (`Derin-Mavi/app/tilt_surucu.py`).
Firmware'e kesintisiz yeniden planlama eklenirse o kuyruk kaldırılabilir ve
takip belirgin biçimde akıcılaşır.

Tasarım kararları ve ölçümler: `../Derin-Mavi/TILT_TAKIP.md`
