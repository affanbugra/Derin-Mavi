# DERİN MAVİ — Proje Beyni

> TEKNOFEST Çelikkubbe Hava Savunma Sistemleri. Hedef: **birincilik**.
> Bu dosya her oturumda otomatik yüklenir ve **kısa tutulur** — uzun dosyada kritik
> satırlar gözden kaçar. Ayrıntılı tarihçe git geçmişindedir (`git log -p CLAUDE.md`).
> Tarihsel/uzun notlar: `SON_DURUM.md`, `FINAL_ENTEGRASYON.md`, `TILT_TAKIP.md`,
> `ENTEGRASYON.md`. Kurulum: `README.md`.

---

## 0. Claude, nasıl çalışmalısın

1. **Körü körüne uyma.** Daha iyisini görüyorsan söyle ve gerekçelendir. "Yap" denildi
   diye güvenliği bozma.
2. **Şartname tek referanstır.** Emin değilsen `sartname/sartname_metin.txt`'i **tara**;
   hafızadan konuşma. Şartnamede yazan **[KESİN]**, çıkarım **[VARSAYIM]** diye ayrılır.
3. **Dürüst ol.** Test kırmızıysa söyle, "çalışıyor" deme. Donanımda denenmediyse
   "denenmedi" yaz. Görmediğin bir ekranı "düzelttim" diye rapor etme.
4. **Türkçe konuş.** Ekip Türkçe çalışıyor; çoğu üye sohbetten geliştiriyor.
5. **Her kararı puana bağla.** Baraj puanını geçmek önce gelir.
6. **Donanım-bağımsız yaz.** Makineye özel mutlak yol yok; port/kamera/model çalışma
   anında bulunur ya da env ile geçilir. Yarışmaya başka laptopla gidilecek.
7. **Değişiklik yaptıysan bu dosyayı güncelle** — ama **şişirme**: yeni kural eklerken
   eskiyen satırı sil. Hedef: bu dosya ~300 satırın altında kalsın.

**Ekip kuralları:** `main`'e doğrudan commit/push YOK → kendi dalında çalış, PR aç.
Model dosyası dışında ağırlık/veri/`__pycache__`/gizli belge commit edilmez.
Yeni kütüphane kullandıysan `requirements.txt`'e ekle. Push öncesi testleri koş (§6).

**DAL İSİMLENDİRME (zorunlu, 23.09):** `<taban>-<kişi>-<iş>` — hepsi küçük harf,
Türkçe karaktersiz, kelimeler tire ile.
`final_v4-affan-repo-temizligi` · `final_v4-mehmet-tilt-kalibrasyon`
Neden: dal listesine bakan biri **kimin** neyi yaptığını açar açmaz görsün; iki kişi
aynı anda aynı isme itmesin. `final_v4` gibi **taban dallar ortak birleşme yeridir** —
oraya doğrudan geliştirme yapılmaz, kendi dalından PR ile gelinir.

---

## 1. ⛔ DOKUNULMAZLAR — bunları bozan değişiklik kabul edilmez

Bunların her biri **gerçekten yaşanmış bir hatanın** karşılığıdır. Değiştirmek gerekiyorsa
önce ekibe sor, sonra ilgili kapı testini güncelle.

| # | Kural | Neden |
|---|---|---|
| 1 | **Ateşin tek kapısı `_ates_bas`, kesmenin tek kapısı `_ates_kes`.** Yeni bir ateş yolu (buton/kısayol/gamepad/otonom) buradan geçmek zorunda. | İkinci bir ateş yolu bir kez E-Stop denetimini atladı. |
| 2 | **Hareketin tek kapısı `_aci_hareket`.** E-Stop, yasak alan ve mekanik sınırlar orada uygulanır. | E-Stop'ta D-pad komut göndermeye devam ediyordu (şartname Yetenek 3 ihlali). |
| 3 | **Karta giden açı MUTLAK, birim DERECE.** Firmware `moveTo` kullanır; step'e çevirim karttadır. | Delta protokolde ekrandaki açı kartın hedefinden kopuyordu. |
| 4 | **Lazer ölü adam anahtarı**: 250 ms'de bir `L1` tazelemesi; kart 1 sn tazeleme almazsa lazeri KENDİ keser (`protokol.ATES_TAZELE_MS` / `ATES_ZAMAN_ASIMI_MS`, firmware ile aynı). Tazeleme 1 sn kesildiyse PC lazeri **kendiliğinden yeniden yakmaz**. Kesme (`L0`/`STOP`) her karta ve her porttan gider. | "Kes" komutunun gideceğine güvenilemez: kablo koptuğunda o komut zaten gidemez. Donan arayüz geri gelince eski tazeleme lazeri yeniden yakıyordu (24.09 testte yakalandı). |
| 5 | **Mekanik sınırlar iki tarafta da uygulanır** (Python + firmware). Tek tarafa güvenilmez. | Seri monitörden elle `T500` yazan biri mekaniği kırabilir. |
| 6 | **Ateş tek kapıdan, kesmek kolay; ACİL DURDUR kısayolla yalnız KURULUR.** Ateş: `Space`/`B`, kol `L2`+`R2` (tek dokunuş, 23.09 takım kararı) — hepsi `_ates_bas`. `Esc` ateşi keser. ACİL DURDUR: `Backspace`, kol `Options` veya `Daire/B`; kısayol asla DEVAM ettirmez, devam yalnız arayüz butonu. | Kol eskiden Options'ın ikinci basışında acil durdurmayı kaldırıyordu. |
| 7 | **Otonom ateş için o karede kırmızı kanıtı şart** (`anlik_kirmizi_kaniti`). Hayalet hedef veya eski sınıf belleği yetmez; kanıt kaybolursa ateş kesilir. | Aşama-3'te dost vurmak −10 puan. |
| 8 | **Sahte cihaz (mock) asla "hazır/yeşil" görünmez.** Alt çubukta sarı + "kart takılı değil". | Operatör kablosuz sistemi hazır sanıyordu. |
| 9 | **Merkeze alma kademelidir** (motor tavan hızıyla), anlık sıfırlama yok; yön komutu veya E-Stop dönüşü keser. | Ekran sıfıra zıplarken gimbal yolda kalıyor, açı referansı kopuyordu. |
| 10 | **Ayar varsayılanları tek kaynaktan** (`algi.VARSAYILAN_AYAR`). Aynı sabiti ikinci bir yere yazma. | Üç yerde tutulan kp/kd değerleri birbirinden sapmıştı. |

---

## 2. Şartname özeti — **V1.5** (teknofest.org'daki son sürüm) [KESİN]

> `sartname/Şartname.pdf` = yarışma sayfasındaki `2026_Şartname_TR_v1.5` (sitede
> 27.08.2026; 24.09'da indirildi). Repodaki önceki PDF §5.4'ü (hedef/balon) İÇERMİYORDU.
> Yeni sürüm çıkınca aynı adla değiştirin ve `sartname_metin.txt`'i yeniden üretin.

**Takvim:** ÖTR 17.03.2026 · KTR 02.06.2026 · **Sistem Kabiliyeti Videosu 17.08.2026 17:00**
· Finalistler 31.08.2026 · **Finaller 30 Eylül – 4 Ekim 2026**.

**Puanlar (toplam 500):** Rapor+Sunum 100 (ÖTR 10 / KTR 50 / Final sunum 40) · Ebat 20
· Aşama-1 100 · Aşama-2 120 · Aşama-3 160.
**Ebat:** her boyut < 100 cm **zorunlu**; en uzun boyut ≤ 60 cm ise **20 puan**.
**Ödül şartı:** Aşama-3'ten **en az 10 puan** (yoksa ilk üçte bile olsan ödül yok).

| Aşama | Mod | Kurgu | Puan | Baraj / başarısızlık |
|---|---|---|---|---|
| 1 | **Manuel** | 4 hedef, 5/10/15 m, durağan, rastgele dizilmiş. İmha sırası **zarfla** verilir. | Yakın 5 / Orta 10 / Uzak 20 · max 80 + bonus `20×(kalan sn/300)` · yanlış sıra −5 · 5 dk | **≥20 puan** *(V1.4'te 30'dan düştü)* |
| 2 | **Otonom** | 4 tur, 3 koldan aynı anda 3 hedef (Füze + Mini/Micro İHA), A→B. Hedefler **parkurdan çıkmadan** imha edilmeli. Tip sınıflandırması beklenmez. | Tur başına 1/2/3 hedef = 5/15/30 · max 120 · tur başına −5 | **≥20 puan** |
| 3 | **Otonom** | 8 tur; her turda 1 düşman + 2 dost; düşmanın kolu **rastgele**. Düşmanı tipine uygun menzilde imha. | F16 30 · Heli/Füze 20 · İHA 10 · max 160 · dost vurma / düşmanı vuramama −10 (tur başına en çok −10) | **≥10 puan**; **4 ardışık tur** düşman vuramayan takım 0 alır |

**İmha menzilleri (A3):** F16 **10–15 m** · Heli/Füze **5–15 m** · İHA **0–15 m**.
Daha yakından yapılan imha puana sayılmaz.
→ **Strateji: 10–15 m ortak bandı.** Üç tip için de geçerli; mesafe işi "10–15 m'de mi?"
sorusuna iner, hassas derinlik gerekmez.

**Hedefler (§5.4, V1.4'te eklendi):** Balistik Füze · Helikopter · Savaş Uçağı (F16) ·
Mini/Micro İHA.
- Aşama-1 ve 2'de **yalnız kırmızı** maket vardır (dost yok).
- Aşama-3'te **dost = mavi, düşman = kırmızı** (ayrım renkten, tipten değil).
- **Tüm maketlerin ALTINDA kırmızı balon** vardır. **İmha = balonun patlaması**;
  maket yalnız teşhis içindir. ⚠ Bunun yarattığı risk → §7.1.
- Şekil 3 (gerçek foto): maket direğin tepesinde, balon **aynı direkte hemen altında**,
  neredeyse bitişik; balon çapı ≈ maketin eni. Balon boyu şartnamede **yazmıyor**.

**Video (7 yetenek):** 1 arayüz/joystick/klavye anlatımı · 2 durağan 15 m balon ·
3 hareket ederken E-Stop · 4 ateş ederken E-Stop · 5 hareketli hedef takibi ·
6 **5/10/15 m'de tespit + sınıflandırmanın arayüzde gösterimi** ·
7 **(OPSİYONEL)** 10 m'de 1 kırmızı + 2 mavi; otonom düşman imhası, 10 sn bekle,
E-Stop, 10 sn bekle, kapat — dostlara ateş edilmediği görülür.
720p+, 2–5 dk. *(Yetenek 6 artık opsiyonel DEĞİL.)*

**Güvenlik [KESİN]:** harekete-yasak + atışa-yasak alan tanımı zorunlu; sistem yalnız
hedef tarafına bakabilir; **dışarı çıkan kabloyla, güvenli konumda donanımsal acil
durdurma butonu zorunlu** (basmalı/çevirmeli/manyetik); açıkta kablo olmayacak.
Testlere **yükseliş 0°, yan 0°** ile başlanır. Üç aşama için toplam bakım 10 dk (her talep ≥30 sn).

---

## 3. Sistem mimarisi

```
Kamera → algi.py (YOLO+takip) → nisan.py / hedef_kestirici.py (PD + kestirim)
       → arayuz_qt.py (kapılar, operatör)
       → kontrol.py ─┬→ tilt_surucu.py → ESP32-S3 (ws_motor_test)  [tilt + pan + lazer + acil buton]
                     └→ protokol.py    → eski ESP32 kartı          [yalnız pan]
```

| Katman | Dosya | Rolü |
|---|---|---|
| Arayüz | `arayuz_qt.py` (4.3k satır) | Manuel/Otonom, aşama, açı karoları, yasak alanlar, kol göstergesi, E-Stop |
| Görünüm | `tasarim.py` | Renk/ölçü/QSS **tek kaynak** (Apple macOS dili) |
| Algı | `algi.py`, `renk_analizi.py` | Araç tespiti (YOLO11 + ByteTrack), kesin tanıma, dost/düşman rengi |
| Balon | `balon_takip.py` | **A2/A3 kilit + nişan balonda** (`models/bestb2.pt`); araç = balonun kimlik kartı (taraf/tip oyu); imha = ateş edilen balonun kaybolması |
| Nişan | `nisan.py`, `hedef_kestirici.py` | Piksel hatası → açı (PD), yörünge kestirimi |
| Güvenlik alanı | `bolge.py` | İzinli pencere modeli (hareket/atış) — **tek sınır kaynağı** |
| Kontrol | `kontrol.py`, `protokol.py`, `tilt_surucu.py`, `mock_esp32.py` | Karta giden **tek kapı** + donanımsız çalışma |
| Girdi | `gamepad.py`, `kol_ikon.py` | Kol okuma + ekrandaki kol göstergesi |
| Kamera | `kamera.py` | **Yalnız harici USB kamera** (dahili/telefon/sanal elenir) |
| Testler | `kapi_testleri.py` | Güvenlik kapıları (§6) |

**Ortam değişkenleri:** `DERINMAVI_ESP` (`mock` \| port \| `off`) · `DERINMAVI_TILT`
(`off` \| port) · `DERINMAVI_CAM` (dosya/RTSP) · `DERINMAVI_MODEL`.

**Protokol (eski kart):** `P<derece>` `T<derece>` `S<der/sn>` `A<der/sn²>` `G<%>`
`L1`/`L0` `STOP`/`START`; kart insan-okur metin yazar, `protokol.satir_*` ayrıştırır
(`SISTEM AKTIF`, `TILT_MAX:`, `Konum P../T..`, `DURDURUL`).
**Tilt kartı (ESP32-S3):** `E/D/X/G/R/H…`; 50 Hz `STATE3`/`PAN1` yayını, **120 ms'de bir
canlılık darbesi** (`CANLILIK_MS`), 350 ms sessizlikte kart kendini kilitler.

---

## 4. Sayılar — nereden geliyor, kim değiştirir

Bir sayıyı değiştireceksen **iki tarafı birden** (Python + firmware) güncelle.

| Büyüklük | Değer | Kaynak |
|---|---|---|
| Yatay sınır | **kodda sınır YOK** — yalnız hareket penceresi; açılış değeri **±90** (arayüzden değişir). Pencere kapalıysa hareket serbesttir. | `bolge.PAN_VARSAYILAN` |
| Dikey sınır | **kodda sınır YOK** — pencere (açılış ±30 = kalibre kolun tamamı); geriye yalnız mekaniğin kendisi kalır | `bolge.TILT_CALISMA_MIN/MAX` |
| Otonom takip sınırı | **ayrı sınır YOK** — aynı hareket penceresini kullanır (gizli tavan/pay kaldırıldı) | `arayuz_qt._nisan_geldi` |
| Operatör 0° = kol | 30° | `tilt_surucu.KULLANICI_SIFIR` |
| Sürücü çözünürlüğü | 6400 step/tur | `protokol.STEP_TUR` |
| Pan redüksiyon | 83/15 ≈ 5.53 (98.37 step/°) | `protokol.PAN_DISLI` |
| Hız kademeleri | `tilt_surucu.HIZ_TABLO` / `PAN_HIZ_TABLO` | ölçümle ayarlanır |
| Lazer gücü varsayılan | **%40** | `protokol.LAZER_GUC_VARSAYILAN` (firmware ile aynı) |
| Tek kart pinleri (S3) | Lazer **GPIO 18** (PWM 1 kHz, 8 bit) · Acil buton **GPIO 15** (NO, GND'ye çeker, dahili pull-up) · tilt 4/5 · pan 10/11/16 | `ws_motor_test/esp32_ws_test.ino` |
| Ateş tazeleme / zaman aşımı | 250 ms / 1 sn | `protokol.ATES_*` |
| Tespit/PD ayarları | `app/ayarlar.json` | **repoda ortak**; kendi denemenden sonra `git checkout app/ayarlar.json` |

---

## 5. Yasak alanlar ve operatör kuralları

**[23.09] Kodda açı sınırı YOKTUR — tek sınır arayüzdeki pencerelerdir.** Eskiden `bolge` içinde ±60 yatay / ±25 dikey
"çalışma sınırı" vardı; ekranda görünmediği için sahada "neden bu açıya gitmiyor"un
cevabı kodun içinde kalıyordu. Artık sınırı yalnız operatör koyar; geriye kalan tek
sınır mekaniğin kendisidir (kol aralığı + firmware kırpması).

- Operatör **yasak** aralığı değil **izinli pencereyi** girer; dışı yasaktır.
  Hareket penceresi: dışına çıkılamaz, sınırda **kırpılır**. Atış penceresi: yalnız
  içinde ateş; dışına çıkılırsa ateş **kesilir**. Atış penceresi hareket penceresinin
  dışına taşamaz (`atis_uyumla`).
- Yapısal sınırlar pencereden bağımsız her zaman uygulanır; pencere onları yalnız
  **daraltır**. Açılışta pencereler bu sınırlarla **etkin** gelir.
- Hazır ayar: atış yatay ±30 / dikey ±15 (ateş alanı hareket alanından dar başlar).
- Açı karolarında açık pencereler saydam renkli dilim olarak görünür: **sarı** =
  harekete yasak, **kırmızı** = atışa yasak, **soluk yeşil** = atış izni.
- Klavye: `W/A/S/D` veya oklar = yön · `R` = merkez · `Space`/`B` = ateş · `Esc` = ateşi kes ·
  **`Backspace` = ACİL DURDUR** (yalnız kurar). Kol: D-pad + sol çubuk (yatay) / sağ çubuk (dikey) ·
  **Options veya Daire/B = ACİL DURDUR** (yalnız kurar) · L2+R2 = ateş · L1/R1 = merkez.
  Acil durdurmadan çıkış (DEVAM ET) yalnız arayüz butonuyla; donanım butonu basılıyken olmaz.

---

## 6. Doğrulama — push öncesi koş

```bash
python app/kapi_testleri.py        # birleşik arayüz (gerçek pencere açar)
python app/kapi_testleri_arayuz.py # GÜVENLİK KAPILARI, pencere AÇMADAN (31 test)
python app/bolge.py            # yasak alan matematiği
python app/protokol.py         # komut üretimi + sabit tutarlılığı
python app/kontrol.py          # mock cihazla uçtan uca
python app/tasarim.py          # arayüzde stilsiz bileşen var mı
python app/algi.py  app/nisan.py  app/kamera.py  app/gamepad.py  app/kol_ikon.py
python app/balon_takip.py      # A2/A3 balon takibi (kart, gövde rengi, menzil, dost engeli)
```

**Kural:** güvenlik davranışını değiştiren her düzeltmenin bir testi olmalı ve testin
**eski kodda kırmızıya düştüğü** görülmeli. Testi silmek/atlamak değil, güncellemek gerekir.
Testler pencere açmadan koşabilmelidir (kamera/motor gerektirmez).

---

## 7. Açık işler ve riskler

### 7.1 ⚠ Kırmızı balon / dost ayrımı — **kısmen giderildi, ölçüm bekliyor**
Şartname artık **tüm maketlerin altında kırmızı balon** olacağını söylüyor (§5.4).
**Yapıldı (23.09):** renk artık kutunun **üst %70'inden** okunuyor
(`renk_analizi.GOVDE_ORANI`); balon her zaman gövdenin altındadır. Sentetik testte dost
maket + kırmızı balon artık "Dost" çıkıyor, eski davranışta "Düşman" çıkıyordu.
**Kalan iş:** gerçek mavi maket + kırmızı balon fotoğrafında oranı ölçün; balon kutunun
%30'undan fazlasını kaplıyorsa `GOVDE_ORANI` düşürülmeli.
**Balon yolunda (24.09):** taraf, balonun hemen üstündeki gövde renginden de okunur
(`balon_takip._govde_rengi`, mavi öncelikli). Koridor videosunda maketler #00A3E0'a
boyanınca 1904 karede kilit 0 — ama **gerçek mavi maketle denenmedi.**

### 7.2 Diğerleri
| Konu | Durum |
|---|---|
| ~~E-Stop'ta tilt park mı~~ | **Kapandı (23.09):** iki eksen de olduğu yerde donar. Yeni tilt kartı zaten donduruyordu; eski yoldaki park kaldırıldı (kartla laptop farklı şey söylüyordu) |
| Lazer | **Tek kart (24.09):** S3 GPIO 18, firmware yüklendi ve kartla doğrulandı (LZR1 yayını, STOP/START, güç) — **lazer takılı değilken; yakılarak denenmedi.** Doğrulanmadı: PWM frekansı sürücüyle uyumlu mu, 3.3 V/5 V mantık seviyesi, GPIO 18 ↔ GND 10 kΩ pull-down. Acil buton GPIO 15'e henüz bağlanmadı |
| Balon modeli | **Kuruldu (24.09)**, kendi kameramızın koridor videosunda ölçüldü (§8). Menzil içinde (balon ≥16 px) A2/A3 kilidi %96–100. ⚠ **Model, altında drone asılı ~18 m'deki balonu hiç görmüyor** (1080p'de de; 604–1145. kareler): bu videonun kareleri etiketlenip `bestb2` yeniden eğitilmeli. Araç modeli (`best.pt`) el yapımı drone/F16'yı neredeyse hiç okumuyor → A3 kartında **tip çoğunlukla yok**: operatör "Aranan" tipi seçerse tipsiz balon kilitlenmez; balon çapı girilirse tipsiz balona yalnız 10–15 m'de ateş (ortak bant). Hareketli namluda (bulanıklık) ve açık havada denenmedi |
| Aşama-1 zarf sırası | Arayüzde sürükle-sırala var ama **hiçbir yer okumuyor**; ceza mantığı yok |
| Dwell (lazeri hedefte tutma) | Yok |
| Mesafe ölçümü | **Balon çapından** kestirim (24.09): ⚙ "Balon çapı (cm)" sahada cetvelle ölçülüp girilmeli, 10 m'de etiketle doğrulanmalı. Girilmezse (0) A3 menzil kontrolü YOK. Çap yanlışsa A3'te hiç ateş edilmeyebilir |
| Homing | Gerçek limit switch yok; `home()` = "0°'a dön" |
| ~~`tasarim.py` testi kırmızı~~ | **Kapandı (23.09):** `#hedefsatir` stili eklendi |
| Doküman tutarsızlığı | `FINAL_ENTEGRASYON.md` hâlâ "pan ±90 yapısal" diyor; artık kodda sınır yok (23.09) |

### 7.3 Eski notlardan düzelenler (V1.4 ile değişti)
Aşama-1 barajı 30 → **20** · Aşama-3 "3 ardışık tur" → **4 ardışık tur** ·
Aşama-2'de ayrı "3 tur üst üste = 0" kuralı **yok** · video yetenekleri 6 → **7**
(Yetenek 6 zorunlu) · video tarihi 10.08 → **17.08.2026** · balon rengi artık
**[KESİN] kırmızı**.

---

## 8. Değişiklik günlüğü (yalnız son 3 madde tutulur)

- **24.09.2026 · final_v8-yunus-balon-takip (saha: kapanış kilidi + yumuşak manuel)** —
  Sahada: 30° açılış sorusu gelmiyor, açı kaymış, manuel hareket sert. Kök neden (kart kara
  kutusu `app/loglar/tilt_*.log`): kapanışta `closeEvent` → `estop(True)` tek kart acil
  durdurmasıyla S3'e **`STOP`** yolluyordu; USB'den beslenen kart kilitli kaldı, sonraki her
  açılış ACİL DURDUR'da başladı, E-Stop **henüz sorulmamış** açılış yükselişini iptal etti →
  `R` hiç gitmedi, kart kolu 60°'de sandı (kol en alttaydı). Düzeltme: kapanış kartı
  kilitlemez (`estop(True, kart_kilidi=False)`: lazer `L0`, `X`, `D`); E-Stop yalnız
  ONAYLANMIŞ yükselişi iptal eder, sorulmamış soru DEVAM'dan sonra gelir. **Manuel basılı
  tutma ve kol çubuğu artık yörünge (`Y`/`PY`)**: eskiden 50 ms'de bir konum hedefi gidiyor,
  motor her hedefte frenleyip hızlanıyordu (testere dişi). Bırakınca fren: hız 0, hedef =
  durabileceği nokta (v²/2a), `FREN_S` boyunca tazelenir; çapraz tuşta bırakılan eksen de
  frenlenir. Tek dokunuş ve merkeze alma değişmedi. 4 yeni kapı testi, 10 mutasyonun 10'u
  yakalandı; hepsi `_aci_hareket` kapısından geçer. **2. saha turu:** ilk açılış düzgün,
  sonrakiler ~10° kalkıp kaldı / hiç kalkmadı. (a) Kart önceki oturumdan 30°'de kalmışsa
  `R`'nin hemen ardından G30, R ÖNCESİ durumu görüp "zaten orada" diye atılıyordu →
  `sifirla` sonrası R SONRASI ilk `STATE3`'e kadar `hazir=False`, R öncesi tamponlanmış
  STATE3 yok sayılır. (b) `yokla` 100 ms'de dönüyordu → H fiilen 200 ms'de bir, 350 ms
  aşımına ~150 ms pay; açılışta model yüklenirken arayüz takılınca kart kolu yarıda kilitledi
  → `TS.YOKLAMA_MS`=40, kilit açılınca son konum hedefi yeniden gider (`dur()`/yörünge/kart
  reseti siler). 6 mutasyonun 6'sı `tilt_surucu.py` testlerince yakalandı.
- **24.09.2026 · final_v8-yunus-balon-takip (koridor videosu testi)** — Kendi kameramızla
  140 sn koridor videosu (1080p → 1280x720, kırmızı tişörtlü kişi elinde drone/F16 + altında
  balon, 1–20 m; yerde bir balon). Canlı boru hattı (`analiz_et(kilit=False)` +
  `balon_takip.guncelle`) videoda **gerçek zamanlı** oynatıldı (işlem süresi kadar kare
  atlanır); referans: 1920'den 2x karo taraması, izler elle doğrulandı (cam yansıması, cam
  kapı, tişört ayrıldı). Bulunan/düzeltilen: (1) model gri cam kapıyı (%57), tişörtü,
  parlak zemindeki yansımayı "balon" sandı → kutu içi kırmızı oranı ≥0.45 (gerçek balon
  ≥0.83, cam 0.00) + en/boy 0.7–1.5 (gerçek %99.5'i 0.73–1.29). (2) "Üstteki gövde, alttakine
  geç" kuralı kilidi **yerdeki yansımaya** veriyordu → devir iki yönlü ve güvene bağlı.
  (3) **Pencere 213 px balonu kaçırıyordu** — balon modeli büyütmeyi sever (14–28 px balonda
  320 px 4/30, 213 px 24/30, 128 px 28/30) → en küçük pencere 128, kırmızı leke penceresi
  lekenin 2.2 katı (birleşik tişört+balon lekesinde eskisi 320 açıyordu). (4) Araç modeli
  el yapımı maketi 220 karenin 2'sinde okudu → A3 kartı ~4 m'de kuruluyordu; artık balonun
  hemen üstündeki **gövde rengi** oy verir (toplam alan, arka plana taşan yüzey sayılmaz,
  kırmızı oy yalnız sürekliyse, mavi öncelikli). (5) Kısa kayıp: doğrulanmış iz kırmızı
  lekeyle taşınır (model 0.4 sn'den uzun görmezse ateş engelli, 1.5 sn'de biter); genç iz
  0.2 sn'de silinir; kenara değen / güveni <0.5 iz yeni kilit almaz. Sonuç (kilit, önce →
  sonra): 16–20 px A2 %78 → %99, A3 %46 → %100; A3 20–28 px %63 → %98, 28+ px %50 → %96–100;
  kilit kimliği 18 → 13 (kalan geçişler ~18–20 m'de). Maketler dost rengine boyanınca 1904
  karede kilit 0. Kare başı ~30 ms (değişmedi). Video ve ölçüm betikleri repoda YOK
  (videoda yüz var). **2. tur (aynı gün):** 23.09 ekran kayıtları (hareketli namlu, balonsuz)
  ve `test.mp4` negatif test olarak eklendi — ~12 bin karede yanlış balon/kilit 0; buradan
  çıkan hata: yakındaki büyük F16'nın parçası 10 karede 3 kez "balon" çıkıp kilit alıyordu →
  yeni kilit için görülme oranı ≥0.5. Eklenenler: **çift eşik** (yeni iz 0.30, doğrulanmış izi
  sürdürmek 0.15; hayalet karelerin ~%38'inde model balonu 0.15–0.30 ile görüyordu), kilitliyken
  diğer uzak balonlara sırayla pencere (A2 sürü), ateş altında renkle devam yok (patlayan balon
  kaybolsun), A3 balon ortasında mavi = "Dost gövde önünde" engeli, A3'te önce imha bandındaki
  balon (bant dışına kilitliyken bantta düşman görülürse ona geçilir). Sonuç: kilit kimliği
  18 → 6; A3 ateşe hazır 16–20 px %85 → %91, 12–16 px %51 → %75. Ateş kapısına hayalet
  toleransı eklemek 15 m'de ateşi 2 kat artırırdı ama §1 kural 7'ye aykırı — yapılmadı (ekip
  kararı). 30 mutasyonun 30'u yakalandı. Temizlik: hiç çağrılmayan kod silindi
  (`algi` eski kamera yardımcıları, `kontrol.tilt_dur`, `gamepad.merkez_basili`, `protokol.
  TILT_CALISMA_VARSAYILAN`=90 — gerçek sınır `bolge.py`'de ±30) ve eski yapay zekâ devir notu
  `YAPAY_ZEKA_DEVIR/` (arduino-cli yükleme komutu + `EraseFlash=none` uyarısı
  `ws_motor_test/README_TR.md`'ye taşındı).
- **24.09.2026 · final_v8-yunus-balon-takip (tek kart lazer + acil)** — Lazer ve acil durdurma
  ESP32-S3'e taşındı (tek kart): lazer GPIO 18, donanım butonu GPIO 15. Güvenlik firmware'de:
  açılışta pin LOW, 1 sn ölü adam, nabız kaybı/`D` lazeri söndürür, `STOP` kartı kilitler
  (hareket + `L1` reddedilir; PC'nin otomatik `E`si kilidi kaldıramaz; buton basılıyken `START`
  ret). `LZR1` yayını (50 Hz) lazer/acil gerçeğini verir. PC eski kart gerçek değilse lazeri
  S3'e yönlendirir, kesmeyi her karta yollar. Klavye `Backspace`, kol `Options`/`Daire` =
  ACİL DURDUR (yalnız kurar). Testlerde yakalanıp düzeltilen iki hata: donan arayüz geri gelince
  lazer kendiliğinden yeniden yanıyordu; kendi STOP yankımız DEVAM'dan sonra okunup acil
  durdurmayı geri kuruyordu. 18 mutasyonun 18'i testlerce yakalandı. COM3'teki karta yüklendi.
