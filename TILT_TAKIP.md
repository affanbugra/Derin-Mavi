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
