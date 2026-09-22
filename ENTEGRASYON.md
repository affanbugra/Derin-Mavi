# ENTEGRASYON NOTU — Arayüz dalını motor/kalibrasyon çalışmasıyla birleştirme

> **Tarihsel kaynak notu.** Bu metin Affan'ın arayüz dalı için yazılmıştır; aşağıdaki
> 0–60° arayüz açısı, eski P/T motor yolu ve "yalnız birkaç sabit" birleştirme
> varsayımı `final_v1` için geçerli değildir. Gerçekleştirilen birleşmenin doğru
> mimarisi ve testleri [FINAL_ENTEGRASYON.md](FINAL_ENTEGRASYON.md) içindedir.

> **Kime:** gimbal motorlarını, sürücü/kart ayarlarını ve kalibrasyonu yapan ekip
> arkadaşına (ve birleştirmeyi yapacak yapay zekâya).
> **Dal:** `Affan-arayuz-aci-ikon` · **Tarih:** 22.09.2026
> **Kısaca:** Arayüz tarafı bu dalda baştan yazıldı. Motor/kart tarafındaki gerçek
> ölçümleriniz ile buradaki arayüz **çakışmaz**; ikisi `app/protokol.py` üzerinden
> buluşur. Bu dosya tam olarak o buluşma noktasını anlatır.

---

## 0. Önce bunu oku: birleştirme stratejisi

Arayüz dalı **çok sayıda dosyaya** dokundu (arayüz, algı, kontrol, protokol, yeni
modüller). Motor çalışması ise tipik olarak **birkaç sabite + firmware'e** dokunur.
Bu yüzden önerilen yön:

1. **Taban bu dal olsun** (`Affan-arayuz-aci-ikon`).
2. Sizin taraftan yalnızca şunlar taşınsın:
   - `esp32/derin_mavi_esp32/derin_mavi_esp32.ino` (karta gerçekten yüklediğiniz sürüm),
   - **mekanik/kalibrasyon sabitleri** (aşağıda §4 listesi),
   - ölçülmüş hız/ivme değerleri.
3. Ardından §8'deki kontrol listesi baştan sona işletilsin.

Tersi yön (arayüzü eski dala taşımak) **çok daha pahalıdır**: aşağıdaki her şeyin
yeniden yazılması gerekir.

---

## 1. Bu dalda ne var (sizde olmayanlar)

| Konu | Dosya | Ne yapar |
|---|---|---|
| Kontrol istasyonu | `app/arayuz_qt.py` | Manuel/Otonom mod, aşama seçimi, canlı görüntü, açı karoları, alt durum çubuğu |
| **Harekete / atışa yasak alan** | `app/bolge.py` | Operatör **izinli pencere** yazar; dışına çıkılamaz (hareket), dışında ateş edilemez (atış) |
| **Oyun kolu (gamepad)** | `app/gamepad.py`, `app/kol_ikon.py` | Kolla sürüş + ekranda kol resmi; basılan tuş yanar |
| Kamera | `app/kamera.py` | **Yalnız harici USB kamera** açılır (dahili/telefon/sanal elenir) |
| Görünüm | `app/tasarim.py` | Tüm renk/ölçü/QSS tek kaynakta (Apple macOS dili) |
| Kontrol katmanı | `app/kontrol.py`, `app/protokol.py`, `app/mock_esp32.py` | Karta giden tek kapı + donanımsız çalışma |
| Otonom nişan | `app/nisan.py`, `app/algi.py` | Piksel hatası → açı (PD), hedef takibi |
| Güvenlik testleri | `app/kapi_testleri.py` | Pencere açmadan E-Stop/ateş/yasak alan denetimi |

**Yeni davranış kuralları (özet):**
- **Ateş:** klavyede `Space`+`B` **2 sn basılı**, kolda `L2`+`R2` **2 sn basılı**.
  Ateş açıkken tek dokunuş keser. `Esc` her durumda keser. Tek tuşla ateş **yoktur**.
- **Merkeze alma:** MERKEZ butonu / `R` / `L1`-`R1` **2 sn basılı**; dönüş **anında
  değil, motorun tavan hızıyla adım adım** yapılır.
- **Yatay hareket ±90° ile sınırlı (yapısal).** Operatör aracın arkasında durur;
  namlu arka yarıya giremez. Kapatılamaz, yalnız daraltılabilir.
- **Dikey 0…60° sistem açısı** = fiziksel −30…+30 (sistem 0 = namlu 30° aşağı).
- E-Stop: önce ateş, sonra hareket kesilir; arayüz de kartın kendi durmasını yakalar.

---

## 2. Arayüz sistemle NASIL konuşur (sözleşme)

Arayüz motoru **doğrudan sürmez**. Tek yol:

```
arayüz  →  kontrol.py  →  protokol.py  →  (pyserial) →  ESP32  →  sürücü → motor
```

### 2.1 Karta giden komutlar (ASCII satır, `\n` ile biter)

| Komut | Anlamı | Birim / aralık |
|---|---|---|
| `P<derece>` | **Yatay MUTLAK hedef açı** | derece, işaretli ve **sürekli** (sarmaz) |
| `T<derece>` | **Dikey MUTLAK hedef açı** | derece, **0…60** (sistem açısı) |
| `S<derece/sn>` | Tavan hız | derece/sn |
| `A<derece/sn²>` | İvme | derece/sn² |
| `G<yüzde>` | Lazer gücü (PWM duty) | 0…100 |
| `L1` / `L0` | Ateş aç / kes | — |
| `STOP` / `START` | Acil durdur / devam | — |

**Kritik üç nokta:**

1. **Açı MUTLAKTIR, delta değil.** Laptop her seferinde "şu açıya git" der. Kaybolan
   bir komut kalıcı sapma yaratmaz, ateş komutu süregelen hareketi bozmaz. Firmware
   `moveTo()` kullanmalıdır, `move()` değil.
2. **Birim DERECEDİR, step değil.** İki eksenin dişli oranı farklı olduğu için aynı
   step/sn iki eksende bambaşka açısal hız demektir. Dereceden step'e çevirim
   **kartın işidir**; laptop step saymaz.
3. **Yatay açı sarmaz.** Ekranda 0–360 gösterilir ama karta işaretli sürekli açı
   gider (ör. sola 30° = `P-30`). Sarsaydı motor kısa yoldan değil ters yönden dönerdi.

### 2.2 Karttan BEKLENEN metinler

Kart yapısal durum paketi yollamıyor; arayüz **insan-okur satırları** ayrıştırır
(`app/protokol.py` içindeki `satir_*` fonksiyonları). Firmware bunları üretmelidir:

| Satır (içinde geçmesi yeter) | Ne zaman | Arayüz ne yapar |
|---|---|---|
| `SISTEM AKTIF` (açılış banner'ı) | reset / açılış | Kartın yeniden başladığını anlar, iki tarafın referansını sıfırlar |
| `TILT_MAX: 60.0` | açılış banner'ında | Firmware/arayüz tavanı uyuşmazsa **uyarı verir** |
| `Konum P<aci> / T<aci>` | **acil durdurmada** | Ekranı kartın gerçek konumuna çeker |
| içinde `DURDURUL` geçen satır | E-Stop'a girince | Ateşi bırakır, arayüzü E-Stop'a alır |

> Bu satırlar yoksa sistem yine çalışır ama **acil durdurmadan sonra ekrandaki açı
> gerçek konumdan kopabilir**. Firmware'iniz farklı metinler yazıyorsa iki seçenek
> var: ya firmware'i bu metinlere uydurun, ya `protokol.py`'deki `satir_*`
> fonksiyonlarını kendi metinlerinize uydurun (tek dosya, dört küçük fonksiyon).

### 2.3 ⭐ Ölü adam anahtarı (lazer için, atlanmamalı)

Lazerin **açık kalması** için karta **250 ms'de bir `L1` tazelemesi** gider
(`protokol.ATES_TAZELE_MS`). Kart **1 sn** tazeleme almazsa lazeri **kendi kesmelidir**
(`protokol.ATES_ZAMAN_ASIMI_MS`, firmware'de aynı değer).

Sebep: "kes" komutunun gideceğine güvenilemez — kesmenin gerektiği durumların
çoğunda (kablo koptu, laptop çöktü, arayüz dondu) komut zaten gidemez. "Açık kal"
demeyi sürdürmek, "kapan" demeyi beklemekten güvenlidir.

**Lazer henüz bağlı değilse:** `G`/`L1`/`L0` komutları zararsızdır (kart pini
sürer, uçta bir şey yoktur). Firmware bu komutları **tanımıyorsa** bilinmeyen komut
olarak yok sayması yeterlidir; arayüz çalışmaya devam eder. Lazer bağlanınca
**önce ölü adam anahtarını** firmware'e ekleyin.

---

## 3. Arayüzün çağırdığı fonksiyonlar (girdi/çıktı)

Hepsi `app/kontrol.py` içindedir. Motor tarafını değiştirirken **bu imzalar sabit
kalmalıdır**; arayüzün başka hiçbir yolu yoktur.

| Fonksiyon | Girdi | Karta giden | Not |
|---|---|---|---|
| `aci(pan_der, tilt_der)` | mutlak açı (derece) | `P…` / `T…` | Değişmeyen eksene komut gitmez |
| `ates(ac: bool)` | True/False | `L1` / `L0` | Tek ateş kapısı |
| `ates_tazele()` | — | `L1` | 250 ms'de bir (ölü adam) |
| `guc_ayarla(yuzde)` | 0–100 | `G…` | "Ne kadar" (kalıcı ayar) |
| `hiz_ayarla(seviye)` | 1/2/3 | `S…` + `A…` | Tablo: `protokol.HIZ_TABLO` |
| `estop(aktif: bool)` | True/False | `STOP` / `START` | |
| `home()` | — | `P0` + `T0` | Gerçek homing (limit switch) **yok** |
| `oku()` | — | — | Kart metinlerini okur, yukarıdaki satırları ayrıştırır |

Dönüş: hepsi arayüzün alt çubuğa yazdığı bir **durum sözlüğü** verir
(`pan`, `tilt`, `lazer`, `lazer_guc`, `estop`, `durum_ad`, `hiz_ad`).

**Bağlantı seçimi (ortam değişkeni):**

```bash
DERINMAVI_ESP=mock                 # varsayılan: sahte cihaz, donanımsız geliştirme
DERINMAVI_ESP=/dev/cu.usbserial-…  # macOS gerçek port
DERINMAVI_ESP=COM7                 # Windows gerçek port
DERINMAVI_ESP=off                  # kontrol katmanı kapalı (yalnız görüntü işleme)
```

> ⚠ `mock` iken alt çubukta ESP32 **sarı** yanar ve "sahte cihaz (kart takılı değil)"
> yazar. Yeşil **yalnız gerçek porta bağlıyken** görünür. Bunu karıştırmayın:
> sahte cihaz her komutu kabul eder, hiçbir motor dönmez.

Diğer ortam değişkenleri: `DERINMAVI_CAM` (test için video dosyası/RTSP),
`DERINMAVI_MODEL` (model yolu).

---

## 4. ⚙ BİRLEŞME NOKTASI: kalibrasyon sabitleri

Sizin ölçümleriniz **burada** karşılığını bulmalı. İki taraf (Python + firmware)
**aynı** değeri bilmek zorundadır.

`app/protokol.py`:

| Sabit | Şu anki değer | Anlamı |
|---|---|---|
| `STEP_TUR` | 6400 | Sürücü çözünürlüğü (1/32 mikroadım) |
| `PAN_DISLI` | 83/15 ≈ 5.533 | Yatay redüksiyon |
| `TILT_DISLI` | **0.5 — [VARSAYIM, ölçülmedi]** | Dikey redüksiyon **(sizde ölçüm varsa en kritik düzeltme budur)** |
| `MAKS_STEP_SN` | 8000 | AccelStepper'ın güvenli üst sınırı |
| `TILT_MIN/TILT_MAX` | 0 / 60 | Dikey sistem açısı tavanı |
| `HIZ_TABLO` | 15/40 · 40/100 · 75/200 | (tavan hız, ivme) derece/sn |
| `LAZER_GUC_VARSAYILAN` | 40 | PWM duty % |
| `ATES_TAZELE_MS` / `ATES_ZAMAN_ASIMI_MS` | 250 / 1000 | Ölü adam anahtarı |

Firmware karşılıkları: `TILT_MAX`, `TILT_GEAR_RATIO`, `PAN_GEAR_RATIO`, `STEP_PER_REV`,
`ATES_ZAMAN_ASIMI_MS`, `LAZER_GUC_VARSAYILAN` (isimler `.ino` içinde birebir böyle).

`app/bolge.py`:

| Sabit | Değer | Anlamı |
|---|---|---|
| `PAN_MAX` | 90 | **Yapısal** yatay sınır (ön yarı) |
| `TILT_FIZIKSEL_ALT` / `TILT_ARALIK` | −30 / 60 | Dikey fiziksel karşılık |

> **Uyuşmazlık nasıl fark edilir:** kart açılış banner'ında `TILT_MAX` yazarsa arayüz
> kendi değeriyle karşılaştırır ve uyuşmazsa uyarı verir. Diğer sabitlerde böyle bir
> koruma **yoktur** — el ile eşitlemek gerekir.

---

## 5. Arayüzün uyguladığı güvenlik kuralları (firmware'i rahatlatır ama YERİNE GEÇMEZ)

Laptop tarafı şunları zaten kırpar/engeller; yine de **firmware kendi tarafında da
kırpmalıdır** (seri monitörden elle komut yazan biri mekaniği kırmasın):

- Dikey **0…60** dışına komut gitmez.
- Yatay **±90** dışına komut gitmez.
- E-Stop'ta hiçbir hareket/ateş komutu gitmez.
- Atışa yasak alanın dışında lazer açılmaz; ateş sürerken bölgeye girilirse **kesilir**.
- Otonom nişan komutları motorun tavan hızına göre kırpılır ve komutlar üst üste
  binmesin diye "meşgul kapısı" uygulanır.

---

## 6. Görüntü/otonom taraf (kısaca)

- Kamera **yalnız harici USB kamera** açar (`app/kamera.py`). Dahili/telefon/sanal
  kameralar isimden elenir. Kamera yoksa uygulama açılır, "Kamera bulunamadı" der.
- Model `models/best.pt` (4 sınıf: DRONE/F16/FUZE/HELIKOPTER; **balon henüz yok**).
  CPU'da hızlandırmak için `yolo export model=models/best.pt format=openvino imgsz=640`
  (türetilmiş çıktı repoya girmez, herkes kendi makinesinde üretir).
- Otonom modda nişan zinciri: tespit → hedef kilidi → PD kontrol → `kontrol.aci(...)`.
  **Gerçek donanımda hiç denenmedi**; Kp/FOV kalibrasyonu gimbal bağlanınca yapılacak.

---

## 7. Çalıştırma ve test

```bash
python app/arayuz_qt.py          # uygulama (Windows'ta Baslat.bat, macOS'ta Baslat.command)

python app/protokol.py           # komut üretimi + sabitlerin tutarlılığı
python app/kontrol.py            # mock cihazla uçtan uca
python app/bolge.py              # yasak alan matematiği
python app/gamepad.py            # kol teşhisi (cihaz yoksa da çalışır)
python app/kol_ikon.py           # ekrandaki kol çizimi
python app/kamera.py             # kamera eleme kuralı
python app/algi.py  app/nisan.py app/tasarim.py
python app/kapi_testleri.py      # GÜVENLİK KAPILARI (pencere açmaz)
```

> **Bilinen tek kırmızı test:** `test_estopta_iki_eksen_de_oldugu_yerde_donar`.
> E-Stop'ta tilt'in 0°'a park etmesi mi, olduğu yerde donması mı gerektiği **ekip
> kararı bekliyor** (şartname Yetenek 3 "sistem durur" diyor; park etmek de bir
> harekettir). Kodu teste ya da testi koda uydurmadan önce bu karar verilmeli.

---

## 8. Birleştirme kontrol listesi (sırayla)

1. `Affan-arayuz-aci-ikon` dalını çek, `DERINMAVI_ESP=mock` ile aç — arayüz açılıyor mu?
2. Kendi firmware'inizi `esp32/derin_mavi_esp32/derin_mavi_esp32.ino` üzerine getirin;
   §2.1'deki komutları ve §2.2'deki metinleri destekliyor mu, satır satır karşılaştırın.
3. §4'teki sabitleri **ölçülmüş** değerlerle eşitleyin (Python + firmware birlikte).
4. Firmware'i karta yükleyin (dikey tavan **60**; eski 180'li sürüm uyarı verir).
5. `DERINMAVI_ESP=<port>` ile açın. Alt çubukta ESP32 **yeşil** ve port adı görünmeli.
6. **Motor bağlıyken ilk denemeler, lazer beslemesi KAPALI yapılmalı.**
7. Sırayla doğrulayın:
   - D-pad ile 1°'lik adımlar → ekrandaki açı ile gerçek dönüş **aynı mı**?
     (Değilse: dişli oranı sabitleri.)
   - Tuşu basılı tutma → hız kademesiyle uyumlu mu, adım kaçırıyor mu?
   - `±90` yatay ve `0…60` dikey sınırlarda duruyor mu?
   - MERKEZ 2 sn → kademeli dönüş; yolda yön verince duruyor mu?
   - ACİL DURDUR → hareket kesiliyor, arayüz kilitleniyor mu?
   - Kol takılıysa: D-pad ve çubuklar, ekrandaki kol resminde doğru tuşu yakıyor mu?
8. Lazer bağlanınca: önce ölü adam anahtarı, sonra `G`/`L1`/`L0`, en son ateş kapıları.

---

## 9. Bilinen açık konular

`ACIK_ISLER.md` dosyasına bakın. Özetle: E-Stop park kararı, dikey dişli oranı ölçümü,
firmware'in 60° tavanla yeniden yüklenmesi, gerçek donanımda hiç denenmemiş otonom
takip, modelde balon sınıfının olmaması.

**Gerçek donanımda denenmemiş her şey açıkça işaretlidir** (`CLAUDE.md` içinde
[VARSAYIM] etiketleri). Sizin motor tarafındaki ölçümleriniz bu varsayımların
çoğunu kapatacak — birleştirmenin asıl değeri budur.
