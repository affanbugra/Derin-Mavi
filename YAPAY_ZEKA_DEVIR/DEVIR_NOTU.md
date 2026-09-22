# DEVİR NOTU — Derin Mavi: iki eksenli hedef takibi (pan + tilt)

Bu dosya, önceki yapay zekâ oturumlarında (Claude, **20–22 Eylül 2026**) yapılan her şeyin
eksiksiz özetidir. Yeni asistan: **önce bunu baştan sona oku**, sonra
`Derin-Mavi/CLAUDE.md` (özellikle §14 ve §14.1) ve gerekirse `Derin-Mavi/TILT_TAKIP.md`.

---

## 0. Kullanıcıyla çalışma kuralları (ÖNEMLİ)

- Kullanıcı **Türkçe** konuşur ("reisim", "abi" der). Cevaplar Türkçe olmalı.
- **Garip Türkçe teknik terim uydurma.** Kullanıcı açıkça istedi: gerekirse İngilizce terim kullan
  (örn. "trajectory mode", "position mode", "adaptive Kalman", "ROI", "tiling"). "Yörünge kipi"
  gibi ifadeler onu karıştırdı.
- **Testleri çok net anlat:** dronu sabit mi tutacak, hareket mi ettirecek, kaç metre, hangi hızda,
  ne kadar süre. Belirsiz talimat yüzünden bir test turu boşa gitti.
- Kullanıcının terminali **Windows PowerShell 5.1**: komut verirken `&&` değil `;` kullan.
- **GitHub'a push YOK.** "Yerelde yap, istersem ben atarım" dedi. **Commit de sormadan yapılmaz**
  (şu an her şey commit edilmemiş hâlde, bkz. §2).
- **Donanım güvenliği:** kullanıcı genelde sistemin başında, prizde bekliyor. Namluyu hareket
  ettirmeden önce ne olacağını söyle (hangi eksen, kaç derece). Motor gücü takılı olmayabilir,
  kontrol et.
- Bash aracında heredoc içinde `\n` bozuluyor (gerçek satır sonuna dönüşüyor). Dosya yamalarken
  Python betiğini Write aracıyla dosyaya yazıp çalıştırmak daha güvenli.

---

## 1. Proje ve hedef

- **Derin Mavi:** TEKNOFEST 2026 Çelikkubbe hava savunma yarışması (finaller 30 Eylül–4 Ekim).
  Kamera + YOLO ile hedef tespiti, lazerle maketin altındaki balonu patlatma.
  Repo: `github.com/affanbugra/Derin-Mavi`. Arayüz: PySide6 (`app/arayuz_qt.py`), `Baslat.bat` ile açılır.
- Başlangıç isteği: arayüzde seçilen hedefi **önce tilt (yukarı-aşağı)**, sonra **pan (sağ-sol)**
  ekseninde takip etmek. Şu an **iki eksen de çalışıyor**. Kullanıcının son hedefi:
  **takibi "çok iyi" seviyeye getirmek** ve uzak mesafede (10–15 m) çalıştırmak.
- Yarışma notları: Aşama 1 manuel, Aşama 2–3 otonom. Aşama 1–2'de tüm maketler kırmızı;
  Aşama 3'te düşman kırmızı, dost camgöbeği. İmha bandı ~10–15 m.

---

## 2. Klasörler ve git durumu

```
PROJE/
├── Derin-Mavi/            ← repo kopyası, dal: tilt-takip  (ASIL İŞ)
│   ├── app/               ← Python kodu (aşağıda)
│   ├── app/loglar/        ← canlı test kayıtları (CSV + kart kara kutusu .log)
│   ├── app/veri_toplama/  ← otomatik toplanan "zor örnek" kareler (repoya girmez)
│   ├── models/best.pt     ← YOLO11s, 640'ta eğitilmiş, 4 sınıf: DRONE F16 FUZE HELIKOPTER (BALON YOK)
│   └── CLAUDE.md          ← proje beyni (§14, §14.1 bu işin ayrıntılı günlüğü)
├── ws_motor_test/         ← ESP32-S3 firmware + C++ testleri (REPO DIŞI, git'te yok!)
│   ├── esp32_ws_test/     ← motion_core.h (tilt), pan_core.h, yorunge_core.h, esp32_ws_test.ino
│   ├── tests/             ← test_jog.cpp, test_firmware.cpp, stubs/Arduino.h
│   └── run_cpp_tests.cmd  ← MSVC ile testleri derleyip çalıştırır
├── YAPAY_ZEKA_DEVIR/      ← bu klasör
│   ├── resimler/          ← mekanizma, sürücü, kamera görüntüleri
│   └── araclar/           ← geçici test/benzetim betikleri (§10)
└── DERIN_MAVI_kontrol_mimarisi_devir.md ← başka bir oturumun önerdiği mimari (değerlendirmesi §11)
```

**Git:** dal `tilt-takip`, son commit `0702e51`. Üstünde **çok sayıda commit edilmemiş değişiklik** var:
`.gitignore, CLAUDE.md, README.md, app/algi.py, app/arayuz_qt.py, app/kapi_testleri.py, app/kontrol.py,
app/protokol.py, app/tilt_canli_takip.py, app/tilt_surucu.py, app/tilt_takip_testi.py,
esp32/derin_mavi_esp32/derin_mavi_esp32.ino` + yeni dosyalar `app/hedef_kestirici.py,
app/canli_eksen_dogrulama.py, app/canli_pasif_gozlem.py, app/kamera_gecikme_olc.py`.
Bu değişikliklerin bir kısmı **kullanıcının başka bir yapay zekâyla yaptığı** işler
(22.09 akşamı incelendi, hepsi tutuldu, bkz. §8). Commit etmeden önce kullanıcıya sor.

GitHub'a HTTPS bu makinede engelli (clone/push reset alıyor); gerekirse ZIP'i Python ile indir.

---

## 3. Donanım (resimler: `resimler/`)

| Parça | Gerçek |
|---|---|
| Kart | **ESP32-S3**, native USB **COM3** (VID 303A). CH343 yolu takılıysa COM4. `DERINMAVI_TILT=auto` STATE3 yayınından bulur. |
| Tilt | **GPIO4 PUL / GPIO5 DIR**, HSD57 kapalı çevrim sürücü, 6400 darbe/tur, **krank-biyel (kol-biyel)** mekanizma. Kalibrasyon kartın NVS'inde: 7 nokta, **60° = 2675 darbe** (kullanıcı namlu açısına göre yaptı). |
| Pan | **Aynı karta bağlı: GPIO10 PUL / GPIO11 DIR**, ENA GPIO16 **sürülmüyor** (bosta = etkin). Düz dişli **15→83** → **98.37 darbe/°** (90° sahada doğrulandı). `PAN_DIR_POS_HIGH=true` takiple doğrulandı (+ = sağ). |
| Kamera | **OBSBOT Meet 2**, 1280×720 MJPG @ **60 FPS**, DSHOW (MSMF asılıyor), index 0. **Namluyla birlikte döner.** Önünde siyah bir mekanik parça görüntünün altını kapatıyor. |
| Motor beslemesi | 24 V. Sürücü LED'leri yeşil = beslemeli. |
| Lazer | Bu işte hiç kullanılmadı/test edilmedi. |

⚠ **ESP32 eksenlerin yerini ÖLÇMEZ, darbe sayar.** Motor gücü kesilince kol yer çekimiyle
düşer, ESP eski sayıyı tutar (22.09'da kol en alttayken ESP 29.4° diyordu). Uygulama kapansa da
ESP resetlenmez, eksenler en son nerede kaldıysa oradadır. **Teste başlamadan önce kolun gerçek
yerini doğrula** (kamerayla: kol 0°'dayken kamera hafif aşağı, zemine/masaya bakar) ve gerekirse
kol en alttayken `R`, pan karşıya bakarken `PR` gönder (kalibrasyonu silmezler).

---

## 4. Firmware (`ws_motor_test/esp32_ws_test/`) ve protokol

115200 baud, satır sonu `\n`. Karta en son yüklenen sürüm aşağıdakilerin hepsini içeriyor.

| Komut | İş |
|---|---|
| `E` / `D` / `X` | kontrol aç / kapat / dur (X ve D iki ekseni birden durdurur) |
| `H` | nabız; **350 ms gelmezse kart kendini kapatır** (iki eksen de durur) |
| `G<der>` | tilt mutlak hedef 0–60 (position mode, hareket hâlinde durmadan yeniden planlar) |
| `Z<h>,<iv>` | tilt hız/ivme profili (darbe/s), yalnız dururken |
| `R` | "kol şu an en altta" — tilt sayacı 0, kalibrasyon korunur |
| `Q` | yetenek sorgusu (retarget var mı) |
| `K`, `C<der>`, `W/S`, `V…` | kalibrasyon/jog — **Derin Mavi K göndermez** (K tabloyu siler) |
| `P<der>` | pan mutlak hedef (sarmasız, ±400 yazılım sınırı) |
| `PR` / `PZ<h>,<iv>` / `PE0/PE1/PE-` | pan sıfırla / profil (tavan 12000 darbe/s, 150000 darbe/s²) / ENA teşhis |
| **`Y<der>,<der/sn>`** | **tilt trajectory mode**: kart referansı `p0+v·t` olarak kendisi ilerletir |
| **`PY<der>,<der/sn>`** | **pan trajectory mode** |
| `YQ` | trajectory mode desteği sorgusu (`OK,YQ`) |

Trajectory mode (`yorunge_core.h`): motor hızı `v + K·(referans − konum)`, **K=8**, ivme sınırlı,
eksen uçlarında zamanında fren. **150 ms yeni komut gelmezse yumuşakça durur** (saf hız komutunun
"iletişim koptu, motor koşuyor" riski yok). Y/PY'ye "OK" yazılmaz (hat dolmasın), hatalar yazılır.
Her tilt komutu tilt yörüngesini, her pan komutu pan yörüngesini keser; X/D ikisini.

Durum satırları 50 Hz (20 ms):
`STATE3,pos,target,upper,cal,moving,armed,commissioning,angle,goal,count,last_angle,speed`
`PAN1,pos,target,moving,angle,goal,en`

**Derleme / yükleme** (arduino-cli, Arduino IDE içinde):
```
"C:/Program Files/Arduino IDE/resources/app/lib/backend/resources/arduino-cli.exe" compile --fqbn "esp32:esp32:esp32s3:CDCOnBoot=cdc,USBMode=hwcdc" --output-dir "$TEMP/ws_build" esp32_ws_test
... upload -p COM3 --fqbn "esp32:esp32:esp32s3:CDCOnBoot=cdc,USBMode=hwcdc,EraseFlash=none" --input-dir "$TEMP/ws_build" esp32_ws_test
```
⚠ **Yüklemeden ÖNCE iki ekseni 0'a götür** (`E`, `P0`, `G0`, bekle) — yükleme reset atar,
sayaçlar 0 olur. `EraseFlash=none` şart (yoksa kalibrasyon silinir).
Firmware testleri: `ws_motor_test/run_cpp_tests.cmd` (MSVC BuildTools; ~25+ test grubu, hepsi geçiyor).

---

## 5. PC yazılım mimarisi (`Derin-Mavi/app/`)

**Hareketin tek kapısı:** `arayuz_qt.MainWindow._aci_hareket(d_pan, d_tilt, taban_olculen, hiz=None)`.
E-Stop, yasak alan, tilt limiti burada. `hiz` verilirse trajectory mode komutu gider; yasak bölgeye
0.2 sn içinde girecek eksenin hızı 0'lanır. Başında `_acilis_hizala()` çağrılır.

| Dosya | İçerik |
|---|---|
| `tilt_surucu.py` | Kartın PC sürücüsü: STATE3/PAN1 çözümü, mock kart (pan + trajectory taklidi dahil), auto port, kara kutu log, `yorunge()`, `pan_yorunge()`, `pan_git()`, `sifirla()`, `pan_sifirla()`, 50 Hz açı geçmişi (`aci_zamaninda`, `pan_zamaninda`; toplu okunan satırlar 20 ms aralıkla geriye damgalanır), **kol↔kamera açısı dönüşümü** (`KAMERA_PPD_TABLO`, `kamera_acisi`, `kol_acisi`), hız tabloları (`HIZ_TABLO` tilt, `PAN_HIZ_TABLO` 25/60/100 °/s). |
| `kontrol.py` | Arayüzün kart API'si. `pan_ayri`, `yorunge_destekli`, `yorunge()`, `pan_zamaninda/tilt_zamaninda`, **açılış hizalaması** (ilk konum raporunda hedefler ölçülene eşitlenir → `acilis_hizalama`). |
| `hedef_kestirici.py` | `HedefKestirici` (1B Kalman, adaptive q/NIS), `EksenTakip` (asıl kontrolcü, aşağıda), eski `KalmanTakipKontrolu`. |
| `arayuz_qt.py` | `InferenceThread` her karede ham ölçüm yayar (`takip_olcum`) + kamera hareketi telafisi; `MainWindow._takip_olcum_geldi` otonom takibi yürütür (trajectory mode varsa `yorunge_komut`, yoksa `komut`). Kırmızı kanıtı olmayan karede "görülmedi" bildirir. |
| `algi.py` | Kamera + YOLO + ByteTrack + kilit/hayalet + renk + kilit penceresi + uzak edinim + zor örnek + pozlama. |
| `nisan.py` | Eski PD nişancı (artık yalnız konum bildirmeyen kart için yedek) + `nisan_noktasi`. |

### `EksenTakip` (her eksen için ayrı; pan `isaret=+1`, tilt `isaret=-1`)
- Hedefin **dünya açısı**: `z = eksen_açısı(kare_anı) − boşluk_ofseti + işaret·hata_px/ppd`.
  Kare anı = kameradan okuma anı − `kamera_gecikme`.
- **Tilt kamera açısında izlenir:** kol açısı kamera açısına çevrilir (mekanizma doğrusal değil),
  ppd pan ile aynı (18.7); komut kola geri çevrilir, hız yerel eğimle bölünür.
- **Dişli boşluğu**: model + çalışırken öğrenme (`bosluk_kest`), yön histerezisi.
- **trajectory mode (`yorunge_komut`)**: (konum, hız) üretir. Öngörü YOK (kart ilerletiyor).
  Hedef duruyorsa (hız <1°/s, 0.4 sn) position mode mantığına geçer (**"durağan kip"**:
  histerezis + yerleşme düzeltmesi); hedef görünürde ölü bölgedeyse konum sabitlenir.
  `_yorunge_sinirla`: 0.25 sn ileriye bakıp yazılım sınırından 1.5° pay bırakır.
- **Adaptive Kalman**: q, normalize yeniliğe göre **60..800** arasında kayar
  (`nis_yukselis 0.5, nis_inis 0.1, eşik 1.5–4`). Daha agresif ayarlar denendi, kaba geri
  bildirimde salınım yaptığı için alınmadı (bkz. §9).

### `algi.py` tespit/takip zinciri
1. ByteTrack (`model.track`, persist). Normal çözünürlük **640**; kilit yokken 1280 yalnız
   **15 karede bir** (sürekli 1280 yakın dronu bozuyordu).
2. Kilit: ilk kilit sınıf onayı (≥%70, 3 kare, histerezis) ister. **Aşama 2/3'te "anlık kırmızı
   kanıtı"** (`anlik_kirmizi_kaniti`) şart: ilk kilit, **kilit devri** ve **kilit penceresi** için.
   Kilitli kutu **15 kare** kırmızısız kalırsa kilit bırakılır (kilidin insana kaymasına karşı).
3. **Kamera hareketi telafisi**: eksen açılarından hesaplanan görüntü kayması ByteTrack izlerine ve
   kilit hafızasına uygulanır (`kamera_kaymasi_bildir`).
4. **Kilit penceresi (ROI)**: kilitli hedef ana taramada yoksa son yerinin çevresi (en az 213 px,
   kutunun 6 katı) tam çözünürlükte kırpılıp 640'ta taranır → ~3× büyütme. **Ayrı YOLO nesnesiyle**
   (aynı nesneyle `predict` ByteTrack'i bozar). Pencereyle izlenirken kayıp sayacı sıfırlanır.
5. **Uzak hedef edinimi** (kilit yokken, GPU varsa): her 4 karede 12 parça 2× tarama; aday 3
   karede pencereyle doğrulanınca negatif (sentetik) ID ile kilit. Güçlü aday varken atlanır.
   **GPU yoksa kendiliğinden kapanır.**
6. Hayalet kutu: yalnız gösterim, kontrol girdisi değil.
7. **Zor örnek toplama**: `app/veri_toplama/<oturum>/{images,labels}` — `roi`, `dusuk` (etiketli,
   etiket SAHTE), `kayip` (etiketsiz). 1/sn, oturumda 300. Testler geçici klasöre yazar.
8. **Kamera pozlaması**: 7.8 ms (−7) + kazançla parlaklık 100–150'ye ayarlanır; olmazsa otomatik.

---

## 6. Önemli ayarlar (`algi.VARSAYILAN_AYAR`; `app/ayarlar.json` kullanıcının kayıtlı değerleri)

| Anahtar | Değer | Not |
|---|---|---|
| `cozunurluk` | 640 | model 640'ta eğitildi |
| `arama_cozunurluk` | 1280 | yalnız 15 karede bir |
| `kamera_fps` / `kamera_pozlama` | 60 / −7 | pozlama 0 = otomatik |
| `kamera_gecikme` | **0.04** | yük altında ölçüldü (bkz. §7) |
| `takip_ppd_pan` | 18.7 | px / gerçek kamera derecesi (1280 px) |
| `takip_bosluk` | 0.8 | başlangıç; öğrenilir |
| `pan_takip_siniri` | 170 | otonom pan ±; kablo sarmasın |
| `tilt_takip_ust` | 48 | üstü ölçülemedi, kamera çok az dönüyor |
| `roi_tespit/roi_esik` | 1 / 0.30 | kilit penceresi |
| `uzak_tarama/uzak_tarama_periyot` | 1 / 4 | GPU yoksa kapalı |
| `zor_ornek` | 1 | veri toplama |
| `kp/kd` | 0.6/0.06 | yalnız eski PD yolu |
| `nisan_govde` | 1 | balon yok → kutu merkezine nişan |
| `sahi` | 0 | açıkken ByteTrack ID'leri yok olur |

---

## 7. Ölçümler (hepsi sahada/donanımda)

| Ölçü | Değer |
|---|---|
| Kamera gecikmesi (kart açı satırı → okunan kare) | yüksüz 30 ms; **model çalışırken ayrı okuyucuyla 40 ms, doğrudan `cap.read` 60 ms** |
| Pan px/° | 18.7 (19.6/18.6/17.8) |
| Tilt px/° (kol derecesi) | 5°:10.5 · 12°:11.3 · 20°:12.7 · 28°:13.5 · 36°:9.1 · 44°:5.3 → **kol 0–48° = kamera 0–26.5°** (60° ≈ 30°). Hedef kameranın ~27–30° üstündeyse kol tavana dayanır. |
| Boşluk | tilt 0.1–0.9°, pan 0.2–0.7° |
| Pan hızı | Normal 60°/s tepe: 60° dönüş 1.2 sn |
| Trajectory mode donanım izleme | rampa hatası pan 0.52→0.09°, tilt 0.30→0.06° (position mode'a göre); sinüs ±10°/2 sn: gecikme **15–20 ms**, hata 6–9 px |
| Uzak tespit (gerçek dron küçültülerek, 60 örnek/boy) | Tam kare 640: **35 px ve altı %0**. 3× pencere: 18 px %77, 12 px %67. 12 parça tarama: 25 px %75. Uçtan uca: 20 px dron eski sistem 0/3, yeni 3/3 kilit. |
| Kırmızı kanıtı | küçük (12 px) dronda %100 |
| Pozlama | otomatik ~15.6 ms; −7 (7.8 ms) + kazanç ≈ aynı parlaklık, bulanıklık yarıya |

**Canlı takip sonuçları (elde tutulan dron, 2–3 m):**
- İlk PD (eski): görülme %87, dikey 19 px, yatay 43 px, 34 ID değişimi.
- Trajectory mode + düzeltmeler, **sabit tutulan dron**: dikey 6.5 px (sarsıntı ~0), yatay 11.5 px.
- **Yavaş hareket**: dikey 12 px, yatay 26 px. **Normal hız**: dikey 16 px, yatay 31 px.
- ID değişimi (insana kilit kayması düzeltildikten sonra): 82 → 1–5.

---

## 8. Kronoloji: önemli kararlar ve yanlışlar (tekrarlama!)

1. **"Ölü nokta / ters bölge" iddiası YANLIŞTI** (21.09): ESP'nin sıfırı kaymıştı. Eğri telafisi geri alındı.
2. **Pan yön karışıklığı**: kullanıcı DIR kablosunu yanlış takmıştı; ona göre yön çevrildi,
   sonra takip testi yönün ters olduğunu gösterdi → `PAN_DIR_POS_HIGH=true`'ya geri dönüldü.
3. Kamera tavana bakarken pan görüntüyü **kaydırmaz, döndürür**; faz korelasyonu pan'ı göremez.
4. PD + "meşgul kapısı" dur-kalk ve titreme üretiyordu → `EksenTakip` (konum) → sonra
   **trajectory mode** (kullanıcının isteği: "hedefe gidip duran değil, aynı hızda takip eden").
   Pan'da ciddi yumuşama gözlendi (kullanıcı onayı).
5. Tilt'te sabit ppd, kolun kendi hareketini hedef hareketi sandırdı (kol 35→53 fırladı) →
   kamera açısı tablosu.
6. Başka bir oturum (22.09 akşam) şunları ekledi, **hepsi tutuldu**: 640 arama (1280 seyrek),
   Aşama 2/3 kırmızı kapısı, güçlü adayda uzak tarama atlama, `_yorunge_sinirla`,
   `canli_pasif_gozlem.py`, `canli_eksen_dogrulama.py`, `kamera_gecikme_olc.py`
   (son aracın küçük kusuru: açı zamanlarını ~10 ms geç damgalıyor).
7. Sahada **model insan gövdesini maket sanıyor** ("F16 0.68" bacakta) → kilit devrine kırmızı şartı.
8. Arayüz açılışta pan'ı 0 sanıyordu (pan 28°'de kalmıştı) → açılış hizalaması.

---

## 9. Pan'ın hareketli hedefte geride kalması — analiz (AÇIK SORUN)

- Pan, hareket hâlinde karelerin ~%80'inde hedefin **gerisinde**; en büyük hata **yön
  dönüşlerinde** (hedef dönünce pan 0.2 sn eski yönde gidiyor, hata 120+ px).
- Zincir ayrıştırıldı: Kalman tahmin gecikmesi 4–8 px; komut mantığı tahmine uyuyor; motor
  sinüs izlemesi 15–20 ms. Kalan: **~60–80 ms toplam gecikme** (kamera 40 ms + model + seri) ve
  elin 30–60 °/s keskin dönüşleri. Bu adaptive Kalman'dan ÖNCE de vardı.
- `araclar/gercek_hareket.py` kayıtlı gerçek el hareketini benzetime girdi yapar (saha hatasını
  yaklaşık üretir: benzetim ~20 px, saha 26–31 px). Sonuçlar:
  - Kalman üst sınırı 1200–5000 + hızlı manevra algılama: medyan 22.4→19.4 px, %95 101→82 px,
    **ama sahte kartlı kapı testinde ±1° salınım** → alınmadı (60..800 kaldı).
  - Firmware K=8→15/25: hata ~%20–25 azalır, sarsıntı %50–75 artar (kullanıcı titreşimden
    şikâyetçi olduğu için alınmadı; kullanıcıya seçenek olarak sunuldu, cevap bekleniyor).
- Önemli bağlam: yarışma hedefleri **rayda, düzgün** gider (benzetimde rayda sabit hız 0.7 px).
  Elle yapılan test gerçekten daha zor.

---

## 10. Araçlar ve test komutları

**Modül testleri** (`Derin-Mavi/app` içinde, hepsi geçiyor):
```
python algi.py; python hedef_kestirici.py; python tilt_surucu.py; python kontrol.py; python nisan.py; python protokol.py; python kapi_testleri.py; python tilt_takip_testi.py
```
Arayüz ekransız duman testi: `QT_QPA_PLATFORM=offscreen DERINMAVI_ESP=off DERINMAVI_TILT=mock` ile
MainWindow kurulabiliyor (uygulama kapanırken süreç 127 koduyla çıkıyor — önceden de vardı).

**Canlı araçlar:**
| Araç | Kullanım |
|---|---|
| `tilt_canli_takip.py` | Arayüzsüz canlı takip. `--mod yorunge` (trajectory, varsayılan) / `surekli` (position) / `pd`. `--kilit_bekle 120` (süre hedef kilitlenince başlar), `--pan_sinir 60`, `--bas 5`, `--sure 30`. Aşama 2 mantığıyla çalışır. Özet: hata, görülme, ID değişimi, "HIZ DALGALANMASI" (sarsıntı). CSV `app/loglar/`. |
| `canli_pasif_gozlem.py --sure 8 --kare x.jpg` | Motor/ESP'ye dokunmadan kamera+tespit ölçümü |
| `canli_eksen_dogrulama.py --adim 1 --kamera` | İki ekseni ±1–3° oynatıp bağımsızlık kontrolü |
| `kamera_gecikme_olc.py` | Tilt adımıyla gecikme ölçümü |
| `tilt_tani.py auto --git 0` / `--sifirla` | Teşhis, kolu açıya götürme |

**`YAPAY_ZEKA_DEVIR/araclar/` (geçici betikler, `app/` klasöründen çalıştırılmalı; bazıları
`$TEMP/yor_benzet.py`'ye göre yol arıyor, gerekirse yolu düzelt):**
- `bolumlu_test.py` — **3 bölümlü canlı takip testi, sesli bip ile** (1: 20 sn sabit tut, 2: 30 sn
  yavaş, 3: 30 sn normal hız). Kullanıcı bu formatı rahat takip ediyor.
- `analiz.py`, `analiz2.py` — test CSV analizi (tavan süresi, yön değişimi kamera derecesiyle).
- `yor_benzet.py`, `gercek_hareket.py`, `denge.py` — benzetimler (motor + boşluk + gecikme, gerçek el hareketi).
- `gecikme_zinciri.py`, `komut_replay.py` — gecikmenin zincirde nereden geldiğini ayrıştırma.
- `sinus_pan.py` — donanımda pan sinüs izleme testi. `yuk_gecikme.py` — yük altında kamera gecikmesi.
- `gecikme_olc.py` — gecikme/ppd/boşluk ölçümü (ızgara uydurma).
- `uzak_bench.py`, `uzak_bench3.py`, `uzak_ucdan.py`, `kirmizi_uzak.py` — uzak tespit ölçümleri.

**Test protokolü (kullanıcıya böyle anlat):** dron elde, kameradan **2–3 m**, **göğüs hizası /
kamera yüksekliğinde** (kamera ~27° yukarıdan fazla bakamıyor), kırmızı tişörtlü biri kadrajda
olmasın. Bölüm başlangıç/bitişi bip ile bildirilir.

---

## 11. Diğer oturumun mimari önerisi (`DERIN_MAVI_kontrol_mimarisi_devir.md`) — değerlendirme

Çoğu yapıldı (zaman damgası, gecikme ölçümü, konum geri bildirimi, mutlak açı Kalman + ileri
besleme, trajectory mode). **Önerilen ve kullanıcıyla konuşulan açık işler:**
1. **Donanımsal lazer kilidi** (acil durdur ve ALM, lazeri ESP'den bağımsız kessin) — en önemli.
2. **Çıkış eksenine mutlak manyetik enkoder** (AS5048A/AS5600): sıfır kayması, boşluk ve
   krank-biyel doğrusal olmama sorunlarını kökten çözer. Motor enkoderini ESP'ye bağlamak
   anlamsız (sürücü zaten kapalı çevrim). Kullanıcıya soruldu, cevap bekleniyor.
3. ALM çıkışlarını ESP'ye bağlamak (firmware tarafı yazılmadı).
4. 74HCT245 seviye dönüştürücü (3.3 V opto akımı sınırda; şimdiye kadar kaçan darbe görülmedi).
5. Tilt'i eğim ölçerle yeniden kalibre etmek (yüksek açılarda kalibrasyon kamerayla uyuşmuyor).
**Reddedilenler:** 12800 pulse/rev (faydası yok, kalibrasyonu bozar), 36–48 V (hız darboğazı yok),
saf hız komutu (iletişim koparsa motor koşar).

---

## 12. Sıradaki işler (öncelik sırası)

1. **Kullanıcının kararı bekleniyor:** pan gecikmesi için firmware K'yi (8 → 15) artırıp
   sarsıntıyı sahada gözle değerlendirmek mi? Değiştirmek için `yorunge_core.h` `KAZANC`,
   ardından derle + C++ testleri + yükle (§4 uyarıları).
2. **Gerçeğe yakın hareketli hedef testi**: dronu ipe/çubuğa asıp sabit hızla taşıyarak
   (yarışma raylı hedefe benzer). El testi yön dönüşleri yüzünden fazla zor.
3. **Uzak mesafe canlı testi** (henüz yapılamadı): 3 m'den başlayıp 2'şer m geri, 15 m'ye kadar.
   Uzak edinim + 3× pencere sahada doğrulanmadı.
4. **Model**: toplanan zor örnekler (`app/veri_toplama/`) gözden geçirilip etiketlenmeli;
   yeniden eğitimde **balon sınıfı** ve **insan negatif örnekleri** (model insanı maket sanıyor).
5. Kamera gecikmesi aracı (`kamera_gecikme_olc.py`) zaman damgasını sürücünün geçmişinden almalı.
6. Tilt 48° üstü ölçülemedi; mekanik: kamera yükselişi ~30° ile sınırlı (takım bilmeli).
7. Bilinmeyenler: ESP bir kez kilitlenmişti (sebep bulunamadı, `app/loglar/` kara kutu);
   uygulama kapanışında çıkış kodu 127.
8. Commit/push kullanıcıya sorulmadan yapılmayacak.

---

## 13. Bu oturumda kullanıcının söyledikleri (kısa)

- "Pan ekseninde çok ciddi bir yumuşama gördük" (trajectory mode sonrası).
- "Takibi çok iyi seviyeye getirmemiz lazım", "uzak mesafede de çalıştıracağız".
- "Uzak mesafe testini şu an yapamıyoruz."
- Testlerde dronu elde tutuyorlar; bazen kameranın hemen yanında durup dronu alçakta tuttular
  (kadraj dışı) → talimatı net ver.
