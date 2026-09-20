# Dikey eksen (tilt) takibi — ESP32-S3 + HSD57 kol-biyel mekanizması

**Hedef:** arayüzde seçilen hedefi **yalnızca yukarı-aşağı ekseninde** takip etmek.
Yatay (pan) eksen bu aşamada değişmedi.

Bu dal (`tilt-takip`), dikey ekseni eski AccelStepper kartından alıp
**ESP32-S3 + HSD57 kapalı çevrim** kartına taşır. Pan tarafı ve ateş/E-Stop
zinciri aynen kalır.

---

## Neden ayrı bir kart ve ayrı bir protokol?

Tilt artık doğrudan tahrik değil, **krank + biyel** mekanizmasıyla sürülüyor:

| | Eski tilt | Yeni tilt |
|---|---|---|
| Sürüş | AccelStepper, doğrudan | HSD57 kapalı çevrim, kol-biyel |
| Komut | `T<derece>` | `G<derece>` |
| Açı ↔ adım | formülle (`TILT_STEP_DER`) | **ölçülmüş kalibrasyon tablosu** (doğrusal değil) |
| Çalışma aralığı | 0–180° (yazılımsal) | **0–60°** (mekanik) |
| Konum geri bildirimi | **yok** | **var** (`STATE3`, 100 ms'de bir) |

Kol-biyel mekanizmasında motor açısı ile kol açısı doğrusal değildir; "60 derece"yi
formülle hesaplayamazsınız. Kart bu yüzden ölçülmüş bir tablo tutar ve bunu
kalıcı belleğinde (NVS) saklar — bir kez kalibre edilir, resetten sonra da yaşar.

---

## Kurulum sırası

### 1. Firmware

`ws_motor_test/esp32_ws_test/esp32_ws_test.ino` karta yüklü olmalı
(ESP32S3 Dev Module, USB CDC On Boot = **Enabled**). Sürücü **6400 pulse/tur**
ayarında, GPIO4 = PULSE, GPIO5 = DIR.

### 2. Kalibrasyon — **önce bu, bir kez**

Derin Mavi kalibrasyon **yapmaz**, yalnızca **bakar**. Kalibrasyon ayrı araçla yapılır:

```bash
python ws_motor_test/keyboard_control.py --port COM3
```

Kol fiziksel olarak en altta (0°) iken "Kontrolü aç" → "0 konumunda kalibrasyona
başla" → W/S ile ilerleyip ölçtüğün açıları kaydet → 60° ile tamamla.
Ayrıntı: `ws_motor_test/README_TR.md`.

> **Neden Derin Mavi bu işi yapmıyor:** `K` komutu karttaki **kayıtlı tabloyu
> siler**. Kazara tetiklenmesi (yanlış tuş, otonom döngüde bir hata) mekaniği
> dayamaya sürebilir. Kalibrasyon, kolun fiziksel olarak 0'da olmasını ve açının
> harici ölçülmesini gerektiren bir kurulum işidir — otonom bir uygulamanın
> içinde olmamalı.

Kalibrasyon bitmeden Derin Mavi **hiçbir hareket komutu göndermez**; alt çubukta
`Tilt Kartı · KALİBRE DEĞİL` yazar.

### 3. Uygulamayı başlat

`keyboard_control.py`'yi **kapat** (aynı portu iki uygulama açamaz), sonra:

```bash
set DERINMAVI_TILT=COM3 && python app/arayuz_qt.py
```

Donanımsız denemek için:

```bash
set DERINMAVI_TILT=mock && python app/arayuz_qt.py
```

| `DERINMAVI_TILT` | Ne olur |
|---|---|
| yok / `off` | **varsayılan** — tilt eski kartta kalır, hiçbir davranış değişmez |
| `mock` | sahte ESP32-S3 kartı (donanımsız uçtan uca test) |
| `COM3` | gerçek kart |

Pan tarafı ayrı: `DERINMAVI_ESP` eskisi gibi çalışır. Yalnız tilt kartıyla
denemek için `DERINMAVI_ESP=off` verilebilir.

### 4. Takip

Otonom moda geç, **HEDEFLER** listesinden aracı seç. Sistem dikeyde onu takip eder.
Yatay eksen bu aşamada takip etmez.

---

## Mimari — hareketin tek kapısı korundu

```
algi.analiz_et  →  nisan.PDNisanci.adim()  →  piksel hatası → derece
      ↓
arayuz_qt._nisan_geldi        hız kırpması + meşgul kapısı
      ↓
arayuz_qt._aci_hareket        ⟵ E-STOP · YASAK ALAN · AÇI LİMİTİ (tek kapı)
      ↓
kontrol.Kontrol.aci()         ⟵ eksen yönlendirmesi BURADA
      ↓                               ↓
  pan → eski kart            tilt → tilt_surucu.TiltSurucu → ESP32-S3
```

Arayüz yeni kartı **bilmez**. Yönlendirme yalnızca `kontrol.aci()` içindedir;
böylece E-Stop, atışa/harekete yasak alan ve açı limiti otonom modda da aynen
uygulanır. İkinci bir yol açılsaydı bu kontrollerden **kaçan** bir hareket yolu
oluşurdu.

### Yeni dosyalar

| Dosya | İş |
|---|---|
| `app/tilt_surucu.py` | Kartın laptop tarafı: `G`/`E`/`H`/`X`, `STATE3` çözümü, sahte kart |
| `app/tilt_takip_testi.py` | Kapalı çevrim benzetimi (pencere/kamera/kart gerektirmez) |

### Değişen dosyalar

| Dosya | Değişiklik |
|---|---|
| `app/kontrol.py` | `tilt` sürücüsü, `aci()` yönlendirmesi, `tilt_olculen`/`tilt_tavan`, E-Stop farkı |
| `app/arayuz_qt.py` | Dikey referans ölçülen açı (otonom), 60° tavan, "Tilt Kartı" durum çipi, reset uyarısı |

---

## İki kritik tasarım kararı

### 1. Otonom takipte referans **ölçülen** açıdır

`d_pitch`, kameranın gördüğü piksel hatasından türer — yani kolun **gerçek**
konumuna göre ölçülmüş bir hatadır. Onu *yazılımın inandığı* açıya eklemek iki
farklı referansı toplamaktır.

Ölçüldü (`app/tilt_takip_testi.py`, 25° hedef, kol 0°'dan başlıyor):

| Referans | Sonuç |
|---|---|
| **Ölçülen açı** (bu daldaki davranış) | −533 px → **−13.7 px**, aşma yok, kol 24.4°'de yerleşti |
| İnanç açısı (eski davranış) | **554 px aşma**, sönmeyen salınım; yazılım 34.8° sanırken kol 3.0°'de |

Bu, `CLAUDE.md` 13.08 kaydındaki salınımın aynısıdır. `taban_olculen` yolu
"gereksiz karmaşıklık" diye sadeleştirilirse test 9 patlar.

**Manuelde inanç referansı korunur:** operatör yön tuşuna üçüncü kez bastığında
kol hâlâ hareket hâlinde olsa bile "3 adım yukarı" bekler.

### 2. Karta **bayat hedef** girmez

Firmware'de tek bekleme yuvası var: hareket hâlindeyken gelen yeni hedef
sıraya girer, kart **önce mevcut hedefe gider**, sonra bekleyene yönelir.
Takipte bu "önce eski hedefe kadar git, sonra geri dön" demektir.

Çözüm PC tarafında: komutlar kart **boştayken** gönderilir, beklerken tek yuvalı
"en yenisi kazanır" kuyruğunda tutulur (`tilt_surucu.TiltSurucu._bosalt`).
Benzetimde 121 karede yalnız **15 komut** gitti; kart hiç bayat hedef görmedi.

---

## Manuel basılı-tutma — neden yavaştı, ne değişti

Şikâyet: *"yukarı bastıktan sonra tepkiyi geç veriyor, açılar arasında yavaş hareket ediyor."*

**Kök sebep:** arayüz 50 ms'de bir **2°'lik** yeni hedef gönderiyordu. Firmware her
hedefe yavaşlayarak yaklaşır (`MotionCore::schedule` → `sqrt(2·ACCEL·kalan)`) ve
hedefe varınca hızı **sıfırlar**. Yani kol "ilerle-dur-ilerle-dur" yapıyor, tepe
hıza **hiç** çıkmıyordu.

**Çözüm:** basılı tutulunca karta **tek bir "sınıra kadar git" komutu** verilir;
tuş bırakılınca `X`. Kart kendi ivme profiliyle tepe hıza çıkar. Sınır ve yasak
alan komutun **içine** gömülür — böylece kartın nerede duracağını bilmesi için
PC'nin "şimdi dur" demesine yetişmesi gerekmez (100 ms'lik yoklamada 36°/s = 3-4°
aşma demekti).

**Gerçek kartta ölçüldü** (0→20°, kalibrasyon 2675 darbe/60°):

| | Süre | Hız |
|---|---|---|
| Eski (50 ms'de 2°) | 3.99 s | 5.0 °/s |
| Yeni (tek uzak hedef) | 1.18 s | **17.0 °/s** |

**3.4 kat**, üstelik duraksamasız. Uzun hareketlerde fark daha büyür (ivmelenme
payı oransal olarak küçülür); 0→60° teorik ~2.2 s ≈ 28 °/s.

Daha da hızlı istenirse tavan **firmware sabitleridir** — `motion_core.h`'de
`MAX_SPEED=1600` darbe/s (= 36 °/s) ve `ACCEL=3200`. `ws_motor_test/README_TR.md`
bunların optimum ayar olmadığını zaten söylüyor. Yükseltmek mekanikte adım kaçırma
/ sürücü alarmı riski taşır, kademeli ölçülmeli — **bu dalda değiştirilmedi.**

YÜKSELİŞ etiketi artık **ölçülen** açıyı gösterir. Basılı tutarken komut "sınıra
kadar git" olduğu için hedef 60 yazardı, kol ise yolun ortasında olurdu.

## Kazanç ayarı — tavanı mekanik değil GECİKME belirliyor

`ayarlar.json`'da `kp=0.25, kd=0.0` vardı. Bu değerler eski mimaride (geri
bildirimsiz, inanç referanslı) yaşanan salınımı bastırmak için düşürülmüştü.

Taranınca görüldü ki **gecikmesiz bir benzetim yanıltıyor**: orada kp 0.90'a kadar
aşma çıkmıyor. Kamera + çıkarım gecikmesi modellenince tablo değişti
(gerçek kalibrasyon 2675 darbe/60°, 15 FPS):

| kp / kd | gecikmesiz | 1 kare (67 ms) | 2 kare (133 ms) |
|---|---|---|---|
| 0.25 / 0.00 | yerleşme 3.9 s · hareketli hata **72 px** | aynı | aynı |
| 0.50 / 0.06 | 2.7 s · 31 px | aşma yok | aşma yok · 40 px |
| **0.60 / 0.06** | **2.6 s · 31 px** | **aşma yok** | **aşma yok · 34 px** |
| 0.70 / 0.06 | 2.2 s · 25 px | 14 px aşma | **70 px aşma, 3 yön değişimi (SALINIM)** |
| 0.90 / 0.06 | 2.0 s · 28 px | aşma yok | **132 px aşma** |

Seçilen: **kp = 0.60, kd = 0.06.** Hareketli hedefteki kalıcı hata 72 → 34 px
(**2.1 kat**), 133 ms gecikmede salınım yok.

`kd` yüksek kp'de işi **kötüleştiriyor** (türev, gecikmiş hatayı büyütür) — 0.70'te
kd=0 kararlı, kd=0.06 salınıyor. Kazancı yükseltmek isteyen bunu bilmeli.

Bu tavan artık bir testle korunuyor: `tilt_takip_testi.py` test 10, `ayarlar.json`'ı
okuyup 133 ms gecikmeyle salınım arar. kp 0.90'a çekilince kırmızıya düştüğü
doğrulandı.

## Tespit ayarları — düzeltilenler

| Ayar | Eski | Yeni | Neden |
|---|---|---|---|
| `sahi` | 1 | **0** | SAHI açıkken `_analiz_sahi` çalışır ve kendi notuyla *"ByteTrack takibi DEVRE DIŞI: nesneler ID almaz"* — ID yoksa hedef kilidi de yok, **takip çalışamaz** |
| `cozunurluk` | 1280 | **640** | Model 640'ta eğitilmiş; CLAUDE.md §6/12 bunu 3 FPS sorununun sebebi olarak kaydetmiş |
| `iou` | 0.90 | **0.70** | NMS eşiği; 0.90'da çakışan kutular pratikte hiç elenmiyordu |
| `kararlilik` | 120 | **30** | ByteTrack `track_buffer`; 60 FPS'te 120 kare = ölü takipler ~2 sn ekranda |
| `kamera_fps` | 60 | 60 (**değişmedi**) | OBSBOT Meet 2 gerçekten 60 veriyor — ölçüldü |

Eski dosya `app/ayarlar.json.yedek`'te.

## Kamera — OBSBOT Meet 2

Ölçüldü (DirectShow, index 1):

| Format | Çözünürlük | Ölçülen FPS |
|---|---|---|
| MJPG | 1920×1080 | 59.6 |
| MJPG | **1280×720** | **60.2** |
| MJPG | 640×480 | 30.1 |
| YUY2 | 1280×720 | 60.0 |

Uygulamanın kendi kamera yolu (`algi.open_camera`) kamerayı **1280×720 MJPG @ 60 FPS**
açıyor — yani ayar zaten doğru, değiştirilmedi. Açılış ~4 s sürüyor (DSHOW taraması).

⚠ Kodda zaten bir not var: OBSBOT **MSMF backend'inde 21 s asılı kalıyor**. Tarama
DSHOW'u önce denediği için sorun çıkmıyor; backend sırası değiştirilmemeli.

## Güvenlik — eskiden farklı olan davranışlar

| Konu | Davranış |
|---|---|
| **E-Stop** | Kol **olduğu yerde durur**, 0°'a **park etmez**. Acil durdurma yeni bir hareket başlatmamalı. ⚠ Lazer bu kola binecekse takım bu kararı yeniden değerlendirmeli. |
| **Canlılık** | Arayüzün 250 ms'lik yoklama döngüsü durursa (uygulama donar/kapanır) kart 350 ms içinde **kendini kilitler**. Nabız bilerek okuma döngüsüyle aynı kaderi paylaşır. |
| **Kart reset** | Firmware her açılışta "kol fiziksel olarak 0'da" **varsayar**. Kol yukarıdayken reset olursa bildirdiği açı **yalandır** ve dışarıdan hiçbir belirtisi yoktur. Sürücü bunu yakalar (sayaç 0'a döndü + kontrol kapalı), arayüz kırmızı uyarı basar. |
| **Açı aralığı** | 0–60°. Kaydırıcı, yasak alan spinner'ları ve kontrol katmanı hep bu tavandan türer. |
| **Kalibrasyonsuz** | Hiçbir hareket komutu gitmez. |

---

## Test

Donanım, kamera ve pencere gerektirmez; saniyeler sürer:

```bash
python app/tilt_surucu.py && python app/kontrol.py && python app/tilt_takip_testi.py
```

---

## Sonraki adım (bu dalda **yok**)

- **Yatay (pan) eksende takip** — asıl hedef bu; dikey çalıştıktan sonra.
- **Firmware'de kesintisiz yeniden planlama.** `MotionCore` hedefe varmadan yeni
  hedefe geçemiyor. Eklenirse `tilt_surucu`'daki kuyruk kaldırılabilir ve takip
  belirgin biçimde akıcılaşır. Şu anki çözüm firmware'e **hiç dokunmaz**.
- **Kp/Kd sahada ölçülmeli.** Benzetim bir mantık/kararlılık testidir; gerçek
  motor ivmesini, mekanik esnemeyi ve kamera gecikmesini kapsamaz.
- Kol hızının mekanizma oranına göre gerçek değeri ölçülüp `HIZ_TABLO`
  karşılığı gözden geçirilmeli.
