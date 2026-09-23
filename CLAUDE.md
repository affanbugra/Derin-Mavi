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
| 4 | **Lazer ölü adam anahtarı**: 250 ms'de bir `L1` tazelemesi; kart 1 sn tazeleme almazsa lazeri KENDİ keser (`protokol.ATES_TAZELE_MS` / `ATES_ZAMAN_ASIMI_MS`, firmware ile aynı). | "Kes" komutunun gideceğine güvenilemez: kablo koptuğunda o komut zaten gidemez. |
| 5 | **Mekanik sınırlar iki tarafta da uygulanır** (Python + firmware). Tek tarafa güvenilmez. | Seri monitörden elle `T500` yazan biri mekaniği kırabilir. |
| 6 | **Ateş açmak zor, kesmek kolay.** Klavye `Space`+`B` 2 sn basılı; kol `L2`+`R2` 2 sn. `Esc` her zaman keser. Tek tuşla ateş YOK. | Kaza ile lazer açılması en pahalı hata. |
| 7 | **Otonom ateş için o karede kırmızı kanıtı şart** (`anlik_kirmizi_kaniti`). Hayalet hedef veya eski sınıf belleği yetmez; kanıt kaybolursa ateş kesilir. | Aşama-3'te dost vurmak −10 puan. |
| 8 | **Sahte cihaz (mock) asla "hazır/yeşil" görünmez.** Alt çubukta sarı + "kart takılı değil". | Operatör kablosuz sistemi hazır sanıyordu. |
| 9 | **Merkeze alma kademelidir** (motor tavan hızıyla), anlık sıfırlama yok; yön komutu veya E-Stop dönüşü keser. | Ekran sıfıra zıplarken gimbal yolda kalıyor, açı referansı kopuyordu. |
| 10 | **Ayar varsayılanları tek kaynaktan** (`algi.VARSAYILAN_AYAR`). Aynı sabiti ikinci bir yere yazma. | Üç yerde tutulan kp/kd değerleri birbirinden sapmıştı. |

---

## 2. Şartname özeti — **V1.4 (23.06.2026)** [KESİN]

> ⚠ Elimizdeki PDF 23.09.2026'da güncellendi. Aşağıdakiler **yeni** sürümden;
> eski notlarda kalan farklar §7'de listelidir. Şüphede kalırsan PDF'i tara.

**Takvim:** ÖTR 17.03.2026 · KTR 02.06.2026 · **Sistem Kabiliyeti Videosu 17.08.2026 17:00**
· Finalistler 31.08.2026.

**Puanlar (toplam 500):** Rapor+Sunum 100 (ÖTR 10 / KTR 50 / Final sunum 40) · Ebat 20
· Aşama-1 100 · Aşama-2 120 · Aşama-3 160.
**Ebat:** her boyut < 100 cm **zorunlu**; en uzun boyut ≤ 60 cm ise **20 puan**.
**Ödül şartı:** Aşama-3'ten **en az 10 puan** (yoksa ilk üçte bile olsan ödül yok).

| Aşama | Mod | Kurgu | Puan | Baraj / başarısızlık |
|---|---|---|---|---|
| 1 | **Manuel** | 4 hedef, 5/10/15 m, durağan, rastgele dizilmiş. İmha sırası **zarfla** verilir. | Yakın 5 / Orta 10 / Uzak 20 · max 80 + bonus `20×(kalan sn/300)` · yanlış sıra −5 · 5 dk | **≥20 puan** *(V1.4'te 30'dan düştü)* |
| 2 | **Otonom** | 4 tur, 3 koldan aynı anda 3 hedef (Füze + Mini/Micro İHA), A→B. Hedefler **parkurdan çıkmadan** imha edilmeli. Tip sınıflandırması beklenmez. | Tur başına 1/2/3 hedef = 5/15/30 · max 120 · tur başına −5 | **≥20 puan** |
| 3 | **Otonom** | 8 tur; her turda 1 düşman + 2 dost. Düşmanı tipine uygun menzilde imha. | F16 30 · Heli/Füze 20 · İHA 10 · max 160 · dost vurma / düşmanı vuramama −10 (tur başına en çok −10) | **≥10 puan**; **4 ardışık tur** düşman vuramayan takım 0 alır |

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

**Video (7 yetenek):** 1 arayüz/joystick/klavye anlatımı · 2 durağan 15 m balon ·
3 hareket ederken E-Stop · 4 ateş ederken E-Stop · 5 hareketli hedef takibi ·
6 **5/10/15 m'de tespit + sınıflandırmanın arayüzde gösterimi** ·
7 **(OPSİYONEL)** 10 m'de 1 kırmızı + 2 mavi; otonom düşman imhası, 10 sn bekle,
E-Stop, 10 sn bekle, kapat — dostlara ateş edilmediği görülür.
720p+, 2–5 dk. *(Yetenek 6 artık opsiyonel DEĞİL.)*

**Güvenlik [KESİN]:** harekete-yasak + atışa-yasak alan tanımı zorunlu; sistem yalnız
hedef tarafına bakabilir; **dışarı çıkan kabloyla, güvenli konumda donanımsal acil
durdurma butonu zorunlu** (basmalı/çevirmeli/manyetik); açıkta kablo olmayacak.

---

## 3. Sistem mimarisi

```
Kamera → algi.py (YOLO+takip) → nisan.py / hedef_kestirici.py (PD + kestirim)
       → arayuz_qt.py (kapılar, operatör)
       → kontrol.py ─┬→ tilt_surucu.py → ESP32-S3 (ws_motor_test)  [tilt + pan]
                     └→ protokol.py    → eski ESP32 kartı          [yalnız pan]
```

| Katman | Dosya | Rolü |
|---|---|---|
| Arayüz | `arayuz_qt.py` (4.3k satır) | Manuel/Otonom, aşama, açı karoları, yasak alanlar, kol göstergesi, E-Stop |
| Görünüm | `tasarim.py` | Renk/ölçü/QSS **tek kaynak** (Apple macOS dili) |
| Algı | `algi.py`, `renk_analizi.py` | Tespit (YOLO11 + ByteTrack), kesin tanıma, dost/düşman rengi, **düşmanın altındaki balon** (`ek_balonlari_tespit_et`) |
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
- Klavye: `W/A/S/D` veya oklar = yön · `R` (2 sn) = merkez · `Space`+`B` (2 sn) = ateş ·
  `Esc` = ateşi kes. Kol: D-pad + sol çubuk (yatay) / sağ çubuk (dikey) · L2+R2 (2 sn) =
  ateş · L1/R1 (2 sn) = merkez · Options = E-Stop.

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

### 7.2 Diğerleri
| Konu | Durum |
|---|---|
| ~~E-Stop'ta tilt park mı~~ | **Kapandı (23.09):** iki eksen de olduğu yerde donar. Yeni tilt kartı zaten donduruyordu; eski yoldaki park kaldırıldı (kartla laptop farklı şey söylüyordu) |
| Lazer | Hiç bağlanmadı: PWM frekansı, 3.3 V/5 V mantık seviyesi, GPIO 18'e 10 kΩ pull-down doğrulanmadı |
| Balon modeli | **Yol açıldı (23.09):** `models/` içine balon tanıyan ek bir `.pt` konursa otomatik yüklenir, düşman hedefin altında aranır ve nişan **balonun merkezine** gider. Ek model yoksa nişan yine gövdeden kestirilir (`balon_ofset`) — asıl iş hâlâ **ana modele balon sınıfını eklemek** |
| Aşama-1 zarf sırası | Arayüzde sürükle-sırala var ama **hiçbir yer okumuyor**; ceza mantığı yok |
| Dwell (lazeri hedefte tutma) | Yok |
| Mesafe ölçümü | Yok; 10–15 m bandı kontrolü de yok (A3 menzil kuralı buna bağlı) |
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

- **23.09.2026 · final_v7-yunus-yakin-takip** — 5 m arayüz testlerindeki titreme/savrulma.
  (1) Arayüzün Qt kamerası OpenCV yolundan ~25 ms geç (ölçüldü: 60–70 vs 40 ms); takip
  motorun kendi dönüşünü hedef hareketi sanıyordu → `kamera.QT_EK_GECIKME`. ⚠ Tolerans
  ±15 ms: kamera/FPS değişirse yeniden ölçün. (2) Renkle kilit sürdürme yalnız ≤48 px
  (uzak) hedefte; yakında kırmızı parçalanıp kutu 16–48 px zıplıyordu. (3) Kilit penceresi
  en tutarlı kutuyu seçer. (4) **E-Stop pan'ı 0 sanıyordu** (pan motoru olmayan eski
  kartın satırı) → ilk manuel tuş namluyu 28°→1° savurdu; artık ölçülen pan. (5) Otonomdan
  manuele geçişte açılar ölçülen konuma hizalanır. (6) Kilit kimliği değişince takip
  sıfırlanır, yörünge hız komutu ≤45 °/s. Otonomda her ölçüm `app/loglar/takip_*.csv`.
  Not: A2'de hedef 0.5 sn merkezde kalınca "vuruldu" sayılıp 10 sn seçilmez — saf takip
  testi **Aşama 1**'de yapılır. Pilde algı %40–60 yavaş: testte şarj takılı olsun.
- **23.09.2026 · final_v7** — `final_v6` + uzak/hareketli hedef takibi (10 m motorlu saha
  testleriyle). Model kilitli hedefi bir karede kaçırırsa yanındaki kırmızı leke o karenin
  ölçümü olur (`renk_takip`; model 1.5 sn doğrulamazsa kilit yine düşer). Küçük + kırmızı
  uzak aday %35 güvenle onaylanır (`uzak_onay_esigi`). Kilit penceresi 213 + 320 px birlikte
  taranır (10 m'de bulma %70 → %92). A2/A3 renk kuralları v6'daki gibi kaldı. Ölçüm: aynı
  10 m kayıtlarında yavaş yürüyen hedef %73 → %100, motorlu canlı %83 → %91.
  ⚠ Hedef aynı renkte geniş bir yüzeyin (kırmızı tişört) önündeyken model onu göremiyor.
- **23.09.2026 · final_v6 (balon)** — Arkadaşın `balontespit` dalındaki balon işi alındı
  (başka hiçbir şeyi değiştirmeden): ek balon modeli tam kareyi değil **tanınan hedefin alt
  penceresini** tarar. Üstüne iki karar: balon **yalnız düşman** için aranır (dosta ateş
  yok, boşuna FPS harcanmaz) ve bulunan balon artık **nişan noktasıdır** — PD, ekrandaki
  nişangah ve cv2 çizimi aynı listeden beslenir, birden fazla aday varsa asılma noktasına
  **en yakın** olan seçilir. ⚠ Gerçek balon modeliyle/donanımda denenmedi.
