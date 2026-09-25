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
| 7 | **Otonom ateş yalnız o karede GERÇEKTEN görülen hedefte BAŞLAR** — hayalet kutu / eski sınıf belleği yetmez; A3'te yalnız kartı "Düşman" olan (renk kanıtı şartı 23.09 takım kararıyla kalktı). Başlamış ateşi kesen: E-Stop, atışa yasak açı, dost/menzil engeli, kilidin düşmesi ya da başka hedefe geçmesi. **Balonda istisna (24.09, kullanıcı isteği):** ateş `otonom_ates_suresi()` (varsayılan 2 sn; 25.09'dan beri lazer kutucuğunda 0.5–5 sn) sürer, hayalet kesmez — lazer noktası modeli kör ediyor. Araçta hayalet keser. | Aşama-3'te dost vurmak −10 puan. Lazer altındaki balona 37 atışın 37'si 0.2 sn'de kesildi. |
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
| Lazer | **Tek kart (24.09):** S3 GPIO 18, firmware yüklendi ve kartla doğrulandı (LZR1 yayını, STOP/START, güç) — **lazer takılı değilken; yakılarak denenmedi.** Doğrulanmadı: PWM frekansı sürücüyle uyumlu mu, 3.3 V/5 V mantık seviyesi, GPIO 18 ↔ GND 10 kΩ pull-down. Acil buton GPIO 15'e henüz bağlanmadı |
| Balon modeli | **Kuruldu (24.09)**, kendi kameramızın koridor videosunda ölçüldü (ayrıntı: `git log -p CLAUDE.md`). Menzil içinde (balon ≥16 px) A2/A3 kilidi %96–100. ⚠ **Model, altında drone asılı ~18 m'deki balonu hiç görmüyor** (1080p'de de; 604–1145. kareler): bu videonun kareleri etiketlenip `bestb2` yeniden eğitilmeli. Araç modeli (`best.pt`) el yapımı drone/F16'yı neredeyse hiç okumuyor → A3 kartında **tip çoğunlukla yok**: operatör "Aranan" tipi seçerse tipsiz balon kilitlenmez; balon çapı girilirse tipsiz balona yalnız 10–15 m'de ateş (ortak bant). Hareketli namluda (bulanıklık) ve açık havada denenmedi. ⚠ 24.09 akşam: uzaktaki **pembe, çubuğa bağlı** balonları hiç tanımıyor (kayıtta 10 sn tespit 0; 96–320 px her pencere boyunda 48 denemede ≤7) — pencere ayarı değil, eğitim verisi. ⚠ **25.09 (15–17 m, balon 11–12 px): direğe/makete bitişik balonları (Şekil 3 dizilişi) hiç görmüyor**, serbest asılı olanı görüyor; ~25 px'te üçünü de. Yeniden eğitim verisi: `app/veri_toplama/20260925_172654` (yerel, yüzlü — repoya girmez) |
| Aşama-1 zarf sırası | Arayüzde sürükle-sırala var ama **hiçbir yer okumuyor**; ceza mantığı yok |
| Dwell (lazeri hedefte tutma) | Balonda ateş taahhüdü (varsayılan 2 sn, lazer kutucuğundan ayarlanır) + körlükte yol izleme (24.09, §8) — **donanımda denenmedi** |
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

- **25.09.2026 · final_v12 (saha: AI 10 FPS'e düştü)** — Ölçüm (gerçek modeller, kesintisiz
  saha kaydı + uygulamanın kendisi ekransız): Aşama 1 ~60–75 ms/kare, Aşama 2 ~33 ms. A1'in
  %40'ı kilit penceresi (kilitli uzak araç ana taramada görünmeyince HER kare, 2 pencere),
  kalanı araç + balon modeli; GPU %23 dolu — darboğaz model çağrısı başına Python yükü.
  **Asıl bulgu:** Windows güç kısıtlaması (EcoQoS) açıkken aynı döngü **147 ms** (6.8 FPS),
  yalnız E çekirdeklerde 89 ms (0.66×, sahadaki düşüş oranı ~0.64); o gün 16:47–16:54 ve
  21:03–21:22 **pille** çalışılmış (Kernel-Power 105). Yapılan: (1) `main()` süreç için güç
  kısıtlamasını kapatır (`windows_kisitlamasini_kapat`, belgeli API, sistem ayarı değil;
  kısıtlama yokken hız aynı). (2) Tüm model çağrıları FP16 (`algi.cikarim_ayari`, ayar
  "hizli_cikarim"): A1 −%15 (3 tur sıralı A/B), A2 fark yok; tespitler aynı (balon
  1083/1083, araç 527/532 — farklar eşiğin ±0.01 sınırında, kutu ≤ 1.5 px, sınıf 0). (3)
  `kirmizi_oneri` aynı kare nesnesinde bir kez. Elenen: yalın çıkarım (Predictor'sız, sonuç
  birebir ama kazanç < 1 ms), iki modeli paralel koşturmak (−%16 ölçüldü, çekirdek döngü
  değişir — ekip kararı), TensorRT (paket kurulumu gerekir). **Sahada şart: şarj kablosu
  takılı, Windows güç modu "En iyi performans".** 9 mutasyonun 9'u yakalandı. **Donanımda
  denenmedi.**
- **25.09.2026 · final_v12 (kullanıcı isteği: lazer süresi + nişangah ayarı)** — ATEŞ'in
  ⚙'i ile açılan lazer kutucuğuna iki bölüm: (1) **Otonom atış süresi** kaydırıcısı 0.5–5 sn
  (0.1 sn adım, varsayılan 2 sn `algi.VARSAYILAN_AYAR["otonom_ates_sure"]`); tur başında
  okunur, süren turu değiştirmez. `balon_takip` imha penceresi artık tur + 1 sn (sabit 3 sn
  4 sn'lik turda patlayan balonu saymıyordu). (2) **Nişangah** okları: 1 tık = kamera
  karesinde 1 px, basılı tutunca sürekli; kutucuk açıkken artı ortası boş yeşil çizilir
  (kırmızı lazer noktası görünsün). Otonom takip ve ateş kapısı bu noktayı kullanır (değişen
  yalnız arayüz; `lazer_ofset_x/y` kare oranı olarak kalır). Eski %1 adımlı panel
  kaydırıcıları (13 px atlıyordu) kaldırıldı. Güç kartın ayarı olduğu için taslak + onay;
  süre ve nişangah anında uygulanır ve `ayarlar.json`'a yalnız kendi anahtarlarıyla yazılır
  (atomik). Otonom BAŞLADIKTAN sonra nişangah değişmez; görüntü panelinin Sıfırla'sı bu
  üçüne dokunmaz. 8 mutasyonun 8'i yakalandı. **Donanımda denenmedi.**
- **25.09.2026 · final_v12 (saha: 15–17 m'de balonlar tanınmıyor)** — 17:26 oturumu, standda
  3 balon ~11–12 px. (1) **Pencere boyu:** model büyütmeye duyarlı; 11 px balon 128 px
  pencerede %61, 80–96 px'te %98. İz penceresi tabanı 128 → 80; leke turlarında sırayla 80 /
  128 taban (uzakta leke balonla gövdeyi birleştirir, leke boyu balon boyunu söylemez). Tüm
  hat, gerçek kareler (150 × 10 tekrar): serbest asılı balon ekranda 132 → 149, kilit 139 →
  150; balonsuz zemin / insanlar / yakın stand aynı, süre aynı. (2) **Kalan:** direğe ve
  makete bitişik balonlar (Şekil 3 dizilişi) 15–17 m'de her pencerede ve ön işlemede (kübik,
  keskinleştirme, kontrast, TTA) 0; ~25 px'te üçü de 0.9. Aynı karelerde gövde rengi doğru
  (mavi yıldızlı 149/149 Dost, kırmızı uçaklı 146/148 Düşman): A3 ayrımı çalışıyor, eksik
  olan tespit. Renk+şekil bulucu denendi: cam yansıması, insan, duvar figürü, maketin kendisi
  → ateşe dayanak olamaz. Çözüm yeniden eğitim (§7.2). 5 mutasyonun 5'i yakalandı.
  **Donanımda denenmedi.**
