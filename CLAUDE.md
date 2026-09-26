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
| 6 | **Ateş tek kapıdan; ACİL DURDUR kısayolu aç/kapa ama korumalı.** Ateş: `Space`+`B` birlikte, kol `L2`+`R2` birlikte (tek dokunuş, bekleme yok; tek tuş boş) — hepsi `_ates_bas`. ACİL DURDUR: `Esc`, kol `Options/Start` (24.09; Backspace ve Daire boş). İlk basış kurar, **tekrar basış DEVAM** (24.09 kullanıcı kararı) — yalnız kurulduktan `ESTOP_KISAYOL_BEKLEME_S` (1 sn) sonra; klavye otomatik tekrarı ve kolda basılı tutma sayılmaz. İki yön de `_estop_bas`'tan geçer: donanım butonu basılıyken devam yok. | Kol eskiden Options'ın ikinci basışında acil durdurmayı **anında** kaldırıyordu (panikte çift basış). |
| 7 | **Otonom ateş yalnız o karede GERÇEKTEN görülen hedefte BAŞLAR** — hayalet kutu / eski sınıf belleği yetmez; A3'te yalnız kartı "Düşman" olan (renk kanıtı şartı 23.09 takım kararıyla kalktı). Başlamış ateşi kesen: E-Stop, atışa yasak açı, dost/menzil engeli, kilidin düşmesi ya da başka hedefe geçmesi. **Balonda sürekli yakma (26.09 akşam kullanıcı kararı; `ates_parcali`=1 eski parçalı yakma):** tur = toplam `otonom_ates_suresi()`; nişan balondayken lazer yanar; lazerden sonra çekilen 2 karede balon görülmezse (patladı) ya da modelin gördüğü 5 ARDIŞIK karede nişan balon merkezinden 1.5 yarıçaptan uzaksa söner (26.09 gece genişletildi), tur sürer; **her yeniden yanma** yine yalnız o karede görülen balona + nişan kapısı açıkken. Operatör keserse tur biter, 1.5 sn ateş yok. Araçta tek parça, hayalet keser. | Aşama-3'te dost vurmak −10 puan. Lazer altındaki balona 37 atışın 37'si 0.2 sn'de kesildi (24.09); 2 sn kör atışta namlu hareketli balondan 5° kaçtı (26.09). |
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
| Balon | `balon_takip.py` | **A2/A3 kilit + nişan balonda** (`models/bestb2.pt`); araç = balonun kimlik kartı (taraf/tip oyu); imha = ateş edilen balonun kaybolması. Lazer yanarken kilitli balonun penceresine ek **lazer altı modeli** (`models/lazer_uzman/bestb3_lazer.pt`, ayar `lazer_uzman`; alt klasörde — model taraması onu ana balon modeli sanmaz); aynı model bestb2'nin BOŞ döndüğü küçük arama/takip pencerelerinde **uzak balonu** da arar (ayar `uzak_uzman`, kaynak `uzak`) |
| Nişan | `nisan.py`, `hedef_kestirici.py` | Piksel hatası → açı (PD), yörünge kestirimi, salınım EKF'si (`KarmaKestirici`), balona ateş kapısı (`AtesKapisi`) |
| Güvenlik alanı | `bolge.py` | İzinli pencere modeli (hareket/atış) — **tek sınır kaynağı** |
| Kontrol | `kontrol.py`, `protokol.py`, `tilt_surucu.py`, `mock_esp32.py` | Karta giden **tek kapı** + donanımsız çalışma |
| Girdi | `gamepad.py`, `kol_ikon.py`, `kontroller.py` | Kol okuma + ekrandaki kol göstergesi + **tuş listesi (tek kaynak, üstteki "Kontroller" paneli)** |
| Kamera | `kamera.py` | **Yalnız harici USB kamera** (dahili/telefon/sanal elenir) |
| Testler | `kapi_testleri.py` | Güvenlik kapıları (§6) |

**Ortam değişkenleri:** `DERINMAVI_ESP` (`mock` \| port \| `off`) · `DERINMAVI_TILT`
(`off` \| port) · `DERINMAVI_CAM` (dosya/RTSP) · `DERINMAVI_MODEL`.
Port adı `tilt_surucu.port_adi`'dan geçer: yalnız `COM3` biçimi büyütülür, Mac/Linux yolu
(`/dev/cu.usbmodem…`) harf duyarlıdır — `.upper()` Mac'te kartı "yok" gösteriyordu.

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
| **Tilt krank-biyel ölçüleri** (26.09, kullanıcı verdi — ⚠ KAYBETME) | Motora bağlı krank **18 mm** · iletim çubuğu (biyel) **153 mm** · 60° dönen çıkış miline bağlı kol **36 mm**. Motor mili ↔ çıkış mili mesafesi verilmedi. Kol 0–60° = 2675 darbe (krank ~0.42 tur) | kullanıcı, mekanik |
| Sürücü çözünürlüğü | 6400 step/tur | `protokol.STEP_TUR` |
| Pan redüksiyon | 83/15 ≈ 5.53 (98.37 step/°) | `protokol.PAN_DISLI` |
| Hız kademeleri | `tilt_surucu.HIZ_TABLO` / `PAN_HIZ_TABLO` | ölçümle ayarlanır |
| Lazer gücü varsayılan | **%40** | `protokol.LAZER_GUC_VARSAYILAN` (firmware ile aynı) |
| Tek kart pinleri (S3) | Lazer **GPIO 18** (PWM 1 kHz, 8 bit) · Acil buton **GPIO 15** (NO, GND'ye çeker, dahili pull-up; 27.09 bağlandı, çalışıyor) · tilt 4/5 · pan 10/11/16 · buzzer 12 — **şema: `ws_motor_test/esp32s3_baglanti_semasi.png`** | `ws_motor_test/esp32_ws_test.ino` |
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
- Klavye: `W/A/S/D` veya oklar = yön · `R` = merkez · **`Space`+`B` birlikte = ateş** (tek tuş boş) · `Z`/`X` = zoom yakın/uzak · `C` (art arda 1/2/3) = hassasiyet ·
  **`Esc` = ACİL DURDUR aç/kapa** (tekrar basış ≥1 sn sonra devam). Kol: D-pad + **sol joystick (yatay + dikey)**, **sağ joystick Y = görüntü zoom'u**
  (otonomda yok, en çok 4×, yalnız ekran — komut üretmez) ·
  **Options/Start = ACİL DURDUR aç/kapa** · Çarpı/A (art arda 1/2/3) = hassasiyet · L2+R2 birlikte = ateş · **L1+R1 birlikte** = merkez.
  Acil durdurmadan çıkış: DEVAM ET butonu ya da aynı kısayol; donanım butonu basılıyken olmaz.
- **Mod = aşama (25.09):** Aşama 1 = Manuel (kendiliğinden seçili). Aşama 2/3 seçilince
  **hazırlık** (`mod == "Hazırlık"`): otonom başlamaz; elle kontrol **Aşama 1'deki gibi**
  (klavye/kol/ekran D-pad, merkez, zoom, Space+B — 25.09 akşam kullanıcı isteği). ATEŞ'in
  yerindeki **AŞAMA n'İ BAŞLAT** otonomu açar: o andan **elle hareket, merkez, zoom ve elle
  ateş AÇMA biter** (`_manuel_hareket_izni`; kısayol otonomda ateşi yalnız KESER), süren
  merkeze alma durur. Tekrar basış hazırlığa döndürür. Sağ kolon her aşamada aynı; aşamaya
  özel olan (A1 zarf / A2-A3 takip-nişan-aranan) alt satırda. Mod değişince elle açılmış ateş kesilir.
- **HASSASİYET** (D-pad altında): Hassas 0,1° / Orta 0,5° (açılış) / Hızlı 1° tek dokunuş;
  basılı tutma 3 / 10 / 40 °/sn. 15 m'de 1° ≈ 26 cm. Kol D-pad'i de tek dokunuş atar,
  joystick karesel. Tablo: `MainWindow.HASSASIYET`. Merkeze alma/otonom etkilenmez.
- **Ekrandaki kutular (25.09 video):** kutu algı thread'inin eski karesinden gelir; çizilirken
  kart açı geçmişiyle kameranın o andan beri dönüşü kadar kaydırılır (`kamera_kaymasi_px`,
  kart bağlı değilse telafi yok). Oturmuş balon izi kısa kaçırmada kesikli kutuyla kalır.
  Etiket **tek satır** (`F-16 %93`, `Balon %91`): dost/düşman yazılmaz, **renk söyler** (mavi
  dost, kırmızı düşman, yeşil hedef). `etiket_yerlestir` etiketleri birbirinin ve başka
  hedefin üstüne bindirmez; kilitli hedefinki önce yer seçer, istiflenen ince çizgiyle bağlı.
- **Bir tuşu değiştiren `kontroller.py`'yi de değiştirir** (üst çubuktaki "Kontroller" paneli oradan
  okur). Ayrışırsa `kontroller.py` / `kapi_testleri_arayuz.py` kırmızıya düşer.

---

## 6. Doğrulama — push öncesi koş

```bash
python app/kapi_testleri.py        # birleşik arayüz (gerçek pencere açar)
python app/kapi_testleri_arayuz.py # GÜVENLİK KAPILARI, pencere AÇMADAN (36 test)
python app/bolge.py            # yasak alan matematiği
python app/protokol.py         # komut üretimi + sabit tutarlılığı
python app/kontrol.py          # mock cihazla uçtan uca
python app/tasarim.py          # arayüzde stilsiz bileşen var mı
python app/algi.py  app/nisan.py  app/kamera.py  app/gamepad.py  app/kol_ikon.py  app/kontroller.py
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
| Lazer | **Tek kart (24.09):** S3 GPIO 18, firmware yüklendi ve kartla doğrulandı (LZR1 yayını, STOP/START, güç) — **lazer takılı değilken; yakılarak denenmedi.** Doğrulanmadı: PWM frekansı sürücüyle uyumlu mu, 3.3 V/5 V mantık seviyesi, GPIO 18 ↔ GND 10 kΩ pull-down. Acil buton GPIO 15 bağlandı ve çalıştı (27.09). **Lazer MAVİ (26.09):** kırmızı balonu mora boyuyor, model lazer altında balonu tanımıyor → kilitli balonun çevresinde model girdisinde mavi = min(mavi, yeşil) (`balon_takip._mavi_bastir`; gerçek 154 lazerli karede %34 → %56). Üstüne lazer altı modeli (26.09, §8): görülmemiş 76 lazerli karede %70 → %92. Eğitim karesi `app/veri_toplama/*/kacirma_*.jpg` (yüzlü — repoya girmez) |
| Balon modeli | **Kuruldu (24.09)**, kendi kameramızın koridor videosunda ölçüldü (ayrıntı: `git log -p CLAUDE.md`). Menzil içinde (balon ≥16 px) A2/A3 kilidi %96–100. ⚠ **Model, altında drone asılı ~18 m'deki balonu hiç görmüyor** (1080p'de de; 604–1145. kareler): bu videonun kareleri etiketlenip `bestb2` yeniden eğitilmeli. Araç modeli (`best.pt`) el yapımı drone/F16'yı neredeyse hiç okumuyor → A3 kartında **tip çoğunlukla yok**: operatör "Aranan" tipi seçerse tipsiz balon kilitlenmez; balon çapı girilirse tipsiz balona yalnız 10–15 m'de ateş (ortak bant). Hareketli namluda (bulanıklık) ve açık havada denenmedi. ⚠ 24.09 akşam: uzaktaki **pembe, çubuğa bağlı** balonları hiç tanımıyor (kayıtta 10 sn tespit 0; 96–320 px her pencere boyunda 48 denemede ≤7) — pencere ayarı değil, eğitim verisi. ⚠ **25.09 (15–17 m, balon 11–12 px): direğe/makete bitişik balonları (Şekil 3 dizilişi) hiç görmüyor**, serbest asılı olanı görüyor; ~25 px'te üçünü de. Yeniden eğitim verisi: `app/veri_toplama/20260925_172654` (yerel, yüzlü — repoya girmez) |
| Aşama-1 zarf sırası | Arayüzde sürükle-sırala var ama **hiçbir yer okumuyor**; ceza mantığı yok |
| Dwell (lazeri hedefte tutma) | Balonda ateşi **nişan kapısı** başlatır, **sürekli yakar** (26.09 akşam, §1 kural 7; eski 0.5 sn kesintisiz bekleme yalnız araç hedefinde). ⚠ Tilt: 19:59 kaydında namlunun dikey yolu benzetimin 1.3 katı (pan tutuyor). 26.09 21:34 doğrudan ölçüm (`tilt_yon_testi.py egri`): kol ≥ 21'de güvenilir, kol 35–49'da tablo ölçüme yükseltildi; **kol 0–20'de kamera yakın zemine baktığı için ölçüm geçersiz** (uzak sahneye bakarak yeniden ölçülmeli). Benzetim: tablo gerçekten AZ derse (g ≥ 1.6) takip kararsız, FAZLA derse yalnız uyuşuk → tablo ölçümsüz DÜŞÜRÜLMEZ. Balonun patlama süresi (güç %40/%100, 5/10/15 m, sürekli/parçalı) sahada ölçülmedi |
| Mesafe ölçümü | **Balon çapından** kestirim (24.09): ⚙ "Balon çapı (cm)" sahada cetvelle ölçülüp girilmeli, 10 m'de etiketle doğrulanmalı. Girilmezse (0) A3 menzil kontrolü YOK. Çap yanlışsa A3'te hiç ateş edilmeyebilir |
| Homing | Gerçek limit switch yok; `home()` = "0°'a dön" |
| Doküman tutarsızlığı | `FINAL_ENTEGRASYON.md` hâlâ "pan ±90 yapısal" diyor; artık kodda sınır yok (23.09) |

### 7.3 Eski notlardan düzelenler (V1.4 ile değişti)
Aşama-1 barajı 30 → **20** · Aşama-3 "3 ardışık tur" → **4 ardışık tur** ·
Aşama-2'de ayrı "3 tur üst üste = 0" kuralı **yok** · video yetenekleri 6 → **7**
(Yetenek 6 zorunlu) · video tarihi 10.08 → **17.08.2026** · balon rengi artık
**[KESİN] kırmızı**.

---

## 8. Değişiklik günlüğü (yalnız son 3 madde tutulur)

- **26.09.2026 akşam · derin_mavi_fitifnal (saha 19:59: "hareketliyken vuramıyor, geriden takip,
  lazer açmıyor, tilt aşıyor")** — (1) Balonda **sürekli yakma** (kullanıcı kararı; lazer altı
  modeliyle balon lazer altında da görülüyor): §1 kural 7; lazer kutucuğunda "Parçalı ateş"
  anahtarı (vars. kapalı). (2) Salınım EKF'si **varsayılan KAPALI** (`takip_ekf` 0): seçildiği
  karelerde nişan hatası iki kat (pan 0.61 → 1.08, tilt 0.62 → 1.24 yarıçap). (3) Teşhis: 10
  kilitte nişan, görülen karelerin %38'inde balonda (benzetim aynı yollarla %43 — sahayı tutuyor).
  Kayıttan çıkan balon yollarında gecikmesiz ideal öngörücü bile 0.2 sn sonrasını 0.7–1.3 yarıçap
  kaçırıyor → EKF, ileri besleme 0.5 → 1.0, tilt filtresi sonucu DEĞİŞTİRMEDİ (%43); gecikme ×0.7
  → balon üstünde yakma 1.37 → 1.60 sn, yanarken balonda %59 → %71; kapıyı gevşetmek +%5–10.
  Gecikme (saha CSV): kare damgası → AI bitti 100 ms (Qt kamera payı 25 ms dahil), AI → arayüz
  16 ms, AI periyodu 49 ms (araç modeli 16 + balon 18 ms). Uzak balon: bestb2 makete bitişik
  16 px balonu videoda 331 karenin 0'ında, lazer altı modeli 310'unda gördü (normal karede bir
  afişi de balon sandı). `tilt_yon_testi.py egri` onarıldı (olmayan
  `tilt_egri` modülünü çağırıyordu). 22:23 kaydı: balon ancak 18–19 px'te (~12–13 m) görülüyordu;
  bestb2 makete bitişik uzak balonu 121 karenin 0'ında, ikinci model 121'inde gördü → ikinci model
  bestb2'nin boş döndüğü küçük pencerelerde de çalışır (`_uzak_tespit`, ayar `uzak_uzman`);
  görülmemiş koridor karelerinde sahte tespit bestb2 0.09 / ikinci model 0.11 kare başına. Tilt
  tablosu yalnız GÜVENLİ yönde (yükseltilerek) ölçüme göre güncellendi (§7.2). Nişan dışı kesme 2 kare/1.0 → 5 kare/1.5
  yarıçap. Yavaş kayan küçük balon artık akan kipte (akış/duruş eşiği 2.0/1.0 → 1.5/0.75 der/sn, yalnız
  ≤24 px; `HK.SAHA_AYARI`): kayıtlarda kilitli balon tespiti 13–16 Hz geliyordu, ama hedef 0.5–3 der/sn
  giderken komutların %34–50'si "git-dur"du. **Aşama 2: yalnız balon** (ayar `a2_yalniz_balon`, vars. açık):
  A2'de araç modeli hiç çalışmaz (dost yok, tip beklenmez), kare ~16 ms kısalır; A3 etkilenmez.
  **Donanımda denenmedi.**
- **26.09.2026 · derin_mavi_fitifnal (lazer altı balon modeli; kullanıcı: "ekstra olsun, eski modeli
  bozmasın")** — `bestb2`'den ince ayarla ikinci model `models/lazer_uzman/bestb3_lazer.pt` (ayar
  `lazer_uzman`, 0 = yalnız bestb2). Veri (yerel, yüzlü, repoya girmez): gerçek lazerli balon
  kırpıntıları (uçak / yalnız parlama etiketleri elle elendi; kırpıntıda etiketsiz balon kalırsa
  atıldı), lazerin balonsuz yere vurduğu kareler (negatif), koridor videosu + yapay mavi lazer;
  girdi hep mavi bastırılmış. Yalnız lazer kilitli balondayken, o balonun 7 boy penceresinde,
  bastırma bölgesinde bestb2'nin GÖRMEDİĞİ kutuyu ekler; kutu yalnız kilitli izi sürdürür (yeni iz,
  geniş eşleşme yok); lazersizken çıktı birebir bestb2; hata verirse kendini kapatır. 4 katlı
  oturum çapraz doğrulaması (76 görülmemiş lazerli kare): bestb2 %37, + bastırma %70, model %87,
  **birlikte %92**; lazerin balonsuz yere vurduğu 288 kilit yerinde sahte kutu 0; lazersiz 125
  karede 104 → 105. "Bilinmeyen yerde" 15 kutunun 14'ü direğe bitişik gerçek balon (bestb2 görmüyor).
  Maliyet: lazer yanarken kare başına +13 ms (RTX 3050 Ti, FP16). Benzetim: hareketli balonda
  yakma 1.37 → 1.5 sn, duranda fark yok. Ayrıca `_lazer_bak` kutu merkezi kare dışındayken sıfıra
  bölüyordu (o karede balon takibi boş dönüyordu) — düzeltildi. 11 mutasyonun 11'i yakalandı.
  **Donanımda denenmedi.**
- **26.09.2026 · derin_mavi_fitifnal (saha: hareketli balon patlamıyor; lazer MAVİ)** — Bu
  gecenin kayıtları (01:32, ≈10 m hareketli balon): lazer yanınca tespit ~0.2 sn'de bitiyor
  (6/6 atış); takip "körlük"te son 1.5 sn'nin doğrusunda sürdü (01:33:06: 2.2°/sn × 2 sn = 5.4°),
  balon lazer sönünce 9 yarıçap uzakta, YENİ kimlikle döndü (B1→B6, 5 yanlış imha); ateş dışı
  namlu balonun kendi hareketini izliyordu (görünen salınım, dönüşteki 6.7° sıçrama). Yapılan:
  (1) **Parçalı yakma** (arayüz, §1 kural 7): parça ≤ 0.5 sn, lazerden sonra çekilen 2 karede
  balon yoksa hemen kes, aynı balon + nişan kapısı → yeni parça; lazer kutucuğunda "Parça
  süresi"; ayar `ates_kayipta_kes`. (2) **Mavi bastırma** (lazer kilitli balondayken model
  girdisinde). (3) **Lazer sonrası geniş yeniden eşleşme** (4 boy, TEK aday, boy oranı dar).
  (4) Kendi mavi lazerimiz A3'te "dost gövde önünde" sanılmaz (lazerli karelerin %14'ünde
  tetikleniyordu); dost araç/balon kontrolleri sürer. (5) Takip körlüğü lazerle biter (+0.85 sn
  kalktı). Benzetim (lazer altında kör, hareketli 15 sahne): lazer yanarken balonda %37 → %72,
  balonun üstünde yakma 0.40 → 1.11 sn. Firmware darbesi (0.3/0.1 sn) denendi, elendi (%36).
  Kontrolcüyü yumuşatma ölçüldü: ivme tavanı 150'ye kadar isabet aynı, 100'de −5 puan
  (yapılmadı). 13 mutasyonun 13'ü yakalandı. **Donanımda denenmedi.**
