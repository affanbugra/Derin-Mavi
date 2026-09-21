# DERİN MAVİ — Proje Beyni (CLAUDE.md)

> Bu dosya projenin **beynidir** ve her oturumda otomatik yüklenir. Önemli her karar, gerçek,
> context ve teknik çalıştırma notu **tek yerde** burada tutulur. **Yaşayan dokümandır** — bir şey
> netleştikçe/değiştikçe güncellenir. Repoda yalnızca **iki doküman** vardır: bu CLAUDE.md (proje
> beyni, teknik derinlik) ve [README.md](README.md) (ekibin okuyup kurması için özet). İkisi de
> repoda açıktır.

---

## 0. Claude, sen kimsin ve nasıl çalışmalısın (HER OTURUMDA HATIRLA)

Sen bu projede **teknik danışman + yazılım geliştirme ortağısın.** Amaç net: TEKNOFEST 2026
Çelikkubbe Hava Savunma Sistemleri yarışmasında **BİRİNCİLİK.** Süreç boyunca eşlik ediyorsun.

**Çalışma prensiplerin:**
1. **Körü körüne uyma.** Kullanıcının veya KTR'nin dediği en iyi çözüm olmayabilir. Daha
   iyisini görüyorsan **söyle ve gerekçelendir.** Bunu sana her seferinde hatırlatmak zorunda
   kalmasınlar — bu senin varsayılan davranışın.
2. **Tek referans = ŞARTNAME.** KTR bile %100 bağlayıcı değil (araç sıfırdan yapılıyor).
   Bir çelişki varsa şartname kazanır. Emin değilsen `sartname/Şartname.pdf`'e (veya hızlı
   arama için `sartname/sartname_metin.txt`) dön.
3. **Her kararı PUANA bağla.** "Bu ne kadar puan getirir/kaybettirir?" sorusu pusulan.
   Baraj puanlarını geçmek önce gelir, sonra maksimizasyon.
4. **Basitlik kazandırır.** En sağlam çözüm en az parça içerendir (örn. 10–15m bandı içgörüsü).
5. **Dürüst ol.** Test başarısızsa söyle. Bir şey çalışmıyorsa "çalışıyor" deme. Riskleri
   erken sesli söyle (özellikle 10 Ağustos video baskısı).
6. **Türkçe konuş.** Ekip Türkçe çalışıyor.
7. **DONANIM-BAĞIMSIZ / DİNAMİK yaz.** Sistem şu an kullanıcının MateBook D15'inde
   geliştiriliyor ama yarışmaya **büyük ihtimalle daha güçlü, farklı bir laptopla** gidilecek.
   HİÇBİR şey bu makineye sabitlenmez: kamera index/backend otomatik bulunur (env override
   destekli), yollar göreli, model/donanım seçimi çalışma anında algılanır. Kod başka ortamda
   "indir-çalıştır" mantığıyla sorunsuz koşmalı. (Kamera kaynağı: `DERINMAVI_CAM` env — index
   / dosya / RTSP-URL; tanımsızsa otomatik tarama.)
8. **ŞARTNAME DİSİPLİNİ + KESİN/VARSAYIM AYRIMI.** Şartname gerektiren her bilgi/işlemde
   **gerçek şartnameyi tara** (`sartname/sartname_metin.txt` grep veya `sartname/Şartname.pdf` oku) —
   hafızaya/varsayıma güvenip **emin olmadan işlem yapma.** Bir bilgi şartnamede/resmi duyuruda
   yazıyorsa **[KESİN]**, senin/ekibin çıkarımıysa **[VARSAYIM]** olarak ayır ve öyle davran.
   Kesinmiş gibi davranıp yanlış yönlendirme = en büyük hata.

---

## 🔧 EKİP ÇALIŞMA KURALLARI (Git akışı + katkı — HERKES OKUR, İSTİSNASIZ)

> Bu bölüm takımın refahı ve işleyişi içindir. Kod ortak; bir kişinin dikkatsizliği herkesin
> işini bozabilir. Aşağıdakiler **kural**, öneri değil.

**1. ASLA doğrudan `main`'e commit/push YAPMA.**
- Her geliştirme kendi **alt branch'inde (feature branch)** yapılır:
  ```bash
  git checkout main && git pull           # önce güncel main'i al
  git checkout -b özellik/kısa-ad         # örn: özellik/gimbal-matematigi
  # ...çalış, commit at...
  git push -u origin özellik/kısa-ad
  ```
- `main` her zaman **çalışan, kararlı** sürümdür. Bozuk/yarım kod `main`'e girmez.

**2. `main`'e BİRLEŞTİRMEDEN (merge) ÖNCE mutlaka SOR / EMİN OL.**
- GitHub'da **Pull Request (PR)** aç, kendi başına merge etme.
- Merge etmeden önce ekibe sor: *"Bu değişikliği main'e alıyorum, herkesin haberi var mı?
  Kimsenin üstünde çalıştığı bir yeri bozuyor mu? Emin miyiz?"*
- En az **1 ekip arkadaşı gözden geçirip onaylamadan** merge YOK. Özellikle algı çekirdeği
  (`algi.py`), arayüz (`arayuz_qt.py`) ve kontrol (`kontrol.py/protokol.py`) gibi ortak kalpler
  değişiyorsa iki kez düşün — bunlar herkesin bağlı olduğu tek kaynaklardır.

**3. HER PC'de çalışacak şekilde yaz (taşınabilirlik — bkz. ilke 7).**
- **Makineye özel MUTLAK yol YAZMA** (`C:\Users\...`, `D:\Masaüstü\...`). Her yol `__file__`'a
  görelidir (`os.path.join(HERE, ...)`). Kamera/model/kontrolcü çalışma anında bulunur veya env
  ile geçilir (`DERINMAVI_CAM/MODEL/ESP/FOCAL`).
- **Yeni bir kütüphane kullandıysan `requirements.txt`'e EKLE.** Yoksa "bende çalışıyordu"
  olur, başkasında patlar. Sürüm sınırını da yaz (`paket>=x.y`).
- Yeni özelliği push etmeden önce **temiz kafayla dene**: uygulama açılıyor mu, hata veriyor mu?

**4. Commit hijyeni.**
- Anlamlı Türkçe commit mesajı yaz (ne yaptığını söyle: "gimbal PD kontrolü eklendi" gibi,
  "değişiklik" / "fix" değil).
- **Repoya girmemesi gerekenleri commit etme:** model dosyaları (`*.pt/.onnx`), veri setleri,
  `__pycache__`, kişisel/gizli dosyalar. `.gitignore` bunları zaten tutar — zorla eklemeye çalışma.
- Push'tan önce **`git pull` (veya `git pull --rebase`)** yap; çakışmayı dikkatle çöz, körü
  körüne "kabul et" deme (birinin emeğini silebilirsin).

**5. İletişim.**
- Bir dosyanın üstünde uzun çalışacaksan ekibe haber ver (aynı yeri iki kişi değiştirince
  çakışma çıkar). Büyük mimari değişikliği önce konuş, sonra kodla.
- Bir şeyi netleştirdinse/değiştirdiysen bu **CLAUDE.md yaşayan dokümandır** — ilgili yeri güncelle.

**6. Gizlilik.** Repo şu an public. Şartname/KTR gibi gizli belgeler, şifreler, kişisel veri
**asla** commit edilmez (`.gitignore` PDF/3mf/Analiz'i zaten engeller). Emin değilsen sorma
değil — önce sor, sonra push.

---

## 1. Yarışma takvimi (kritik tarihler)

| Tarih | Olay | Durum |
|---|---|---|
| 23.03.2026 | Ön Tasarım Raporu | ✅ Geçildi |
| 09.06.2026 | Kritik Tasarım Raporu (KTR) | ✅ Geçildi |
| **10.08.2026 · 17:00** | **Görev Kabiliyeti Videosu son teslim** | ⏳ **ŞU AN BURADAYIZ** |
| 24.08.2026 | Finalistlerin açıklanması | — |
| Ağustos–Eylül 2026 | Yarışma Finalleri | — |
| 30 Eylül–4 Ekim 2026 | TEKNOFEST | — |

**Şu anki faz: VİDEO AŞAMASI.** Araç henüz yok (mekanik ekip sıfırdan yapacak). Bu süreçte
bizim işimiz: yazılımı (görüntü işleme, model eğitimi, arayüz, kontrol katmanı) hazır etmek;
en son araçla entegre edip videoyu çekmek.

---

## 2. Görev Kabiliyeti Videosu — gösterilecek 6 yetenek (SIRAYLA)

720p+, 2–5 dk, tek YouTube (liste-dışı olabilir) linki, açıklamada yetenek zaman damgaları.

1. **Arayüz:** Kullanıcı komut arayüzleri (UI/joystick/klavye) tüm fonksiyonlarıyla anlatılır.
   *Entegrasyonu tamamlanmış sistem üzerinden göstermek = artı puan.*
2. **Durağan atış:** 15 m mesafedeki balonu patlatma.
3. **Acil Durdur (hareket):** Yan+yükseliş ekseninde hareket ederken E-Stop → sistem durur.
4. **Acil Durdur (ateş):** Ateş ederken E-Stop → ateş kesilir.
5. **Takip:** Yan+yükseliş ekseninde hareketli bir hedefi takip. (Hedef görsellere benzer
   herhangi bir unsur olabilir.)
6. **(OPSİYONEL)** 5/10/15 m'de farklı hedef tiplerinin tespit + sınıflandırması arayüzde
   (F16 / Mini-Micro İHA / Füze / Helikopter).

> Not: Video final değil ama finalist olmanın kapısı. Yetenek 1–5 zorunlu güç; 6 opsiyonel artı.

---

## 3. HEDEFLER ve DOST/DÜŞMAN — puanın kalbi (ŞÜPHE YOK)

| Kategori | Tip | Boyut | Renk |
|---|---|---|---|
| **Düşman** | Drone (İHA) | 30 cm | **Kırmızı #F50A0A** |
| **Düşman** | Helikopter | 50 cm | **Kırmızı #F50A0A** |
| **Düşman** | Savaş Uçağı F16 | 50 cm | **Kırmızı #F50A0A** |
| **Düşman** | Balistik Füze | 40 cm (boy) | **Kırmızı #F50A0A** |
| **Dost** | Helikopter | 50 cm | **Camgöbeği #00A3E0** |
| **Dost** | Savaş Uçağı F16 | 50 cm | **Camgöbeği #00A3E0** |

> **Yukarıdaki tablo = [KESİN] renk şeması** (renk kodları ayrı resmi kanaldan teyitli).
> Ama dost/düşman kararı **tipe DEĞİL, RENGE** bakar (aşağı).

**SSS / sık karışan noktalar:**
- *"Dost/düşman nasıl belirlenir?"* → **İki AYRI iş:** (1) model **nesneyi/tipi** tanır,
  (2) renk **tarafı** belirler → **maviye yakın = DOST, kırmızıya yakın = DÜŞMAN, arası yok.**
  Tipe bakan hiçbir kural YOK; ne renkse odur. Sadece **Aşama 3'te** yapılır.
- *"İHA/Füze hep düşman mı?"* → Pratikte kırmızı oldukları için renk kuralı onları düşman
  çıkarır — ama biz bir **tip-kuralı KOYMAYIZ**, renge bakarız. "İHA/Füze'nin cyan versiyonu
  yok" ifadesi **[VARSAYIM]** idi, artık **kullanmıyoruz** (gereksiz — renk zaten karar veriyor).
- *"Balon nerede olacak?"* → **[KESİN] maketlerin ALTINDA.** (Artık açık/belirsiz değil.)

**Görüş geometrisi (parkur çizimi + takım bilgisi — veri üretiminin temeli):**
- Hedefler raya asılı, zemine PARALEL, "hafif öne eğik" (burun-aşağı ~0-20°).
- Sistem-hedef yükseklik farkı ±0.5-1 m → 5-15 m'de dikey bakış açısı **±12° bandı**.
- Serpantin ray → hedef HER yaw açısından görülür (azimut 0-360).
- Kuş bakışı / ters / dik pozlar yarışmada FİZİKSEL OLARAK İMKÂNSIZ → sentetik veri
  %85 gerçekçi dağılım + %15 serbest (robustluk payı) üretir (`GERCEKCI_*` sabitleri).
- **Füze mesh'i DİK modellenmiş** ama şartname Şekil 6 + temsili fotoda maket YATAY asılı →
  render'da füzeye %70 yatay / %30 dik taban dönüşü uygulanır (montaj belirsizliği payı).

**HAYATİ KURALLAR:**
- **Dost/düşman = RENK, basit binary:** maviye yakın=DOST, kırmızıya yakın=DÜŞMAN, **arası yok.**
  **Tip (model) ile taraf (renk) AYRI adımlardır.** Aynı F16/Helikopter hem dost (cyan) hem
  düşman (kırmızı) olabilir. "İHA/Füze hep düşman" gibi bir tip-kuralı YOK — renge bakılır.
- **Renk/taraf yalnızca AŞAMA 3'te yapılır.** [KESİN] **Aşama 1 ve 2'de tüm maketler kırmızı,
  dost yoktur** → o iki aşamada renk işi HİÇ yapılmaz, sadece TANIMA yeterli (renk önemsiz).
- **Bu sene "angajman" kavramı YOK** (kullanıcı bilgisi) → arayüz dilinden çıkarıldı.
- **Balon rengi dost ve düşmanda AYNIDIR** → ayrım balondan YAPILAMAZ, maketin gövde renginden.
- **İmha kanıtı = balonun patlaması.** Balon maketin ALTINDA [KESİN], lazerle patlatılır.
- Maketlerin 3D dosyalarını TEKNOFEST paylaştı; **orijinal boyutta 3D baskı alınıp** gerçek
  test ortamı simüle edilecek. (Asıl model doğruluğu bu basılı maketlerin fotoğraflarıyla gelir.)

---

## 4. Aşamalar, puanlama ve barajlar

**Genel puan (toplam 500):** Rapor+Sunum 100 · Ebat 20 · Aşama1 100 · Aşama2 120 · Aşama3 160.
**Ebat:** en uzun boyut **≤60 cm = 20 puan**, 60–100 cm = 0 puan. (→ Mekanik hedefi: ≤60 cm.)
**Ödül şartı:** Aşama-3'ten **en az 10 puan.** (Alınmazsa genel sıralamada ilk 3 bile olsa ödül yok.)

### Aşama 1 — Farklı Menzillerde Duran Hedef İmhası (MANUEL)
- Hedefler sabit, 5/10/15 m. Aynı hedef seti tüm menzillerde.
- Puan: Yakın **5** / Orta **10** / Uzak **20**. Max 80 + **Bonus Süre <20** (`BSP = 20 × kalan_sn/300`).
- Zarftan gelen **SIRAYLA** vurulmalı. Yanlış sıradaki hedef = **−5 ceza.**
- Baraj: **≥30 puan.** Süre: **5 dk.** Ateş emri operatörden (manuel).

### Aşama 2 — Sürü Saldırısı ve İmha (OTONOM)
- 4 tur. Her tur 3 koldan aynı anda **3 hedef** (Balistik Füze + Mini/Micro İHA) yaklaşır,
  A→B hareket eder. Tur bitince imha edilen yerine yenisi konur.
- **Tip sınıflandırması YOK — hedefler düşman, hepsi vurulur.**
- Puan: tur başına 1/2/3 hedef = **5/15/30.** Max 120. Ceza: tur başına vuramama −5.
- Baraj: **≥20 puan.** **3 tur üst üste hiç vuramama = 0 (elenme).**

### Aşama 3 — Farklı Katmanlardaki Hareketli Hedeflerin İmhası (OTONOM)
- 8 tur. Her tur **1 düşman + 2 dost** yaklaşır. Düşmanı tespit + **tipe göre uygun menzilde** imha.
- Puan: F16 **30**, Heli/Füze **20**, İHA **10.** Max 160.
- Ceza: **dost vurmak −10, düşmanı vuramamak −10** (tur başına max −10).
- **İmha menzilleri:** F16 **10–15 m**, Heli/Füze **5–15 m**, İHA **0–15 m**.
  (Bu menzillerden yakın imha puana SAYILMAZ.)
- Baraj: **≥10 puan.** **3 ardışık tur düşman vuramama = 0.**

### ⭐ KRİTİK STRATEJİK İÇGÖRÜ — "10–15 m ortak imha bandı"
Tüm hedefleri **10–15 m** bandında vurmak her tip için geçerli aralığa düşer
(10–15 ⊂ F16[10-15], Heli/Füze[5-15], İHA[0-15]). Bu sayede mesafe ölçümü
**"hedef 10–15 m bandında mı?"** basit kontrolüne iner → pahalı/çok hassas derinlik
zorunluluğunu kaldırır. Tek kamera + bilinen boyut bu bandı doğrulamaya yeter.

---

## 5. Sistem mimarisi (KTR temelli — araç sıfırdan yapıldığı için hedef mimari)

**Görüntüden atışa zincir:** Kamera → Laptop (görüntü işleme + karar) → UART → ESP32
(motor + lazer kontrol) → 2 eksen gimbal + lazer.

- **İşlemci:** Laptop (yarışmaya laptopla gidilecek). KTR: HP Victus, i5-12500H, RTX 3060.
- **Kamera:** KTR'de OAK-D-Pro (stereo). *(Açık karar — bkz. §8; bugün "tek kamera" dendi.)*
- **Aktüatör:** Her eksende 1× NEMA23 kapalı çevrim step (yaw 360°, pitch min 60°), STEP/DIR.
  ESP32'ye bağlı **iki motor**: pan = YATAY eksen (STEP 6/DIR 7, ENABLE 16, **15→83 diş
  redüksiyon**), tilt = DİKEY eksen (STEP 4/DIR 5, ENABLE 17). **Acil stop butonu = GPIO 15**
  (NO, basılı=LOW); **lazer = GPIO 18 (PWM)**. Firmware AccelStepper, sürücüler **6400 step/tur**.
- **Kontrolcü:** ESP32, UART **115200 baud**, PySerial. Komutlar **ASCII satır**:
  `P<derece>` `T<derece>` `S<der/sn>` `A<der/sn²>` `G<%>` `L1/L0` `STOP` `START` — açı **MUTLAK**.
  Kart yapısal durum paketi yollamaz, insan-okur metin yazar. **Hız düzeyi 3 kademe** → §5.1.
- **İş bölümü:** laptop yalnızca *mutlak hedef açı + hız düzeyi + komut* söyler; mikroadım,
  dişli oranı, rampa (ivmelenme) ve homing ESP32'de kalır. Laptop step saymaz.
- **İmha:** LaserTree 80W-AA-PRO lazer (24V, PWM tetik). Odak merceği 5–15 m için kalibre.
  **[KESİN] Tam güçle çalışmıyoruz — varsayılan %40** (takım kararı 06.08); güç `G<yüzde>`
  komutuyla ayarlanır, `L1/L0` ateşi açıp keser. Ayrıntı ve dwell etkisi → §5.3.
- **Güç:** Mean Well LRS-350-24 (24V). Buck → 5V (kamera+ESP32). E-Stop + şalter + sigorta.
- **Kontrol algoritması:** PD kontrol (piksel hatası → yaw/pitch); homing için limit switch.
- **Manuel kontrol:** USB gamepad (Aşama 1).
- **Otonom mod modelleri:** tespit YOLOv11 + takip (KTR: Macar/Hungarian ID eşleme + öngörülü kestirim).

**Güvenlik (şartname zorunlu):** harekete-yasak alan + atışa-yasak alan tanımı; sadece hedef
tarafına bakabilme; donanımsal E-Stop + yazılımsal E-Stop; homing ile bilinen başlangıç.

### 5.1 ESP32 iletişim katmanı ve MOTOR HIZ DÜZEYİ (05.08.2026)

**[KESİN] Protokol, ESP32'de GERÇEKTEN ÇALIŞAN koda göre belirlendi.** Ekipten gelen firmware
(AccelStepper) ASCII satır komutları konuşuyordu; kısa süre binary/delta bir protokol yazılmıştı
ama karşılığı yoktu → **atıldı.** Bugün tek kaynak `app/protokol.py` + `esp32/derin_mavi_esp32/derin_mavi_esp32.ino`.

| Konu | Karar |
|---|---|
| Komut biçimi | ASCII satır, `\n` ile biter: `P<derece>` `T<derece>` `S<der/sn>` `A<der/sn²>` `L1`/`L0` `STOP` `START`. |
| Açı semantiği | **MUTLAK** (`moveTo`), delta DEĞİL. Kaybolan komut kalıcı sapma yaratmaz; ateş komutu süregelen hareketi bozmaz. Ekrandaki açı ile kartın hedefi tek kaynaktan türer → **kopma yapısal olarak imkânsız** (§13.1'deki hata sınıfı ortadan kalktı). |
| Azimut sarması | Ekranda 0–360, **karta sürekli (birikimli) açı gider**: 350°→10° geçişinde `P370`. Yoksa motor kısa yoldan değil 340° geri döner. |
| **Mekanik [KESİN]** | Sürücü çözünürlüğü **6400 step/tur** (1/32 mikroadım). **Yatay eksende 15→83 diş = 5.533:1 redüksiyon** → **98.37 step/derece.** Dikey eksen: redüksiyon **[VARSAYIM] 1:1** → 17.78 step/derece (⚠ ölçülüp doğrulanmalı; yanlışsa tilt açıları yanlış olur). |
| Hız birimi neden derece/sn | İki eksenin dişli oranı farklı → aynı step/sn iki eksende bambaşka açı hızı demek olurdu. Laptop her yerde **derece** konuşur (P/T de derece); step'e çevirmek kartın işi. Dişli/mikroadım değişirse yalnız firmware sabiti değişir. |
| Hız düzeyleri | **3 kademe (derece/sn, derece/sn²):** Yavaş `S15/A40` · Normal `S40/A100` · Hızlı `S75/A200`. |
| Tavanı ne belirledi | **Darboğaz pan ekseni:** 98.37 step/derece → 75°/s bile ~7380 step/sn. AccelStepper adımları yazılımla ürettiği için ESP32'de güvenli üst sınır ≈ **8000 step/sn** (`MAKS_STEP_SN`); tablo bunun altında kalacak şekilde seçildi ve test bunu doğruluyor. |
| İvme neden birlikte | Step motor yüksek tavan hıza düşük ivmeyle çıkamaz; düşük hızda yüksek ivme adım kaçırır. Kademe = (hız, ivme) çifti. |
| Geri bildirim | Kart **yapısal durum paketi yollamıyor**, insan-okur metin yazıyor. Bu yüzden arayüzdeki açı **"hedef"** diye yazılır — ölçüm gibi göstermek en yanıltıcı hata olurdu (mesafe özelliğinde bir kez yaşandı). |
| Arayüz | Sağ kolonda **MOTOR HIZI** kartı; sağ panel stack'inin DIŞINDA → hem Manuel hem Otonom modda görünür. Adım butonları (1°/5°/10°) `Hassas/Orta/Geniş` oldu: adım "ne kadar", hız "ne kadar çabuk". |
| **Basılı tutma** (05.08) | Tek dokunuş = seçili adım (1/5/10°). Tuş 300 ms'den uzun basılı kalırsa 50 ms'de bir **sürekli hareket**. Tik başına açı = **kademenin derece/sn'si × geçen süre** — sabit adım gönderilseydi (50 ms'de 5° = 100°/s) hedef motorun önüne geçer, tuş bırakılınca gimbal yetişmek için dönmeye devam ederdi. Qt'nin kendi auto-repeat'i kullanılmaz: hızını işletim sistemi belirlerdi ve iki tuş aynı anda basılıyken çapraz hareket çalışmazdı. **Odak kaybında** (Alt+Tab) tekrar kesilir — tuş bırakma olayı gelmeyebilir ve gimbal sonsuza dek dönerdi. |

**Firmware'e eklenenler** (`esp32/derin_mavi_esp32/derin_mavi_esp32.ino`, ekipten gelen kodun üstüne):
1. **Lazer (`L1`/`L0`)** — pin **15**; imha unsuru koda hiç girmemişti.
2. **`STOP` artık lazeri de keser** — E-Stop'un ilk işi ateşi kesmektir; motor kilitlemek yetmez.
3. **`S` komutu (tavan hız)** — eskiden yalnız ivme (`A`) değişebiliyordu, hız sabitti;
   3 kademeli hız düzeyi bu komut olmadan mümkün değil.
4. **Tilt yazılımsal limiti (0–90°)** — seri monitörden elle `T500` yazan biri mekaniği kırmasın.
   Arayüz de kırpar; **tek tarafa güvenilmez.**
   **07.08 düzeltmesi:** tavan **60° → 90°**. Ayrıca bir tutarsızlık giderildi: arayüzdeki
   "Maksimum Yükseliş" kaydırıcısı zaten 90'a kadar gidiyordu ama `protokol.TILT_MAX` 60'ta
   kırpıyordu — kaydırıcı 90'a çekilse bile gimbal **60'ta takılı kalıyor**, operatör sebebini
   göremiyordu. Kaydırıcının tavanı, yasak-alan kutuları ve "Varsayılan" düğmesi artık
   `protokol.TILT_MAX`'tan türer (tek kaynak). Gerçek kartta doğrulandı: `T85`/`T90` geçiyor,
   `T120` → 90'a, `T-10` → 0'a kırpılıyor.
5. **DONANIMSAL ACİL STOP BUTONU (05.08 akşam):** **[KESİN] GPIO 15**, NO (normalde açık),
   GND'ye çeker → dahili pull-up ile **basılı = LOW**. Giriş her döngüde okunur (30 ms sıçrama
   filtresi). Basılınca `acilDurdur()` çalışır: **önce lazer, sonra hareket, sonra sürücü
   ENABLE hatları (pin 16/17) kesilir.** Sıra kasıtlı — ateş her şeyden önce durur.
   - **Buton bırakılınca sistem KENDİLİĞİNDEN BAŞLAMAZ.** Operatör arayüzden DEVAM ET demeli;
     acil durdurmadan çıkış her zaman bilinçli bir eylem olmalıdır.
   - **Buton basılıyken `START` REDDEDİLİR.** Yazılımdan geçilebilen bir E-Stop, E-Stop değildir.
     Kart reddederken metninde "SISTEM DURDURULDU" geçirir → laptop tarafı da E-Stop'ta kalır.
   - Açılışta buton zaten basılıysa kart hemen durur (reset sonrası kaçak hareket olmaz).
6. **[KESİN — 07.08'DE DEĞİŞTİ] E-Stop'ta motorlar TUTAR; ENABLE ASLA kesilmez.**

   **Sahada ne oldu:** acil durdurmadan çıkınca gimbal **aniden fırlıyordu.** Sebep
   yazılım değildi — kapalı çevrim (closed-loop) sürücünün kendi servo döngüsüydü:
   ENABLE kesilince rotor serbest kalıyor, mil kayıyor (dikey eksen yer çekimiyle
   düşüyor), sürücünün **encoder'ı bu kaymayı izlemeye devam ediyor**; ENABLE geri
   verildiğinde biriken pozisyon hatasını **kendi maksimum hızıyla** kapatıyor. Bu
   hareketi ESP32 üretmiyor (`distanceToGo()` sıfır), dolayısıyla hız kademesi de
   sınırlamıyor. Fırlamanın olması, `ENA_AKTIF_LOW = true` varsayımının **doğru**
   olduğunu ve ENABLE hattının sürücüye gerçekten bağlı olduğunu da kanıtladı.

   **Yeni davranış (takım kararı):**
   | | |
   |---|---|
   | ENABLE | `setup()`'ta bir kez enerjilenir, **bir daha dokunulmaz.** `setDrivers(false)` diye bir yol yok; fonksiyon `enableAc()` olarak sadeleşti. |
   | Lazer | İlk iş olarak kesilir (sıra değişmedi). |
   | Pan | **Olduğu yerde kilitlenir** (`moveTo(currentPosition())`), acil durdurma boyunca hiç hareket etmez. |
   | Tilt | **0° park konumuna iner** — lazerli namlu yukarıda asılı kalmasın diye bilinçli bir harekettir. Bu yüzden E-Stop'ta `tiltMotor.run()` çağrılmaya devam eder; `panMotor.run()` çağrılmaz. |
   | Komutlar | `systemActive = false` → P/T/L/S/A hepsi reddedilir. Mümkün olan **tek hareket** tilt'in park etmesidir. |
   | **Sıfır kabulü** | **KALDIRILDI.** Motorlar tuttuğu için mil kaymaz, referans geçerli kalır. Sıfırlama ENABLE'ın kesildiği eski tasarımın zorunlu telafisiydi; artık her acil durdurmada mutlak açıları kaydırmak demek olurdu. **Bedeli de bitti: E-Stop artık açı referansını bozmuyor.** |

   Laptop tarafı da aynı şeyi söyler: `kontrol.estop(True)` yalnız `tilt_hedef`'i sıfırlar
   (pan korunur), arayüzde `_sifir_kabul` → **`_estop_park`** oldu.

   ✅ **Gerçek kartta doğrulandı:** `P60`+`T40` → `STOP` → *"Pan kilitli, tilt 0 derece park
   konumuna iniyor"* → `P200`/`T50` **reddedildi** → `START` → *"Referans korundu
   (P60.00 / T0.00)"*. Kapı testleri: `test_estopta_enable_kesilmez`,
   `test_estopta_pan_kilitli_tilt_park_eder`, `test_devam_edince_referans_korunur`
   (eski davranışa dönülünce kırmızıya düştüğü doğrulandı).

   ⚠ **[VARSAYIM] Şartname riski:** Yetenek 3 *"hareket ederken E-Stop → sistem durur"*
   diyor; tilt'in park konumuna inmesi bir **harekettir** ve videoda "durmadı" gibi
   yorumlanabilir. Çekimde bunu sözle açıklamak (güvenli park duruşu) ya da park özelliğini
   video için kapatmak değerlendirilmeli.

   *Aşağıdaki eski madde tarihsel kayıttır, artık uygulanmaz:*
   ~~**E-Stop'ta motorlar TUTMAZ, BIRAKIR + HER İKİ GEÇİŞTE SIFIR KABULÜ**~~ (takım kararı):
   ENABLE kesilince tutma torku gider, dikey eksen yer çekimiyle düşer. Kart mevcut konumu
   **hem durdurma anında (`acilDurdur`) hem de `START`'ta** sıfır kabul eder
   (`setCurrentPosition(0)`), tilt zaten yalnız yukarı gidebildiği için (taban 0°) bu güvenli
   taraftır: düşmüş namlu "en alt = 0°" referansıyla çalışmaya başlar. **Laptop tarafı da aynı
   anda sıfırlanır** (`kontrol.estop()` + arayüzde `_sifir_kabul()`, iki geçişte de); iki taraf
   aynı sıfırı görmezse ekrandaki açı kartın hedefinden kopar. Otonom PD kontrolcüsünün türev
   geçmişi de burada sıfırlanır (duraklama öncesi birikmiş hata, devam edince sıçrama olmasın).

   **Düzeltme 06.08 — neden iki kez sıfırlanıyor:** `acilDurdur()` eskiden
   `moveTo(currentPosition())` yapıyordu; bu motoru durdurur ama **adım sayacı eski değerinde
   kalırdı.** ENABLE kesilip mil kaydığında (dikey eksen düşer) sayaç ile gerçek konum arasındaki
   fark DEVAM'a kadar açık kalıyor, arada gelen her komut o kaymış referansa göre hesaplanıyordu.
   `setCurrentPosition(0)` üç işi birden yapar: `_targetPos = _currentPos = 0` (→ `distanceToGo()`
   sıfır, **sürücüye tek pulse gitmez**) ve `_speed = _stepInterval = 0` (birikmiş rampa silinir).
   START'taki sıfırlama yine de duruyor: E-Stop ile DEVAM arasında motorlar serbesttir, mil o
   süre boyunca kaymaya devam edebilir — geçerli sıfır, **sistemin yeniden enerjilendiği andaki**
   konumdur. Kapı testi: `test_estopta_referans_hemen_sifirlanir` (eski davranışa dönülünce
   kırmızıya düştüğü doğrulandı).

   ⚠ Bunun bedeli: **her E-Stop açı referansını kaydırır.** Gerçek (limit switch'li) homing
   gelene kadar E-Stop sonrası mutlak açılar fiziksel gerçekle birebir örtüşmez.

   ⚠ **Kapalı çevrim sürücüde bu yetmeyebilir [VARSAYIM].** NEMA23 kapalı çevrim sürücüler
   kendi encoder'larını izler; ENABLE geri verildiğinde bazıları biriken konum hatasını
   **kendiliğinden telafi eder** — yani ESP32 hiç pulse göndermese bile motor "kaçırdığı" açıyı
   geri alır. Böyle bir sıçrama görülürse sebep firmware değil sürücü ayarıdır (konum hatası
   temizleme / alarm reset ayarı) — sürücü kılavuzundan kapatılmalı.

**⚠ Donanım uyarıları (ekip doğrulamalı):**
- **Buton NO seçilmiş — bunun bir zaafı var:** kablo koparsa hat pull-up ile HIGH kalır ve
  buton "basılmamış" görünür, yani **arıza E-Stop'u sessizce devre dışı bırakır.** NC
  (normalde kapalı) buton kopmada da durdurur. Yarışma öncesi NC'ye geçilmesi önerilir
  (firmware'de tek sabit: `ESTOP_AKTIF_LOW = false`).
- **[KESİN] Lazer tetiği GPIO 18 — 25 DEĞİL.** (Düzeltme 06.08: `SOC_GPIO_VALID_GPIO_MASK`
  ile doğrulandı, **ESP32-S3'te GPIO 22/23/24/25 fiziksel olarak yoktur**; klasik ESP32'de
  vardılar. 25'e yazmak sessizce hiçbir şey yapıyordu, derleme de uyarmıyordu.) Diğer pin
  güvenliği: kart S3 olduğu için önceki "GPIO 15 strapping" ve "GPIO 16/17 PSRAM" uyarıları
  **geçersiz kaldı** — kullandığımız pinlerin tamamı S3'te serbest ve strapping dışı (§5.2).
- **ENABLE polaritesi kesin değil.** Ölçülen tek şey: hatlara hiçbir şey bağlı değilken
  motorlar çalışıyor — bu iki yaygın sürücü ailesinde de böyledir, polariteyi belirlemez.
  Firmware'de yaygın olan (LOW = enerjili) yazılı; E-Stop'ta motorlar serbest kalmıyorsa
  `ENA_AKTIF_LOW = false`. **Yanlış polarite hareketi durdurmayı engellemez** —
  `systemActive=false` olunca `run()` hiç çağrılmaz; ENABLE ikinci güvenlik katmanıdır.
- **[VARSAYIM → düzeltilecek] Dikey eksende de redüksiyon VAR ama oranı ölçülmedi.** Şimdilik
  1:1 (ekip bildirecek). O gelene kadar tilt açıları gerçek açı değildir: "60°" komutu
  gerçekte 60/oran kadar döndürür. Değişecek iki yer: `protokol.TILT_DISLI` ve firmware
  `TILT_GEAR_RATIO`.

**Python tarafındaki sağlamlaştırma:**
- Kart metinleri 250 ms'de bir **okunur** (gönderim değil, okuma yoklaması): okunmazsa hem seri
  tampon dolar hem de kartın kendi başına durmasından haberimiz olmaz. `"SISTEM DURDURULDU"`
  satırı görülünce arayüz **ateşi bırakır** (seri monitörden STOP, ileride donanımsal E-Stop).
- Değişmeyen eksene komut gönderilmez; hatta gereksiz trafik dolaşmaz.
- Alt çubuktaki **Lazer** göstergesi canlandı (şimdiye kadar hiç güncellenmiyordu).

### 5.2 [KESİN] Kart ESP32-**S3** — kurulum ve uçtan uca doğrulama (05.08.2026)

Kart esptool ile tespit edildi: **ESP32-S3** (QFN56 rev v0.2, 8 MB PSRAM, MAC 30:30:f9:13:92:24),
laptopa **CH343** USB-seri çipi üzerinden **COM7**'den bağlı. Klasik ESP32 değil — farkı önemli:

| Konu | Sonuç |
|---|---|
| Arduino kartı | **ESP32S3 Dev Module** (`esp32:esp32:esp32s3`). `esp32:esp32:esp32` ile yüklenmez. |
| Strapping pinleri | S3'te **GPIO 0, 3, 45, 46**. Kullandığımız pinlerin hiçbiri bunlarda değil → **GPIO 15 strapping uyarısı S3'te GEÇERSİZ** (o klasik ESP32 içindi). Buton basılıyken reset boot'u etkilemez; lazer pini açılışta kaçak tetiklenmez. |
| **OLMAYAN pinler** ⚠ | **S3'te GPIO 22/23/24/25 YOKTUR** (`soc_caps.h`: `SOC_GPIO_VALID_GPIO_MASK` bu dördünü maskeden çıkarır). Klasik ESP32'de vardılar. Bu numaralara yazmak **sessizce hiçbir şey yapar; derleme hata vermez.** Lazer bu yüzden 25→**18**'e alındı (06.08). |
| Ayrılmış pinler | S3'te GPIO **26–32** dahili SPI flash, oktal PSRAM'de **33–37** de PSRAM; **43/44** = UART0 (CH343 → laptop), **19/20** = USB D-/D+. Kullandığımız 4/5/6/7/15/16/17/18 tamamen bu bölgelerin dışında ✓ |
| USB CDC On Boot | **KAPALI kalmalı** (varsayılan). Kart harici CH343 (UART0) üzerinden konuşuyor; açılırsa `Serial` USB'ye gider ve laptop hiçbir şey duymaz. |

**Ortam:** Arduino IDE 2.x + esp32 core **3.3.11** + AccelStepper **1.64.0**. Firmware
**uyarısız derleniyor** (`--warnings all`): 324 KB flash (%24), 22 KB RAM (%6). Adımlar README'de.
Sketch, Arduino kuralı gereği kendi adıyla aynı klasörde:
`esp32/derin_mavi_esp32/derin_mavi_esp32.ino`.

**Firmware'e eklenen:** `Serial.setTimeout(20)` — varsayılan 1 sn'lik `readStringUntil`
bloklaması, parçalı gelen bir komutta `loop()`'u durdurup `AccelStepper.run()` çağrılmadığı
için adım kaçırtırdı.

**✅ GERÇEK DONANIMDA DOĞRULANDI (yüklendi + `DERINMAVI_ESP=COM7` ile konuşuldu):**
açılış banner'ı okundu · `S15/A40` hız kademesi kabul edildi ve yankılandı · `STOP` →
*"SISTEM DURDURULDU"* → kontrol katmanı satırı tanıyıp `estop_aktif=True` yaptı · `START` →
*"Mevcut konum SIFIR kabul edildi (P0.00 / T0.00)"* → hedefler sıfırlandı. Yani protokol,
komut üretimi, satır okuma ve E-Stop tanıma zinciri **mock'ta değil, kartta** çalışıyor.
⏳ Henüz denenmeyen: **motor hareketi (P/T komutları)** ve lazer tetiği.

⏳ **Bekleyen:** gerçek portta uçtan uca deneme (`DERINMAVI_ESP=COM<n>`), **dikey eksenin dişli
oranı** (şu an 1:1), **sürücü ENABLE polaritesinin doğrulanması** (`ENA_AKTIF_LOW`), hız
kademelerinin gerçek mekanikte doğrulanması (adım kaçırma sınırı ölçülüp `HIZ_TABLO`
düzeltilecek), limit switch **homing** (kartta yok — `home()` şimdilik yalnızca "0°'a dön" demek;
homing gelince E-Stop sonrası açı kayması da biter), kartın konum geri bildirimi (gelirse
ekrandaki açı "hedef" değil "ölçüm" olur), NO → **NC butona geçiş** (kablo kopmasına karşı).

### 5.3 LAZER GÜCÜ — PWM ve %40 kararı (06.08.2026)

Takım kararı: **lazer tam güçle çalıştırılmayacak, varsayılan %40.** Eskiden lazer pini
`digitalWrite` ile açılıp kapanıyordu (sadece 0/tam güç); artık **PWM** sürülüyor.

| Konu | Karar |
|---|---|
| Sinyal | **GPIO 18**, LEDC PWM · 1 kHz · 8 bit (`ledcAttach/ledcWrite`). Duty oranı = güç oranı. ⚠ Pin 25'ten taşındı: S3'te 22–25 yok (§5.2). `ledcAttach`'ın dönüşü artık kontrol ediliyor, kurulamazsa açılış banner'ı bağırıyor. |
| Komut ayrımı | **`G<yüzde>` = "ne kadar"** (kalıcı ayar), **`L1/L0` = "ne zaman"**. Hız tarafındaki `S/A` ile `P/T` ayrımının aynısı. |
| Neden `L<yüzde>` değil | `L1` bugün "aç" demek; L'ye yüzde yüklenseydi mevcut her çağrı sessizce **%1 güce** düşerdi — kod çalışır görünür, lazer yanmazdı. En sinsi kırılma türü. |
| %100'de duty | 255 değil **256** yazılır: 8 bit'te 255 hâlâ kısa bir LOW darbesi bırakır, 256 pini sürekli HIGH yapar. |
| E-Stop | `setLaser(false)` → **duty 0** (pin sürekli LOW). Güç ayarı kalıcıdır, ateş kesilir — E-Stop sırası değişmedi: önce lazer, sonra hareket, sonra ENABLE. |
| Açılış | Kart açılışta duty 0; laptop bağlanınca hız düzeyiyle birlikte `G40` gönderir (kart kendi varsayılanında kalmasın). |
| **ATEŞ butonu** (06.08) | **AKTİF HEDEF kartı kaldırıldı** — gösterdiği her şey zaten üst şeritte vardı (`eng_name`/`eng_sub`); boşalan yer manuel yön kontrollerine verildi (D-pad tuşları 68×54 → 86×68 px). ATEŞ butonu **manuel panelin altına** taşındı ve büyütüldü. Klavyeden **`L`** de ateşi açıp kesiyor: `_ates_kisayolu` → `_ates_bas` (tek kapı korunuyor). `L` **her modda** çalışır — buton Otonom'da görünmez ama lazeri kesme yolu moda bağlı olmamalı. Kısayolun butondan **fazla yetkisi yok**: E-Stop'ta buton kilitliyse `L` de geçmez (yoksa E-Stop klavyeden aşılabilirdi). Kapı testi: `test_l_kisayolu_ates_kapisindan_gecer`. |
| **Arayüz** (06.08) | Sağ kolonda **LAZER kartı**: güç kaydırıcısı (%0–100) + hızlı kademeler (%20/%40/%70/%100) + başlıkta anlık durum (`● ATEŞ · %40` / `○ Kapalı · %40`). MOTOR HIZI gibi **stack'in dışında** → hem Manuel hem Otonom modda görünür. Güç değişiminin tek kapısı `_lazer_guc_degisti`. Güç **kalıcı olarak kaydedilmez**: her açılış güvenli varsayılana (%40) döner — "geçen sefer %100'de bırakmışız" diye başlamak istemeyiz. |

**ATEŞİN ÜÇ KATMANI (06.08 — "bir anda lazer çalışırsa" endişesine karşı).** Lazer çok
güçlü; tek kapı yetmez, birbirinden bağımsız katman gerekir:

1. **Boot koruması.** `setup()`'ın **ilk iki satırı** lazer pinini LOW'a çeker (`Serial.begin`'den
   bile önce). Ama reset anında ROM bootloader boyunca pin **float** kalır ve buna yazılım
   müdahale edemez → **tek gerçek çözüm donanımsal: 10 kΩ pull-down (GPIO 18 ↔ GND).**
   Yükleme yaparken lazer beslemesi kapalı tutulur.
2. **Tek kapı, arayüzde.** Ateşin tek yolu `_ates_bas` (ATEŞ butonu). Kesme yolu da tek:
   `_ates_kes` — E-Stop, atışa-yasak alan, kartın kendi durması hepsi oradan geçer. Kart
   tarafında `L` komutu `systemActive` bloğunun içinde: **E-Stop'ta ateş komutu işlenmez.**
3. **⭐ ÖLÜ ADAM ANAHTARI (yeni).** Lazer açık kalmak için karta **250 ms'de bir `L1`
   tazelemesi** gitmelidir (`_esp_yokla`). **1 sn** tazeleme gelmezse kart lazeri **kendi
   keser.** Sebep: "kes" komutunun gitmesine bel bağlanamaz — kesmenin gerektiği durumların
   çoğunda (seri kablo koptu, laptop çöktü, arayüz dondu, USB çıktı) komut zaten gidemiyordur.
   "Açık kal" demeyi sürdürmek, "kapan" demeyi beklemekten güvenlidir.
   Sabitler tek kaynakta: `protokol.ATES_TAZELE_MS` / `ATES_ZAMAN_ASIMI_MS` (firmware ile aynı);
   `protokol.py` testi `tazele × 2 ≤ zaman_aşımı` değişmezini korur — aksi halde kaçan birkaç
   tazeleme ateşi ortasında lazeri söndürür ve dwell bozulur.

   İki kapı testi bunu koruyor: `test_ates_tazelemesi_kesilirse_lazer_soner` ve
   `test_ates_kapaliyken_tazeleme_gitmez` (kapalı lazeri kazara açan bir `L1` dolaşmasın).
   Tazeleme kodu kaldırılınca testin **gerçekten kırmızıya düştüğü doğrulandı.**

**✅ KARTTA DOĞRULANDI (06.08, yüklendi + COM7'den konuşuldu):** açılış banner'ı
*"Lazer: GPIO 18 PWM 1000 Hz, guc %40"* yazdı ve **`ledcAttach` hata satırı ÇIKMADI** —
yani PWM kanalı gerçekten kuruldu, GPIO 18 bu kartta geçerli. `G40` → `LAZER ACIK (%40)`,
`G100` → `LAZER ACIK (%100)`, `L0` → `LAZER KAPALI`. Ölü adam anahtarı da çalıştı: tazeleme
sürerken lazer açık kaldı, kesilince kart kendi kapattı.
⏳ **Henüz bilinmiyor: lazerin fiziksel olarak tetiklenip tetiklenmediği** — GPIO 18'de
gerilim ölçülemedi (multimetre yok), lazer beslemesi kapalıydı. Sıradaki test: kademeli
güç (G10 → G40 → G100) ile gerçek tetikleme.

**⚠ Doğrulanmamış üç nokta (donanımda denenmedi):**
1. **PWM frekansı [VARSAYIM] 1 kHz.** CNC lazer sürücülerinin tipik değeri (GRBL varsayılanı
   da bu). Modül tepki vermezse **önce bunu** değiştirin: 200 Hz / 5 kHz / 20 kHz. Yanlış
   frekansta sürücü sinyali hiç görmeyebilir veya titreşim yapar.
2. **Mantık seviyesi.** ESP32 çıkışı **3.3 V**; LaserTree'nin TTL girişi çoğunlukla **5 V**
   bekler. Bazı kartlar 3.3 V'u HIGH sayar, bazıları saymaz — saymıyorsa level shifter veya
   küçük bir N-MOSFET gerekir. Bu **kodla çözülmez.**
3. **Boot anında GPIO 18 kısa süre yüksek empedansta (float) kalır.** GPIO 18 S3'te strapping
   değil, ama lazer sürücüsünün PWM girişi dahili pull-down'lı değilse **reset/yükleme anında
   kaçak tetiklenebilir.** Önlem: sinyal hattına **10 kΩ pull-down** (GPIO 18 ↔ GND). Yükleme
   yaparken lazer beslemesi kapalı tutulmalı.

**⚠ PUANA ETKİSİ (körü körüne uymuyoruz — kayıt için):** %40 duty ≈ %40 ortalama optik güç,
yani balonun patlaması **~2.5 kat uzun sürer.** Bu doğrudan **dwell süresi** demek ve dwell
Aşama 2–3'ün asıl zorluğu (§7). Süre puana bağlı: Aşama 1'de bonus (`BSP = 20 × kalan_sn/300`),
Aşama 2–3'te tur süreleri. **Yapılacak ölçüm:** balonun 5/10/15 m'de %40 ve %100'de patlama
süresi. %40 patlatamıyor ya da dwell'i tur süresini riske atacak kadar uzatıyorsa değer
yükseltilir — tek satır (`protokol.LAZER_GUC_VARSAYILAN`), kod değişmez.

### 5.4 USB GAMEPAD (07.08.2026) — manuel kontrolün üçüncü girdisi

Şartname **Yetenek 1** kullanıcı komut arayüzlerini *"UI/joystick/klavye"* diye sayar →
gamepad videoda gösterilecek, doğrudan puan. `app/gamepad.py` + arayüzde 50 ms'lik yoklama.

| Konu | Karar |
|---|---|
| Kütüphane | **pygame** (SDL). Hem XInput hem DirectInput padleri okur. `requirements.txt`'te. |
| **Tek kapı kuralı** | Gamepad **kendi komut yolunu AÇMAZ**: hareket `_aci_hareket`, ateş `_ates_kisayolu`→`_ates_bas`, merkez `_aci_reset`, E-Stop `_estop_bas`. Geçmişte ikinci bir ateş yolu E-Stop denetimini atlamıştı (§12 B1) — aynı hata sınıfı geri gelmesin. |
| **Buton haritası** | **SDL GameController API** tercih edilir: SDL'in cihaz veritabanı her padi standart düzene eşler, *A tuşu hangi padde olursa olsun A'dır*. SDL cihazı tanımazsa ham Joystick'e düşülür (XInput numaraları varsayılır). |
| Neden bu kadar önemli | Ham numaralar padden pade **değişir**: Xbox/XInput'ta `7 = Start`, PlayStation DualSense'te `7 = R2`. Sabit numara yazılsaydı **ACİL DURDUR başka bir pad takıldığında yanlış tuşa düşerdi.** |
| Düzen | Sol çubuk + D-pad = gimbal · **A** = ateş (aç/kes) · **Y** = merkeze al · **LB/RB** = motor hız kademesi · **Start** = ACİL DURDUR / DEVAM |
| Hareket matematiği | Adım = `tavan hız (°/s) × geçen süre × çubuk sapması` — basılı tutmayla (§5.1) aynı mantık, tek farkı analog çarpan. Sabit adım gönderilseydi hedef motorun önüne geçer, çubuk bırakılınca gimbal dönmeye devam ederdi. |
| Ölü bölge | %15, ve **kalan aralık yeniden 0..1'e yayılır**. Düz kesme yapılsaydı çubuk eşiği geçtiği anda hız 0'dan 0.15'e sıçrardı. Ölü bölge olmasaydı gimbal hiç durmaz, sürüklenirdi. |
| Kenar tetikleme | Ateş/E-Stop butonları **basıldığı an** okunur. Seviye okunsaydı düğme basılı tutuldukça her 50 ms'de tekrar tetiklenir, lazer yanıp sönerdi. |
| Sıcak takma | Cihaz yokken ~2 sn'de bir taranır; uygulama açıkken pad takılabilir (yarışma günü kablo çıkar/takılır). Kopma da yakalanır, arayüz kilitlenmez. |
| Yokluğu | pygame kurulu değilse **veya** pad takılı değilse özellik sessizce kapalı, uygulama normal açılır (ilke 7). Alt çubukta "Gamepad · yok". |

**Teşhis:** `python app/gamepad.py` — hangi yolun kullanıldığını (standart/ham), çubuk
değerlerini ve basılan düğmeleri canlı gösterir. Ham yolda yanlış tuşa düşerse `BTN_*`
numaraları oradaki çıktıya bakılarak düzeltilir.

⚠ **Bu makinede test notu:** ilk denemede görülen *"Controller (Gamepad F310)"* gerçek bir
cihaz değil, **ViGEmBus** (`Nefarius Virtual Gamepad Emulation Bus`) üzerinden emüle edilen
sanal bir XInput padiydi. Takımın fiziksel cihazı Bluetooth **DualSense**. Gamepad bağlıyken
uçtan uca deneme **henüz yapılmadı**; kod cihazsız (sahte pad) test edildi.

---

## 6. Mevcut yazılım ve KRİTİK BOŞLUKLAR (yapılacaklar)

> **GÜNCEL DURUM (24.07.2026 — GitHub temizliği · 08.08 model kararıyla güncellendi):** Proje
> GitHub'a **public repo** olarak hazırlandı. Ağır/gizli her şey
> `d:\Masaüstü\Derin Mavi - YEDEK\`'e taşındı: `sentetik_veri/` (dataset+model+eğitim scriptleri),
> `Analiz/` (Şartname/KTR/parkur PDF — GİZLİ), `Modeller_Kil6t/` (3mf), `Arayuz_legacy/` (Flask).
> **Model artık `models/` klasörüne konur** → `arayuz_qt.py` `_model_bul()` otomatik bulur, kod
> değişmez. Model yoksa uygulama açılır, alt çubukta "Model yok" uyarısı çıkar.
>
> **[08.08 DEĞİŞTİ] Repo artık modelsiz GELMİYOR:** `models/best.pt` versiyon kontrolüne
> alındı (18 MB) — ekip klonlayınca aynı ağırlıkla çalışsın diye. Türetilmiş biçimler
> (`.onnx`, `.engine`) hâlâ **girmez**; `.engine` TensorRT çıktısıdır, GPU modeline +
> TensorRT sürümüne + sürücüye bağlıdır, başka makinede **açılmaz**. Veri seti girmemeye
> devam ediyor. ⚠ Repo **public** → modeli buraya koymak onu herkese açar; bu bilinçli
> bir takım kararıdır.

**Var olan (temiz repo):**
- **ARAYÜZ (native, ANA):** `app/arayuz_qt.py` → PySide6 masaüstü kontrol istasyonu.
  Algı çekirdeği `app/algi.py` (kamera + YOLO + renk taraf = TEK KAYNAK). Tarayıcı/Flask
  GEREKTİRMEZ; ileride PyInstaller ile tek `.exe` → her laptopta kurulumsuz. Çalıştır: kökteki `Baslat.bat`.
- **Kontrol iskeleti:** `protokol.py` (UART) + `mock_esp32.py` + `kontrol.py`
  (`DERINMAVI_ESP=mock|COM<n>|off`). ATEŞ/E-Stop zinciri arayüze bağlı, donanımsız test edilebilir.
  05.08'de **2 step motor + lazer + 3 kademe hız düzeyi** için düzenlendi (bkz. §5.1).
- **Model:** `models/best.pt` **repoda** (4 sınıf: DRONE/F16/FUZE/HELIKOPTER — balon yok, §12).
  Klonlayan herkeste hazır gelir. Hızlandırma isteyen `.engine`/openvino'yu kendi makinesinde
  üretir (`yolo export …`) — o çıktılar repoya girmez. Eski Flask arayüzü (`arayuz_app.py`)
  emekli edildi, yedeğe taşındı.
- Ortam: Python 3.10+ (3.14 test), torch **CPU**, PySide6 6.11 (abi3),
  OpenCV Türkçe-yol düzeltmesi (imdecode). Kamera donanım-bağımsız (`DERINMAVI_CAM` env / otomatik tarama).
- **⚠️ TEKNİK TUZAK:** torch/ultralytics `arayuz_qt.py`'de **ANA THREAD'de** import edilir
  (op-registration thread-safe DEĞİL; arka planda import = Qt çizimiyle çakışıp segfault). QThread
  yalnızca hazır `YOLO(path)`'i kullanır. **Modeli asla arka planda import etme.**

**Düzeltilecekler (şartnameye göre — durum 16.07.2026):**
1. ✅ **Dost/düşman artık RENKTEN** — `app/renk_analizi.py` (HSV kırmızı/cyan), `SIDE` kaldırıldı.
   Mimari: YOLO = **tip** tespiti; HSV = taraf. Deterministik, açıklanabilir.
2. ✅ **Sentetik veri renkli** — #F50A0A / #00A3E0 gövdeler (cyan yalnız F16+Heli), beyaz ışık.
3. ✅ **Balon eklendi** — 5. sınıf "balon" (direkte, rastgele renkli); sınıflar artık:
   `['f16','helikopter','drone','fuze','balon']` (nc=5).
4. ⚠️ **Mesafe — DEVRE DIŞI, kodu SİLİNDİ** (karar 18.07, temizlik 30.07): `est_distance`,
   `MENZIL`, `GERCEK_BOYUT`, `FOCAL_PX` ve `mesafe_kalibrasyon.py` **koddan kaldırıldı.**
   Sebep: FOCAL_PX=900 kalibre edilmeden gösterilen sayılar (ör. "12.4 m") gerçek ölçüm gibi
   yanıltıcıydı; özellik kapatıldıktan sonra 12 gün ölü kod olarak durdu. Angajman kararı
   yalnızca TİP + RENK'e dayanıyor. Şartnamenin imha menzil tablosu **§4'te yazılı** —
   özellik geri gelince oradan yeniden yazılır (git geçmişinde de duruyor).
6. ✅ **v2 model eğitildi** (17.07, mAP50 0.995) → **v3 boru hattı kuruldu** (18.07): Roboflow
   1026 gerçek foto + sentetik → `dataset_v3` (2454/382). Bu boru hattı yedeğe alındı
   (`sentetik_veri`), current yaklaşımdan vazgeçildi (bkz. §6 GÜNCEL DURUM).
7. ✅ **Native arayüz iskeleti** (17.07): `arayuz_qt.py` — canlı video + tespit overlay, aktif
   hedef kartı, tespit tablosu, mod (Manuel/Otonom) + aşama seçimi (aşamaya duyarlı, sürüklenebilir
   Aşama-1 kartları dahil), FPS, **çalışan yazılımsal ACİL DURDUR**.
8. ✅ **Kontrol iskeleti kuruldu** (18.07): `protokol.py` (UART paket, XOR checksum) +
   `mock_esp32.py` (sahte cihaz — sınırlı hızda motor sim, ateş, E-Stop) + `kontrol.py`
   (yüksek seviye API, `DERINMAVI_ESP=mock|COM<n>|off`). Arayüze bağlandı: ATEŞ butonu gerçekten
   lazeri açıp/kapatıyor (mock üzerinde), **E-Stop ateşi kesip ATEŞ butonunu kilitliyor** (Yetenek
   3-4 tam davranışı), alt çubukta ESP32/Seri Port canlı durum gösteriyor. Gerçek ESP32 gelince
   `DERINMAVI_ESP=COM5` yeterli — kod değişmez, ESP32 C tarafı bu protokole göre yazılmalı.
   Bekleyen: gimbal sürüş matematiği (piksel hatası→açı), homing, yasak alan mantığı.
9. ✅ **Nişan mantığı yazıldı** (29.07): `app/nisan.py` — hedef↔balon eşleştirme
   (`nisan_noktasi`) + piksel hatası→açı PD kontrol (`PDNisanci`). Otonom modda
   `AlgiThread._nisan_al` → `MainWindow._nisan_geldi` → `kontrol.nisan()` zinciri çalışıyor.
   Bekleyen: dwell (lazeri hedefte tutma) mantığı ve gerçek donanımda Kp/FOV kalibrasyonu.

10. ✅ **ALGI/ARAYÜZ SAĞLAMLAŞTIRMASI** (29.07) — "ham YOLO daha iyi tanıyor" şikâyetinin
   kök sebepleri bulundu ve giderildi. Ayrıntı için bkz. §12.

11. ✅ **`hedeftakip` branch'i `otonom_v4`'e taşındı — SAHI HARİÇ** (13.08) — `hedeftakip`
   branch'inde geliştirilen arayüz/algı iyileştirmeleri (takım kararıyla SAHI dilimli tespit
   **hariç tutularak**) bu branch'e uygulandı. Getirilenler:
   - ~~**ByteTrack → kendi IoU tracker'ımız.**~~ **[13.08 AKŞAM GERİ ALINDI — bkz. §7.2.]**
     Bu maddede `model.track()` yerine `model.predict()` + basit kare-kare IoU eşleştirmesi
     (`_iou_id_esle`) getirilmişti; otonom modda gimbal kendi hareketiyle görüntüyü
     kaydırınca hedef ID'si kararsızlaşıp "rastgele hareket" hatasına yol açtığı bulununca
     **ByteTrack'e geri dönüldü**, `_iou_id_esle` ve yardımcıları tamamen silindi.
     `_tracker_yaml_yaz`/`_TRACKER_YAML` yeniden CANLI yolda kullanılıyor (ölü kod değil).
   - **Kalıcı hedef kilidi (`algi.hedef_sec`/`kilitli_hedef`).** HEDEFLER kartındaki bir isme
     tıklamak o track ID'yi elle kilitler; otomatik kilitle AYNI mekanizma
     (`_kilitli_track_id`), tetikleyici operatör. Aynı hedefe tekrar tıklamak kilidi bırakır.
     İlk otomatik kilit **≥%80 güven** ister; kilit bir kez kurulunca gösterim eşiği o
     hedef için 0'a düşer (kaybolmaz). Hedef geçici olarak tespit edilemezse **hayalet
     hedef** (son bilinen kutu, düşük güvenle) kilidi bir sonraki karede geri gelene kadar
     ekranda tutar — titremeyi önler.
   - **TESPİT EDİLEN HEDEFLER tablosu → HEDEFLER kartı.** `QTableWidget` yerine numaralı,
     tıklanabilir buton listesi (`_hedefler_karti`/`_hedef_liste_guncelle`); sıra daima
     Füze→Helikopter→F16→İHA (`HEDEF_ONCELIK`), tespit sırasından bağımsız. Sağ kolon artık
     `QStackedWidget` değil — Manuel panel yalnızca Manuel modda görünür/gizlenir, HEDEFLER/
     Motor Hızı/Lazer kartları her iki modda sabit.
   - **Lazer boresight/paralaks kalibrasyonu.** Yeni ayarlar `lazer_ofset_x/y` (⚙ panel,
     Nişan sekmesi): kamera ekseni ile lazerin gerçekte vurduğu nokta arasındaki kayma,
     kare boyutunun yüzdesi olarak kalibre edilir. `nisan.PDNisanci` artık kare merkezine
     değil bu kalibre noktaya kilitleniyor. Qt canlı görünümde kırmızı bir referans nişangahı
     (kalibre noktada) + `algi.draw_overlay`'de (cv2 tarafı) yeşil sabit merkez nişangahı
     eklendi.
   - **"Aynala" (flip) ayarı tamamen kaldırıldı.** `cv2.flip` kalıcı olarak kapatıldı (takım
     kararı), `nisan.py`'deki yaw-işareti telafisi de onunla birlikte gitti — flip artık
     hiçbir yerde yok, `algi.AYAR`'da `ayna` anahtarı bulunmuyor.
   - **Tespit kutusu rengi artık SABİT yeşil** (Qt canlı görünümde) — eskiden güven yüzdesine
     göre yeşil/camgöbeği/kırmızı arası kayardı, takım kararıyla sadeleştirildi.
   - Küçük düzenlemeler: `BESLEME_CONF` 0.10→0.05, ByteTrack yaml'daki `track_low_thresh`
     0.1→0.05, manuel panel/D-pad/açı göstergesi daha kompakt (HEDEFLER kartına yer açmak
     için), D-pad tuş metinleri tek glife indirildi (▲/◀/▶/▼/MERKEZ).
   - **BİLİNÇLİ OLARAK GETİRİLMEYEN:** SAHI (Slicing Aided Hyper Inference) dilimli tespit —
     `sahi` kütüphanesi, `sahi`/`sahi_dilim`/`sahi_ortusme` ayarları, `_analiz_sahi`,
     `sahi_durumu()`, alt çubuktaki SAHI durum göstergesi, `requirements.txt`'teki
     `sahi>=0.11.15` satırı. Takım kararı: bu özellik şimdilik bu branch'e girmesin.
     `hedeftakip`'te duruyor, ileride istenirse oradan tekrar bakılır.
   - **Getirilmedi (kasıtlı, kapsam dışı):** `hedeftakip`'teki `models/best_openvino_model/`
     (türetilmiş model çıktısı — CLAUDE.md ilke: türetilmiş biçimler repoya girmez, herkes
     kendi makinesinde üretir), `app/ayarlar.json` (bu branch'in kendi kalibre edilmiş çalışma
     zamanı değerleri — `hedeftakip`'in farklı ayar setiyle ezilmedi), `Baslat.bat`'taki
     `venv`/`​.venv` sıralama değişikliği, `CLAUDE.md`'nin `hedeftakip` versiyonu (o branch'in
     kendi günlüğü SAHI'yi merkeze koyuyor — bu madde onun yerine kendi doğru özetimizdir).
   - Doğrulama: `python app/algi.py`, `python app/nisan.py`, `python app/kapi_testleri.py`
     hepsi geçti; `arayuz_qt.py` hatasız import edildi. `algi.py`/`nisan.py` artık
     `hedeftakip`'in ilgili dosyalarıyla **birebir aynı** (satır satır diff temiz).

12. ✅ **HEDEFLER kartı dikey büyümüyor + AI 3 FPS sorunu çözüldü** (13.08) —
   - **HEDEFLER kartı artık YATAY.** Eskiden her yeni tanınan hedef `QVBoxLayout`'a yeni
     satır olarak ekleniyordu → kart dikey büyüyüp alttaki Motor Hızı/Lazer kartlarını
     aşağı itiyordu. `QHBoxLayout` + sabit yükseklikte (`34px`) yatay kaydırmalı
     `QScrollArea`'ya çevrildi: isimler yan yana dizilir, kart boyu sabit kalır, sığmayan
     kısım yatay kaydırılır (dikey kaydırma yok, `addStretch` ile butonlar sola yaslanır).
   - **3 FPS'in kök sebebi bulundu — ÇİFT problem:**
     1. `app/ayarlar.json`'da `cozunurluk: 1280` kayıtlıydı; model (`models/best.pt`,
        checkpoint meta verisinden doğrulandı: **YOLO11s**, `imgsz=640`'ta eğitilmiş)
        1280'de çalıştırılıyordu — hem 4× fazla piksel işi hem eğitim çözünürlüğünden
        sapma (isabeti de artırmıyor). **640'a düşürüldü** (`algi.VARSAYILAN_AYAR` zaten
        640'tı, yalnızca kaydedilmiş yerel dosya sapmıştı).
     2. Çözünürlük düzeltmesiyle bile CPU'da (bu makinede ayrık GPU yok, torch CPU-only
        derleme) YOLO11s ham PyTorch ile **ölçüldü: ~3.7 FPS**. **OpenVINO export**
        kuruldu ve üretildi (`models/best_openvino_model/`, 640px) → **ölçüldü: ~15 FPS**
        (aynı makinede, aynı 640, ~4× hızlanma). `app/algi.py`'deki `_model_bul()` zaten
        `best.engine` > `*_openvino_model` > `*.onnx` > `*.pt` önceliğiyle arıyordu —
        klasör var olduğu için kod değişmeden otomatik devreye girdi.
   - `requirements.txt`'e `openvino>=2023.3` eklendi (export komutu yorum olarak yanında).
     `.gitignore`'a `*_openvino_model/` eklendi — TensorRT (`.engine`) gibi bu da **türetilmiş
     çıktı**, repoya girmez, herkes kendi makinesinde `yolo export model=models/best.pt
     format=openvino imgsz=640` ile üretir (tek komut, birkaç saniye sürüyor).
   - ⚠ **Yeni klonlayan/başka makineye geçen biri OpenVINO klasörünü görmeyecek** — ilk
     açılışta uygulama otomatik `best.pt`'ye (PyTorch, yavaş) düşer, uyarı vermez. Export
     komutu zaten [README.md](README.md)'de yazılı (§Model); ekip üyeleri kendi
     makinelerinde **bir kez** çalıştırmalı — 5 saniye sürüyor, FPS'i ~4× artırıyor.

---

## 7. LAZER'e özgü içgörüler (mermiden TAMAMEN farklı — akılda tut)

- **Balistik düşüş YOK** → mesafeye göre nişan düzeltmesi gerekmez. Sadece **kamera-lazer
  boresight/paralaks** kalibrasyonu (kameranın merkezi ≠ lazerin vurduğu nokta, ofset kalibre edilir).
- **Dwell time (bekleme süresi):** Balonu patlatmak için lazer balon üzerinde **bir süre
  tutulmalı.** Hareketli hedefte (Aşama 2-3) problem "vur-geç" değil **"noktayı üstünde tut".**
  → Aşama 2-3'ün gerçek zorluğu takip kararlılığı ve merkezleme hassasiyetidir.
- **Nişan noktası = BALON**, maket gövdesi değil. Model balonu tespit etmeli ya da
  maket-balon geometrik ofsetinden balon merkezi hesaplanmalı.
- Lazer güvenliği: test/çekimde lazer gözlüğü zorunlu.

### 7.1 Otonom takip — "aşırı/saçma hareket" (13.08.2026)

Şikâyet: OpenVINO ile FPS ~4→~15'e çıkınca (bkz. §6 madde 12) otonom modda namlu hedefi
ortalarken **aşırı ve tutarsız** hareket etmeye başladı. İki kök sebep bulundu, ikisi de
**FPS artışının doğrudan sonucu**:

1. **Sabit `d_yaw` tavanı (eski `MAKS_ADIM_DER=8°`) bir HIZ SINIRI DEĞİL, çağrı başına
   sabit bir açıydı.** FPS arttıkça bu tavanın izin verdiği GERÇEK açısal hız da katlanarak
   arttı: 4 FPS'te 8°×4=32°/sn, 15 FPS'te 8°×15=120°/sn — motorun en hızlı kademesinin
   (Hızlı: 75°/sn) bile üstünde bir sınır. **Çözüm:** `MainWindow._nisan_geldi`
   (`arayuz_qt.py`) artık PD'nin ürettiği komutu **seçili motor hızına göre** (`P.HIZ_TABLO`)
   kırpıyor — tıpkı basılı-tutma D-pad hareketinde (`_tekrar_tik`) zaten yapılan
   `adım = tavan_hız × geçen_süre` hesabıyla AYNI mantık. ESP32 konum geri bildirimi
   göndermediği için (`pan_ham`/`tilt_aci` yazılımın İNANCIdır, ölçüm değil) bu kırpma
   olmadan yazılımın hedef açısı motorun gerçekte gidebileceğinden hızlı ilerleyebiliyordu.
2. **Türev yumuşatması (`TUREV_YUMUSATMA`) sabit-örneklem alfaydı, zaman-sabiti değil.**
   FPS yükselince (dt küçülünce) aynı sabit alfa gerçek-zamanda DAHA AZ gürültü filtreliyordu
   → tespit kutusunun kare-kare piksel titremesi türev terimine daha güçlü bindi. **Çözüm:**
   `nisan.py`'de `TUREV_ZAMAN_SABITI` (saniye) tabanlı üstel yumuşatmaya geçildi
   (`alfa = 1 - exp(-dt/tau)`) — filtrenin gerçek-zamandaki gücü FPS'ten bağımsız sabit kalır.

⚠ **Bu iki düzeltme gerçek donanımda TEST EDİLMEDİ** (bu makinede kamera/gimbal yok).
Simülasyonla (temiz sinyal + sentetik piksel gürültüsü) doğrulandı ama motor ataleti/ivme
profili, UART gecikmesi, gerçek tespit gürültüsü büyüklüğü modellenmedi.

### 7.2 Otonom takip — ASIL kök sebep: ByteTrack yerine naif IoU tracker (13.08.2026)

§7.1'deki PD/hız kırpma düzeltmelerinden sonra kullanıcı **düşük Kp (0.27) ve Kd=0 ile bile**
otonom modda "rastgele hareket, tanımladığı hedefi takip etmiyor" bildirdi — bu, PD
kazancının değil **hedef kimliğinin (tracking ID) kendisinin** kararsız olduğunu gösterdi.
Ayırt edici ipucu kullanıcıdan geldi: **manuel modda araç düzgün çalışıyor, sorun yalnızca
otonoma geçince başlıyor.**

**Kök sebep bulundu:** §6 madde 11'de (`hedeftakip`'ten SAHI hariç taşıma) `model.track()`
(ByteTrack, Kalman-filtreli hareket tahmini) yerine basit kare-kare IoU eşleştirmeli kendi
tracker'ımız (`_iou_id_esle`) getirilmişti. Bu değişim **hedeftakip'te SAHI'nin dilimli
tespitiyle ByteTrack çalışamadığı için zorunluydu** — ama bu branch SAHI kullanmıyor,
yani o zorunluluk hiç geçerli değildi; gereksiz yere taşınmış bir regresyon oldu.

**Neden özellikle otonom modda ortaya çıktı:** ByteTrack'in aksine naif IoU eşleştirmenin
hareket tahmini YOKTU — yalnızca art arda iki karenin ham kutu konumlarını karşılaştırıyordu
(eşik IoU≥0.30). Otonom modda gimbal PD düzeltmesiyle kendi kendine dönünce KAMERA GÖRÜNTÜSÜ
de kayar; bir sonraki karede aynı fiziksel hedefin kutusu yeterince örtüşmeyip **farklı bir
ID alabiliyordu**. Bu, `_kilitli_track_id`in dets içinde bulunamamasına, `_karar_ver`'in o
"yeni" ID için onay durumunu sıfırdan başlatmasına ve nişan noktasının (aim point) kare kare
kararsızlaşmasına yol açıyordu — tam olarak "rastgele hareket" tarifi. Manuel modda otomatik
kilit/nişan hiç devrede olmadığı için (insan D-pad ile sürüyor) bu hiç görünmüyordu — kendi
kendini besleyen bir geri besleme kırılmasıydı: yalnızca gimbal OTONOM olarak hareket ederken
tetikleniyordu.

**Çözüm:** `algi.analiz_et` **ByteTrack'e (`model.track`, `persist=True`) geri döndürüldü**;
`_iou_id_esle`/`_iou_hesapla`/`_iou_sonraki_id`/`_iou_onceki_kutular` tamamen silindi (SAHI
olmadan hiçbir amaca hizmet etmiyorlardı). Kilit/hayalet-hedef/onay mantığının TAMAMI
korundu — yalnızca "ID nereden geliyor" değişti (`b.id` / ByteTrack, eskisi gibi). OpenVINO
export edilmiş modelle `model.track()`'in sorunsuz çalıştığı ayrıca doğrulandı (§6 madde 12'de
kurulan hızlandırma ile uyumlu). Tüm testler (`algi.py`, `nisan.py`, `kapi_testleri.py`) ve
gerçek OpenVINO modeliyle çok karelik bir duman testi (`analiz_et` art arda 10 kare, hata YOK)
geçti.

⚠ **Bu da gerçek donanımda TEST EDİLMEDİ.** Kamera/gimbal olmadan "hedefi artık akıcı takip
ediyor mu" nihai olarak doğrulanamaz — bir sonraki adım budur. §7.1'deki hız-kırpma
(`_nisan_geldi`) ve zaman-sabitli türev yumuşatması (`nisan.TUREV_ZAMAN_SABITI`) düzeltmeleri
de yerinde duruyor, ByteTrack'le birlikte çalışırlar (birbirini dışlamazlar).

### 7.3 Otonom takip — "ortaladığı an durmuyor, karşı tarafa geçiyor" (13.08.2026 akşam)

ByteTrack düzeltmesinden (§7.2) sonra kullanıcı **artık gerçekten takip ediyor** dedi — ama
yeni bir davranış bildirdi: hedefi ortalarken **durmuyor**, karşı tarafa geçiyor, oradan geri
dönüyor, yine geçiyor — **hiç yerleşmeyen bir salınım**. Bu klasik bir "gecikme" (dead-time)
kontrol sorunu: ESP32 konum geri bildirimi göndermediği için (§5.1) yazılım motorun NE ZAMAN
fiziksel olarak hedefe vardığını bilemez. Motor bir komutu yerine getirirken (ivmelenme
profiliyle onlarca-yüzlerce ms sürer, özellikle H_NORMAL'de tepe hıza — 40°/sn — çıkmak 0.4 sn
ister) kamera görüntüsü henüz güncellenmez; o süre içindeki HER YENİ KARE aynı (bayat) piksel
hatasını görür ve PD aynı hatadan taze bir düzeltme daha üretir. Her biri tek başına §7.1'in
hız sınırının içinde kalsa bile **TOPLAMLARI** gerçek ihtiyacın kat kat üstüne çıkar — motor
nihayet yetiştiğinde hedef zaten karşı tarafa geçmiş olur, aynı şey tersten tekrarlanır.

**Çözüm — "meşgul kapısı" (`MainWindow._nisan_geldi`):** gönderilen komutun tahmini fiziksel
tamamlanma süresi kadar (üçgen ivme profili: `2×√(mesafe/ivme)`, asgari `NISAN_MIN_ARALIK=0.10`
sn) **yeni komut kabul edilmez**. Bir sonraki kabul edilen kare artık kameranın GÜNCELLENMİŞ
(bayat olmayan) görüntüsünü yansıtır, PD gerçek hataya göre karar verir.

⚠ **Simülasyonla ölçülen gerçek bir ödünleşim var: bu düzeltme yakınsamayı YAVAŞLATIYOR.**
Gerçekçi (ivmelenen) bir motor benzetiminde meşgul kapısı OLMADAN sistem ~3 sn'de yerleşiyordu;
kapıyla birlikte ~8 sn'ye çıktı (salınım kesinlikle YOK — `yön-değişimi=0` — ama daha temkinli).
**Ayrıca bu benzetim, meşgul kapısı OLMADAN bile salınım ÜRETMEDİ** — yani gerçek donanımdaki
salınımın tam mekanizmasını laboratuvar dışında birebir yeniden üretemedim; UART gecikmesi,
inference'ın kendi işlem süresi (kare "yakalandığı an" değil, ~66ms SONRA sonuç veriyor) veya
gerçek tespit gürültüsü gibi modellemediğim etkenler de katkıda bulunuyor olabilir. **Meşgul
kapısı salınımı KESİNLİKLE azaltır/önler** (matematiksel olarak komutların üst üste binmesini
engeller).

**13.08 gece — ince ayar:** kullanıcı bu ilk sürümü ("tam tamamlanma süresini bekle") denedi:
açı artık sapıtmıyordu (salınım gerçekten gitmişti) ama **"ortalamakta çok geç kalıyor,
akıcılık kötü"** dedi. Kök sebep: `2×√(mesafe/ivme)` hareketin TAMAMEN durmasını (üçgen
profilin hem hızlanma HEM yavaşlama yarısını) bekliyordu — gereğinden çok temkinliydi.
**`NISAN_MESGUL_ORANI` (0.4) eklendi**: artık bu tam sürenin yalnızca %40'ı kadar beklenir —
hareketin TAMAMEN durmasını değil, GÖRÜLEBİLİR ölçüde ilerlemesini bekler. Taban da
`NISAN_MIN_ARALIK` 0.10→0.04 sn'ye indirildi (zaten inference ~15 FPS'te ~0.067 sn'de bir kare
geldiği için 0.10'un pratik bir etkisi kalmamıştı). Simülasyonla tarandı (oran 0.7→0.2):
**0.4'te 3 sn'de yerleşme + salınım YOK**, 0.2'de salınım geri gelmeye başlıyor — 0.4 bilinçli
bir güvenlik payıyla seçildi. Gerçek donanımda hâlâ yavaşsa **bir sonraki adım
`NISAN_MESGUL_ORANI`'yi kademeli yükseltmek** (0.5, 0.6…) veya salınım geri gelirse düşürmek
(`arayuz_qt.py`, tek sabit); `NISAN_MIN_ARALIK` ikinci bir tavan.

---

## 8. AÇIK KARARLAR (netleşince güncelle)

- **[x] Kamera / mesafe:** **Derinliksiz tek kamera + bilinen boyut** (karar, 16.07.2026).
  KTR'deki OAK-D-Pro bağlayıcı değil — KTR genel fikir için, mimariyi şartname + gerçek
  imkânlar belirler. Mesafe = monoküler geometrik tahmin + 10–15 m bandı kontrolü.
- **[x] Donanım gerçeği:** Geliştirme laptopu **Huawei MateBook D15, ~8 GB RAM, ayrık GPU YOK**
  (KTR'deki HP Victus/RTX 3060 elde değil). Sonuçları:
  - **Eğitim → Google Colab'da** (ücretsiz T4 GPU; CPU'da saatler süren eğitim dakikalara iner).
    Veri üretimi lokalde → zip → Colab'da eğit → `best.pt` indir. Lokal CPU eğitimi YASAK değil
    ama israf; sadece küçük hızlı denemelerde.
  - **Canlı tespit (inference) lokalde CPU'da** koşacak → asıl risk FPS. Önlemler: YOLOv8n/11n
    (en küçük model), imgsz 416–512, ve **ONNX Runtime / OpenVINO export** (Intel CPU'da
    ciddi hızlanma). Hedef: ≥10 FPS canlı tespit.
  - Yarışma günü daha güçlü laptop bulunursa tak-çalıştır olacak şekilde kod donanım-bağımsız yazılır.
- **[x] İmha:** LaserTree 80W lazer (yurt dışından geldi, onaylı).
- **[x] Platform:** Yarışmaya laptop ile gidilecek.
- **[ ] E-STOP'TA TİLT PARK ETSİN Mİ? (güvenlik kararı — ekip vermeli, 21.09.2026)**
  `kontrol.py` §5.1 kararına göre tilt'i **0° park** konumuna indiriyor; ama
  `kapi_testleri.test_estopta_iki_eksen_de_oldugu_yerde_donar` ve `mock_esp32.py`
  testi **her iki eksenin de olduğu yerde donmasını** bekliyor → bu iki test
  KIRMIZI. Testler yeni niyete göre yazılmış, kod eski davranışta. Şartname
  Yetenek 3 "hareket ederken E-Stop → sistem durur" diyor ve park etmek de bir
  harekettir (§5.1'deki ⚠ nota bak). **Karar verilmeden kodu teste ya da testi
  koda uydurmayın.**
- **[ ] Dikey eksen dişli oranı:** `protokol.py` testi `TILT_STEP_DER = 17.778`
  (1:1) bekliyor, sabit **8.889**'a çekilmiş (yani 2:1 girilmiş). Gerçek oran
  ölçümle doğrulanmadan test düzeltilmemeli — yanlışsa tüm tilt açıları yanlış
  olur (§5.1).
- **[ ] Arayüzün görsel doğrulaması yarım:** Apple tasarım sisteminin son
  rötuşları (kaydırıcı oluk marjı, otonom panel boşluğu, alt çubuk model yazısı)
  yalnızca kod düzeyinde yapıldı; gerçek ekranda karşılaştırılmadı (§12.4).
- **[ ] Aktüatör/kontrolcü fiziksel durumu:** NEMA23 + ESP32 alındı mı? Araç mekanikçe
  sıfırdan yapılacağından yazılım donanım-bağımsız (mock UART) ilerleyebilir.

---

## 9. Yol Haritası (video 10.08 → final)

**Video öncesi (yazılım hazırlığı — donanım-bağımsız yapılabilecekler):**
1. ✅ **Renk mimarisi** (16.07, 24.07'de sadeleştirildi): `app/renk_analizi.py` — HSV ile
   kırmızı/cyan → dost/düşman. **Basit binary:** maviye yakın=Dost, kırmızıya yakın=Düşman,
   arası yok. Eski "Bilinmeyen" ve "İHA/Füze hep düşman (HEP_DUSMAN)" mantığı KALDIRILDI —
   tip-kuralı yok, sadece renge bakılır. Renk yalnız **Aşama 3'te** çalışır (A1-A2 sadece tanıma).
2. ✅ **Renkli + balonlu sentetik veri** (16.07): `render_synth.py` şartname renkleriyle
   (#F50A0A / #00A3E0) render ediyor; balon (direkte, rastgele renk) **5. sınıf "balon"** olarak
   etiketleniyor (nişan noktası); koyu perde arka planı eklendi (yarışma ortamı). Işık BEYAZ
   tutuldu (renkli ışık HSV analizini bozar). Eğitimde `hsv_h=0.01` (ton kayması kırmızıyı
   cyana çevirmesin!).
3. ⚠️ **Mesafe (16.07) → DEVRE DIŞI (18.07), kodu silindi (30.07):** kalibre edilmeden
   yanıltıcı olduğu için UI'dan ve karar zincirinden çıkarıldı, sonra ölü kod olarak
   temizlendi (bkz. §6 madde 4). Menzil tablosu §4'te; özellik gerekince oradan yazılır.
4. ✅ **v1 Colab eğitimi** (17.07): yolov8n, 100 epoch, T4. **mAP50 0.995 / mAP50-95 0.975**
   (tüm sınıflar; balon 0.995). DİKKAT: sentetik val setinde — gerçek dünya performansı değil,
   boru hattı doğrulaması. `best.pt` + `best.onnx` indirildi, yerel modele kondu.
5. ✅ **Gerçekçi poz v2** (17.07): render pozları yarışma geometrisine daraltıldı
   (elevasyon ±12°, burun-aşağı 0-20°, roll≈0, %15 serbest pay; balon konumu alt/üst/gövde
   rastgele). v2 veri üretildi → **v2 Colab eğitimi kullanıcıda bekliyor** (aynı notebook).
   Zip komutu: `Compress-Archive -Path dataset -DestinationPath dataset.zip -Force`

> **Model/veri boru hattı = YEDEKTE (vazgeçildi):** Sentetik veri (render_synth), Roboflow v3
> birleştirme (`dataset_v3`, 2454/382), Colab eğitimi (v1 mAP50 0.995 ama yalnız sentetik val)
> — hepsi `sentetik_veri`'de, artık yedekte. Sim-to-real farkı + düşük gerçek doğruluk nedeniyle
> **current model/veri terk edildi; gerçek maket fotoğraflarıyla sıfırdan eğitilecek.** Yeni model
> `models/best.pt` olarak repoya konunca uygulama otomatik kullanır (kod değişmez).

**FAZ 3 — Gerçek veri ile model (maket baskıları TAM SETİ gelince):**
- Maketler ŞARTNAME RENKLERİNDE basılmalı/boyanmalı: kırmızı (tümü) + cyan (F16, Heli).
  Yoksa dost/düşman gerçekte test EDİLEMEZ. Balonlar temin edilmeli (kırmızı ağırlıklı).
- Fotoğraf protokolü: her maket × {5,10,15 m} × {yaw çeşitleri} × {aynı hiza/alt/üst}
  × {balonlu/balonsuz} × farklı ışık → tip başına 150-300 kare. v3 ile ön-etiket + elle düzeltme.
- **Fine-tune v4:** v3 + yeni gerçek veri karışık, düşük lr → sim-to-real kapanışını tamamlar.
- Mesafe özelliği geri isteniyorsa FOCAL_PX kalibrasyonu yeniden yazılır (§6 madde 4);
  HSV eşiklerini gerçek boyada doğrula.

**FAZ 4 — Teknofest örnek parkur görüntüleri gelince:** görüntüler `sentetik_veri/backgrounds/`
klasörüne → `render_synth.py` ZATEN gerçek arka plan destekli (`REAL_BGS`) → v4 eğitimi.
Işık/zemin bilgisiyle gerçek test ortamı simülasyonu kurulur. (Balon konumu artık [KESİN]:
maketlerin altında → `draw_balloon` buna göre sabitlenir.)

**FAZ 5 — Entegrasyon ve "kusursuzluk" (donanımla paralel):**
- ✅ Arayüz: manuel/otonom mod, aşamaya duyarlı görev paneli, çalışan yazılımsal E-Stop.
- ✅ **Kontrol iskeleti kuruldu** (18.07): `protokol.py` + `mock_esp32.py` + `kontrol.py` —
  ATEŞ/E-Stop zinciri arayüze bağlı, donanımsız uçtan uca test edilebiliyor.
- ⏳ Yasak alan (atışa/harekete) mantığı — arayüzde görsel var, işlevsel değil.
- ⏳ Tur sayacı — arayüzde gösterge var, gerçek tur ilerleme mantığı yok (donanım/otonom
  döngüsü gelince bağlanacak).
- ⏳ **Aşama-1 zarf sırası bağlanmadı (yarım uç).** Sürükle-sırala kartlar çalışıyor ve
  `SiraliKartlar.sirali_tipler()` kullanıcının dizdiği sırayı veriyor, ama bu sırayı **hiçbir
  yer okumuyor** — "yanlış sırada vurma = −5 ceza" mantığı yok. Otonom/atış döngüsü kurulunca
  hedef seçimi bu listeyi tüketmeli.
- ⏳ Gimbal sürüş matematiği: piksel hatası → açı komutu (PD kontrol, KTR referans).
- Hedef↔balon eşleştirme (nişan noktası) + dwell (lazeri üstünde tutma) mantığı.
- **Test protokolü:** Aşama 1/2/3 senaryo simülasyonları + kabul kriterleri + regresyon
  listesi — "yarışmada yazılımsal aksaklık çıkmasın" hedefi buradan geçer.

**Donanım gelince:** gimbal sürüş, ateş tetik, homing, gerçek E-Stop, boresight kalibrasyonu,
uçtan uca entegrasyon, video çekimi (6 yetenek).

**Final öncesi:** 3 aşama senaryolarını gerçek parkurda tekrarlı prova, bakım süresi stratejisi
(3 aşama toplam 10 dk bakım), zarf/sıra stratejisi (Aşama 1), sürü/çoklu hedef önceliklendirme.

---

## 10. Dosya haritası

**REPO (public, GitHub'a giden):**
```
d:\Masaüstü\Derin Mavi\            ← repo kökü (git init yapıldı)
├── Baslat.bat                   ← ÇALIŞTIR (Windows tek tık) → app/arayuz_qt.py
├── README.md                    ← ekip için kurulum/kullanım özeti
├── CLAUDE.md                    ← BU DOSYA (proje beyni)
├── requirements.txt             ← ultralytics, opencv-python, numpy, PySide6
├── sartname\                    ← Şartname.pdf + sartname_metin.txt (şartname taraması için)
├── .gitignore  .gitattributes
├── app\                         ← uygulama kodu
│   ├── arayuz_qt.py (ANA, native PySide6; _model_bul() dinamik model)
│   ├── algi.py (algı çekirdeği=tek kaynak: kamera+YOLO+karar)
│   ├── nisan.py (piksel hatası→açı PD nişan + hedef↔balon eşleştirme)
│   ├── renk_analizi.py (HSV dost/düşman)  kontrol.py  protokol.py  mock_esp32.py
│   ├── kapi_testleri.py (E-Stop/ateş/yasak alan güvenlik kapıları — pencere açmaz)
│   └── Grafik\ (logo + kart ikonları)
│   NOT: her modül `python app/<ad>.py` ile kendi kendini test eder (donanım gerekmez).
└── models\                      ← BOŞ gelir (README.md + .gitkeep). Model buraya konur.
```

**YEDEK (repoda YOK — `d:\Masaüstü\Derin Mavi - YEDEK\`):** `sentetik_veri\` (dataset+model+eğitim),
`Analiz\` (Şartname.pdf, KTR [Takım ID 948118], Parkur çizim, temsili fotolar — GİZLİ),
`Modeller_Kil6t\Modeller.3mf` (TEKNOFEST maket 3D), `Arayuz_legacy\` (eski Flask arayüzü + html + png'ler).
Gerçek veri eğitimi/kalibrasyon gerekince buradaki `sentetik_veri` boru hattı geri getirilir.

---

## 12. Algı/Arayüz sağlamlaştırması (29.07.2026) — "neden ham YOLO'dan kötüydü?"

Şikâyet: *"Arkadaşım YOLO'yu doğrudan kameraya bağladı, AYNI model çok daha iyi tanıdı.
Bizimkinde öyle değil, takip edemiyor, odaklanamıyor."* Şikâyet **haklıydı** ve sebebi
model değil, **bizim kodumuzdaki 5 katmandı.** Kök sebepler ve alınan kararlar:

| # | Kök sebep | Çözüm | Dosya |
|---|---|---|---|
| A1 | **Sınıf adı beyaz listesi** tespitleri sessizce siliyordu (`if cls not in DISPLAY: continue`). Model `F16`/`iha`/`balloon` gibi ufak bir ad farkıyla eğitilmişse TÜM kutular uyarısız yok oluyordu. | Sınıf adı `r.names`'ten **dinamik** okunuyor; `ES_ANLAM` ile normalize ediliyor; eşleşmeyen sınıf **ham adıyla çiziliyor**. Kutu asla atılmaz. | `algi.py` |
| A2 | **ByteTrack yanlış yapılandırılmıştı** (`new_track_thresh 0.1` vs varsayılan 0.25) → herkes ilk karede ID alıyor → "Gösterim eşiği" ayarı **ölü**; çöp tespitler `track_buffer` boyunca **hayalet kutu** olarak ekranda kalıyordu. Ayrıca modele `conf=0.25` verildiği için ByteTrack'in düşük skorlu kutuları hiç görmüyordu (varlık sebebi iptal). | Tracker eşikleri **Ultralytics varsayılanlarına** çekildi; modele `conf=BESLEME_CONF(0.10)` veriliyor, filtreleme tracker'a bırakıldı; `gosterim` gerçek bir çizim filtresi oldu. | `algi.py` |
| A3 | **Kamera tamponu** → görüntü ~200-350 ms geçmişti (kutu nesnenin arkasında). Ayrıca çözünürlük hiç set edilmiyordu (kamera varsayılanı). | `KameraOkuyucu` ayrı thread'de okuyup **hep en taze kareyi** tutuyor; `BUFFERSIZE=1`, MJPG + 1280×720 isteniyor. | `algi.py` |
| A4 | **Qt sinyal kuyruğu birikiyordu** (queued connection olayları düşmez) → gecikme kartopu. | "Son kare kazanır": GUI kareyi çizmeden thread yeni kare göndermiyor. | `arayuz_qt.py` |
| A5 | `KeepAspectRatioByExpanding` görüntüyü **kırpıyordu** (kadraj kenarındaki tespit görünmüyordu) + QGraphicsView proxy'si ile **iki kez smooth ölçekleme** (bulanıklık + boşa CPU). | `KeepAspectRatio` + `FastTransformation`. | `arayuz_qt.py` |
| A6 | `cv2.flip` her kareyi **koşulsuz aynalıyordu** → ham YOLO'dan farklı görüntü + nişan matematiğinde işaret hatası (gimbal hedeften kaçar). | Varsayılan **KAPALI**, ayar panelinde seçenek; açıkken yaw işareti otomatik telafi ediliyor. | `arayuz_qt.py`, `nisan.py` |

**Şartname/güvenlik hataları (giderildi):**
- **B1** `_fire_bas` → `kontrol.ates()` zorunlu argümansız çağrılıyordu (**TypeError**) ve
  **E-Stop kontrolü yoktu**. Ölü yol kaldırıldı; ateşin **tek kapısı** `_ates_bas`.
- **B2** E-Stop yalnız ATEŞ butonunu kilitliyordu; **D-pad/WASD hareket komutu gitmeye devam
  ediyordu** ve arayüzdeki açı etiketleri gerçek konumdan kopuyordu (Yetenek 3 ihlali).
  Artık hareketin de tek kapısı var (`_aci_hareket`), E-Stop'ta en başta kapanıyor.
- **B4** `ates()` `dx=dy=0` gönderdiği için mock ESP32'de **süregelen hareketi iptal
  ediyordu** (takip + ateş aynı anda çalışmıyordu). *(Bu hata sınıfı 05.08.2026'da kökten
  kalktı: protokol artık **mutlak açı** kullanıyor, ateş komutu hareket hedefine hiç
  dokunmuyor — bkz. §5.1. Aşağıdaki delta notları tarihsel kayıttır, uygulanmaz.)*

**Tasarım ilkesi (bundan sonra korunacak):** ayarların varsayılanları **Ultralytics'in kendi
varsayılanlarıdır.** Hiçbir kaydırıcıya dokunmayan biri, ham `yolo track source=0` ile aynı
davranışı görür. Kodun içinde gizli "iyileştirme" YOKTUR; sapmak isteyen **ayar panelinden** sapar.

**Bu makinede ölçülenler (29.07):** kamera 1280×720 @ **10 FPS** (YUY2; dahili kamera MJPG
desteklemiyor, çözünürlük düşürmek FPS'i ARTIRMIYOR — ölçüldü) · inference 640px'te ~20 FPS ·
**darboğaz KAMERA.** → Takip akıcılığı için **30 FPS'lik USB kamera** en yüksek getirili
donanım yatırımı. CPU tarafında OpenVINO (`yolo export ... format=openvino`) 2-3× ek pay verir;
`models/best_openvino_model/` varsa uygulama **otomatik** tercih eder.

**⚠ MODEL GERÇEĞİ (08.08 güncel):** `models/best.pt` **4 sınıf** tanıyor:
`DRONE`, `F16`, `FUZE`, `HELIKOPTER`. *(29.07'de yalnız 2 sınıf vardı — F16 ve İHA o gün
eklendi.)* **BALON hâlâ modelde YOK → tespit edilemiyor.** Balon olmadığı için nişan noktası
gövde merkezine düşüyor (nişan zinciri hazır, balon gelince kod değişmeden devreye girer).
Arayüz bu gerçeği alt çubukta açıkça yazıyor. Balon **nişan noktasıdır** (maketlerin altında,
§7) — eksikliği doğrudan isabet hassasiyetini düşürür, sıradaki eğitimin **1 numaralı işi**
`balon` sınıfını eklemek: 5 sınıfın tamamı (`f16, helikopter, drone, fuze, balon`).

**Model artık repoda:** `models/best.pt` versiyon kontrolünde (takım kararı 08.08) — herkes
aynı ağırlıkla çalışsın diye. Türetilmiş biçimler (`.onnx`, `.engine`) **girmez**; `.engine`
TensorRT çıktısıdır ve GPU modeline + TensorRT sürümüne + sürücüye bağlıdır, başka makinede
açılmaz. Herkes kendi makinesinde üretir (`yolo export model=models/best.pt format=engine`).

### 12.1 KESİN TANIMA kararlılığı (07.08.2026) — "%70'i geçen hedefi takip et"

Şikâyet: *"YOLO çok kararlı davranmıyor; bir modeli %70 üzerinde doğruladığı zaman onu takip
etmesi gerekiyor."* Onay mekanizması (`_karar_ver`) **zaten vardı** — sorun kırılgan olmasıydı.
Beş kök sebep bulundu ve giderildi:

| # | Kök sebep | Çözüm |
|---|---|---|
| 1 | **Tek zayıf kare sayacı SIFIRLIYORDU** → kural pratikte "3 ARDIŞIK kare ≥%70" demekti. Gerçek videoda güven dalgalanır (%75, %68, %72…), onay ya hiç gelmiyor ya çok geç geliyordu; kutu `?` kalıyordu. | **Histerezis:** zayıf kare sayacı sıfırlamaz, **bir azaltır**. Ölçüldü: aynı 20 karelik gerçekçi dizide onay **14. kare → 7. kare**. |
| 2 | **Sınıf tekilliği** (`_kilitli_siniflar`): bir sınıfı tek track "sahiplenirdi", aynı tipten ikinci hedef **sonsuza dek belirsiz** kalırdı. Oysa Aşama 2'de 3 koldan aynı anda Füze+İHA gelir, Aşama 3'te düşman F16 ile dost F16 aynı karede olabilir. | Kural **tamamen kaldırıldı**. Ayırt etme zaten takip ID'sinin (ve A3'te rengin) işi. |
| 3 | Onaylanmış hedefe **hâlâ gösterim eşiği** uygulanıyordu → bir kez doğrulanan hedef güveni düşünce kutu tamamen kayboluyordu. | Onaylı track için `ONAYLI_ESIK = 0.02` — pratikte elenmez. Operatörün kuralı bu: *bir kez %70'i geçtiyse TAKİP ET.* |
| 4 | `kayip_esigi` sabit **60** kare, ama ByteTrack `track_buffer`=30'da ID'yi düşürüp nesneye **yeni ID** veriyordu → onay sıfırdan başlıyordu. | Eşik artık `kararlilik` ayarından türer, ikisi senkron. |
| 5 | `onay_esigi`/`onay_tekrari` **panelde yoktu** — kodda gömülüydü, sahada ayarlanamıyordu. | İkisi de ⚙ panelinde ("Kesin tanıma eşiği", "Onay için kare sayısı"). |

**Sınıf yarışı çoğunluk oylamasıyla çözülür:** rakip bir sınıf yüksek güvenle gelirse mevcut
adayın puanı düşer, ancak puan tükendiğinde aday değişir. Tek karelik yanlış tahmin adayı
**deviremez** (sadece onayı geciktirir); ısrarlı bir sınıf **devirebilir** — model gerçekten
fikir değiştirdiyse ona uyulmalı.

**Onay bozulma:** onaylı track `ONAY_BOZULMA = 15` kare üst üste eşiğin altında kalırsa onay
düşer. Olmasaydı bir kez yanlış onaylanan sınıf, ID yaşadığı sürece düzelmezdi.

**Sıra değişti:** karar **önce**, çizim eşiği **sonra**. Eşik altında kalan kare de onay
durumunu beslemeli — yoksa onaylı bir track zayıfladığında `zayif` sayacı hiç artmaz ve
yanlış onay sonsuza dek yaşardı.

`_karar_ver`'in **hiç testi yoktu**; `algi.py`'ye 9 birim testi eklendi (histerezis, çoklu
hedef, aday devirme, onay bozulma, kayıp ID temizliği).

### 12.2 ÇAKIŞAN KUTU temizliği (07.08.2026) — "aynı alanda iki şey var sanıyor"

Şikâyet: *"Kutular bazen üst üste biniyor, aynı alanda 2 şey varmış gibi algılıyor ama
görevlerde asla böyle bir şey olmayacak."*

**Kök sebep: Ultralytics NMS'i SINIF İÇİ çalışır** (`agnostic_nms=False`). Model aynı maketi
hem `fuze` hem `helikopter` sanarsa kutular %90 örtüşse bile **farklı sınıf oldukları için
NMS onları birleştirmez.** Paneldeki `iou` ayarı bu duruma hiç dokunmaz — o yalnızca aynı
sınıftan kutuları eler.

**Çözüm:** `_cift_kutulari_ele()` — tespit sonrası bir temizlik katmanı. Takımın verdiği görev
gerçeğini doğrudan kullanır: *hedefler raya asılı, birbirinden ayrı gelir; aynı alanda iki
hedef asla bulunmaz* → yüksek örtüşme her zaman modelin aynı nesneye iki kutu atmasıdır.

| Karar | Gerekçe |
|---|---|
| **IoU değil IoS** (kesişim / **küçük** kutunun alanı) | IoU kesişimi birleşime böler, iç içe kutularda düşük çıkar — oysa "küçük kutu büyüğün içinde" en tipik çift-kutu hâlidir. |
| Öncelik: **kesin tanınmış** > güven | Yalnızca güvene bakılsaydı, onaylanmış bir hedef o karede şanslı çıkan geçici bir kutu yüzünden elenebilirdi. |
| **Balon hariç** | Balon `dets`e değil ayrı `balonlar` listesine yazılır, temizliğe hiç girmez. Maketin **altında** olduğu için gövdeyle örtüşür — dahil edilseydi nişan noktası elenirdi (§7). |
| Varsayılan **%60**, panelde ayarlanır ("Çakışan kutu temizliği") | %99 pratikte kapalı demek. Düşürmek agresifleştirir ama Aşama 2 sürüsünde yan yana gelen iki gerçek hedeften biri elenebilir. |
| `agnostic_nms=True` **kullanılmadı** | Model seviyesinde çalışır, balonu da kapsardı ve nişan noktasını sessizce yok edebilirdi. Kendi katmanımız kontrollü ve test edilebilir. |

Uçtan uca doğrulandı (sahte model, `analiz_et` zinciri): 2 çakışan hedef → 1'e indi (güveni
yüksek olan kaldı), ayrı hedef korundu, **balon gövdeyle örtüşmesine rağmen korundu.**
`algi.py`'ye 8 birim testi eklendi.

### 12.3 macOS: kamera seçici görünümü + kamera değişiminde ÇÖKME (20.09.2026)

Şikâyet: üst şeritteki KAMERA bölümü "çok kötü görünüyor". Görsel hata **macOS'a özgüydü**
ve altından iki gerçek hata daha çıktı.

| # | Kök sebep | Çözüm |
|---|---|---|
| 1 | **QSS'te "kenarlıkla üçgen çiz" numarası** (`::down-arrow`'a `width/height:0` + saydam yan kenarlıklar) macOS'ta çalışmıyor: Qt alt bileşeni kutunun tüm genişliğine gerdiği için ok, kutunun üstüne oturan **dev bir mavi kama** olarak çiziliyordu; yanında da native okun gri kalıntısı duruyordu. | Ok QSS'te tamamen kapatıldı (`image:none; border:none; width/height:0`), yeni **`SecimKutusu(QComboBox)`** sınıfı chevron'u `paintEvent`'te QPainter ile kendisi çiziyor — her platformda aynı, ölçeklenmez. Kutu stili `#tabs` ile eşitlendi (aynı zemin/yarıçap/kenarlık) → üst şeritteki üç grup tek tasarım dili. Açılır liste kutuya sıkışmıyor (`showPopup` içerik genişliğine açıyor), uzun kamera adları kesilmiyor. |
| 2 | **"CANLI" yazısı kamera KAPALI iken de duruyordu** — gizlenen yalnızca kırmızı noktaydı, yazı ayrı widget'tı. | Nokta + yazı tek kapsülde (`#livebadge`); rozet bütün olarak görünür/gizlenir. Kapalıyken çözünürlük kutusu da soluk/devre dışı ("Çözünürlük" yazar, eski "—" değil). |
| 3 | ⚠ **Kamera değiştirince/kapatınca uygulama ÇÖKÜYORDU** (SIGSEGV; kaza izi `CaptureDelegate grabImageUntilDate:`). `VideoThread` `okuyucu.cap = None` yapıp **hemen** `eski.release()` çağırıyordu; okuma thread'i o sırada **`cap.read()` içinde** olabiliyordu. macOS/AVFoundation'da sürücü bunu affetmiyor. | `KameraOkuyucu`'ya **okuma kilidi** eklendi: `read()` süren bir cap serbest bırakılamaz; bırakma işi artık `cap_degistir()`'in kendi işi (arayüz tarafındaki `release()` çağrıları silindi). Kilit 2 sn'de alınamazsa (kamera `read()` içinde takılmış) eski cap **bırakılmaz** — bir tutamak sızdırmak çökmekten iyidir. |
| 4 | `closeEvent` yalnız `VideoThread`'i durduruyordu; **`InferenceThread` çalışırken yok ediliyordu** → Qt `abort` ediyordu (kapanışta çökme, SIGABRT). | Kapanışta inference ve kamera-tarama thread'leri de durdurulup bekleniyor. Doğrulandı: aç → kamerayı kapat → tekrar aç → kapan, **çıkış kodu 0**. |

⚠ **Bu branch'te (`Affan-UI_Design-2026-09-20`) bir kapı testi KIRMIZI ve sebebi bizim
değişikliğimiz değil:** `test_estopta_iki_eksen_de_oldugu_yerde_donar` testi E-Stop'ta **her iki
eksenin de olduğu yerde donmasını** bekliyor, ama `kontrol.estop()` §5.1'deki karara göre
**tilt'i 0° park konumuna indiriyor.** Test mi koda, kod mu teste uyacak — bu bir **güvenlik
davranışı kararıdır**, ekip vermeli (§5.1'deki "⚠ şartname riski" notu da bu park hareketiyle
ilgili). Diğer 18 kapı testi + `algi.py`/`nisan.py` kendi testleri geçiyor.

### 12.4 APPLE TASARIM SİSTEMİ — arayüzün tamamı kite taşındı (20–21.09.2026)

Takım kararı: arayüz baştan sona **Apple macOS görünümüne** oturtulacak; "AI ile
üretilmiş" hissi veren rastgele renk/ölçü kalmayacak. Kaynak: takımın indirdiği
**Apple macOS 27 UI Kit** (Sketch, ~110 MB). Sketch dosyası aslında ZIP+JSON'dur;
değerler dosyadan **çıkarılarak** alındı, göz kararı yapılmadı.

**Yeni dosya: `app/tasarim.py` — görünümün TEK KAYNAĞI.** Renk, tipografi, ölçü,
yarıçap, cam efekti ve tüm QSS burada. `arayuz_qt.py` içinde artık elle yazılmış
renk/punto yok; eski sabitler (`TXT`, `MAVI`, `RED`…) korundu ama hepsi buraya
işaret ediyor (yüzlerce çağrı yerini değiştirmeden tek noktadan renk değişimi).

| Konu | Kitten gelen değer |
|---|---|
| Vurgu rengi | `System Colors/Dark 8 Blue` **#0091FF** (`T.AKSAN` — tek satır değiştirilerek marka mavisine dönülebilir) |
| Durum renkleri | Kırmızı #FF4245 · Yeşil #30D158 · Sarı #FFD600 · Camgöbeği #3CD3FE |
| Metin hiyerarşisi | `Labels/Dark`: beyaz %100 / %55 / %25 / %10 — başka gri YOK |
| Yüzeyler | `Fills/Dark`: beyaz %10/8/5/3/2. Kontrol zemini boşta %7, üstünde %10, basılı %16, pasif %3 |
| Pencere | `Window Backgrounds/Dark` **#1E1E1E** (eski lacivert gradyan kaldırıldı) |
| Tipografi | Apple metin rampası: Body 13 · Callout 12 · Subheadline 11 · Caption 10; SF Pro yoksa Inter/Segoe UI'ye düşer |
| Boyut rampası | Mini 16 · Small 20 · **Regular 24** · Large 28 · XL 36 px. Köşe: 4/5/6 px; **Large ve XL KAPSÜL** (macOS 26 "Liquid Glass"in imzası) |
| Group box | beyaz %3 dolgu, **12 px** yarıçap, **kenarlık yok** |
| Segmented | kapsayıcı beyaz %8; seçili segment dolu vurgu rengi |
| Anahtar (switch) | 54×24, tutamaç **32×20 kapsül** (artık daire değil), beyaz %85 |
| Kaydırıcı | oluk 6 px beyaz %10, tutamaç 20 px beyaz daire |
| Tooltip | #262626 %96, 11 px Medium |

**Liquid Glass — dürüst sınır:** gerçek cam efekti arka planı BULANIKLAŞTIRIR;
Qt stil sayfasında böyle bir özellik yok. Kitin reçetesindeki diğer katmanlarla
taklit ediliyor: yarı saydam gövde + üst kenar ışık çizgisi + kapsül geometri.
Yan yana koyunca fark görülür, tek başına bakınca aynı dili konuşur.

**Bu iş sırasında bulunan ve düzeltilen GERÇEK hatalar:**
1. **Kaydırıcılar açık gri kutu içinde duruyordu.** QSS'te yalnız alt bileşenler
   (`::groove`, `::handle`) tanımlanmış, bileşenin kendi zemini tanımlanmamıştı →
   macOS **yerel stili** arkaya gri dikdörtgen boyuyordu. Aynı sınıf hata
   açılır listelerde de vardı (§12.3). Ders: *bir bileşenin alt parçasını
   biçimlendiriyorsan gövdesini de biçimlendir.*
2. **Satır içi `setStyleSheet` ÇOCUKLARA da miras geçiyor.** Otonom paneldeki
   iki kart dolgusunu her etiket bir kez daha boyuyor, yarı saydam yüzeylerde
   bantlar oluşuyordu. Kartlar nesne adına (`#altkart`) taşındı.
3. **Ölü kod:** yasak-alan anahtarları için `setChecked` yoksa çalışacak yedek
   dallar, custom çizilen anahtarın üstüne kutu boyuyordu — silindi.

**Yeni kapı testi (`python app/tasarim.py`):** arayüzdeki her `setObjectName`
için stil sayfasında karşılık var mı diye bakar. Karşılığı olmayan bileşeni Qt
**yerel macOS stiliyle** çizer — koyu arayüzde açık gri bir kutu belirir, hata
vermez, sadece çirkinleşir. Testin gerçekten kırmızıya düştüğü doğrulandı.

⚠ **GÖRSEL DOĞRULAMA YARIM KALDI.** Manuel/Otonom/Aşama-1/ayar paneli ekranları
gerçek macOS'ta ekran görüntüsüyle karşılaştırılarak 5 tur düzeltildi; ardından
laptopun ekranı kapandığı için Qt pencere açamaz oldu (`no Qt platform plugin`)
ve **son tur (açı kartı yüzeyi, ikinci ayar paneli, durum noktaları, uygulama
fontu seçimi) yalnızca kod düzeyinde** yapıldı. Makine başına dönülünce
`Baslat.command` ile açıp gözden geçirilmeli.

---

## 13. Kod sadeleştirme (30.07.2026) — ne silindi, neden

Kullanıcı tespiti: kod bir yığın haline gelmişti; "elle yazsak asla koymayacağımız"
spekülatif parçalar birikmişti. Kural: **davranış değişmeyecek, sadece silinecek.**

**Ölü kod (hiç çalışmıyordu):**
- `arayuz_qt.py`'de `_asama1_panel()` **iki kez tanımlıydı** → Python ikincisiyle üzerine
  yazdığı için birincisi hiç çalışmıyordu. Gerçek hataydı, silindi.
- `est_distance` / `MENZIL` / `GERCEK_BOYUT` / `FOCAL_PX` — mesafe özelliği 18.07'de
  kapatılmış, kod 12 gün ölü durmuştu (bkz. §6 madde 4).
- `FLOOR`, `INFER_IMGSZ` — "geriye dönük uyumluluk" notu vardı, referans eden kimse yoktu.
- `GRAY` — yorumu bile "kullanılmıyor; ileride gerekebilir" diyordu.
- `renk_analizi.taraf_binary()` — uygulama `renk_oranlari()` kullanıyor; bu yalnızca kendi
  testinde geçiyordu.
- Kullanılmayan `QDialog`, `QSizePolicy` import'ları.
- `mesafe_kalibrasyon.py`, `kamera_tara.py` — hiçbir yerden çağrılmıyordu.

**Spekülatif kod (bir ihtiyaca değil "belki gerekir"e yazılmıştı):**
- `ES_ANLAM` eşanlamlı sözlüğü: `"quadcopter"`, `"rocket"`, `"fighter"`, `"jet"`, `"plane"`…
  Projede hiçbirinin karşılığı yok. **Asıl hata düzeltmesi kaldı** (bilinmeyen sınıf artık
  sessizce silinmiyor, ham adıyla çiziliyor); `kanonik()` yalnızca ad sadeleştirmesi yapıyor.
  Yeni model farklı ad kullanırsa `DISPLAY`'e **tek satır** eklenir.
- `tanila.py` teşhis aracı (319 satır) — istenmemişti, silindi.

**Tekrar (aynı şey birden çok yerde yazılmıştı):**
- Kaydırıcı stilinde iki neredeyse aynı CSS bloğu → tek şablon + iki renk takımı.
- D-pad'de dört neredeyse aynı CSS bloğu → tek şablon + dört renk takımı.
- Üç "yasak alan" bölümü (onay kutusu + min/max) → tek `_yasak_alan_bolumu()` kalıbı.
- `_ayar_yukle()` dosya yolunu tekrar yazıyordu → mevcut `_ayar_dosya()` kullanılıyor.
- `_manuel_kontrol_panel()` 379 satırdı → adlandırılmış alt kuruculara bölündü
  (`_dpad_sayfasi`, `_aci_gostergesi`, `_dpad_izgarasi`, `_adim_butonlari`,
  `_aci_ayar_sayfasi`, `_aci_durum_baslat`).

**Yorumlar:** "neden böyle yapıldı" açıklamaları KALDI (kodu okuyanın soracağı soru o).
Giden: uzun anlatı paragrafları, ölçüm günlüğü notları, plan maddesi atıfları (A1/C3 gibi —
kodu okuyan için anlamsız).

**Sonuç:** `app/` 4481 → 3697 satır · yorum oranı %19 → %18 · `algi.py` %28 → %21 ·
`nisan.py` %37 → %29.

### 13.1 İkinci tur (30.07.2026 — sadeleştirmenin denetimi)

Sadeleştirme adımı denetlendi: davranışsal regresyon çıkmadı, ama (a) düzeltilen bir
hatanın **kardeşi**, (b) bir şartname boşluğu ve (c) kuralın uygulanmadığı yerler bulundu.

**Gerçek hatalar (düzeltildi):**
1. **Ekran açısı ↔ cihaz hedefi kopması (B2'nin kardeşi).** `_aci_hareket` açıyı tilt
   limitine kırpıyor ama ESP32'ye **ham delta** gönderiyordu: 55°'de +8 istenince ekran
   60 derken cihazın hedefi 63 oluyordu. *(05.08.2026: mutlak açıya geçilince bu hata
   sınıfı yapısal olarak imkânsız hâle geldi — ekran ve komut tek kaynaktan türüyor.)*
2. **Eksen tanımı çelişkisi.** Arayüz tilt'i `0..60`, mock ESP32 pitch'i `-30..+30` idi —
   aynı ekseni iki farklı tanımlıyorlardı. Tek tanım: **0° = ufuk, + = yukarı, tavan 60°,
   negatif tilt YOK.** Bugün bu limit hem `protokol.py`'de hem firmware'de uygulanıyor.
3. **Atışa yasak alan ateş sırasında denetlenmiyordu.** `_ates_bas` yalnız butona basılan
   anı kontrol ediyordu; lazer açıkken bölgeye girmek serbestti. Ateşi kesmenin tek yolu
   artık `_ates_kes()`; hem yasak bölgeye girişte hem E-Stop'ta oradan geçilir.

**Kuralın uygulanmadığı yerler (tekrar → tek kalıp):** iki yasak alan kartı → `_yasak_kart()` ·
adım butonu iki CSS kopyası → tek şablon · `keyPress/keyRelease` iki tuş haritası → tek
`TUS_YON` sözlüğü · `_dpad_press/release` 5'er dal → `YON_TABLO`.

**Kalan spekülatif kod:** `_guzel_kamera_adi` 55 → 25 satır (EpocCam/Camo/OBS-özel/IR
dalları ve 16 kelimelik sonek listesi gitti; DroidCam/iVCam/Iriun kaldı — kamera darboğazında
telefonu webcam yapmak gerçek bir ihtimal). `kameralari_listele(haric=)` parametresi silindi.

**Tek kaynak (kırılmıştı):** `kp/kd/olu_bolge` varsayılanları üç yerde yazılıydı
(`algi.VARSAYILAN_AYAR`, `nisan.py` sabitleri, ayar tablosundaki `oneri` sütunu). Artık
**tek kaynak `algi.VARSAYILAN_AYAR`**: `nisan.py` oradan okur, ayar tablosundan `oneri`
sütunu kaldırıldı, kaydırıcının yeşil "önerilen" işareti doğrudan oradan türer.

**Yeni: `app/kapi_testleri.py`** — arayüzün `__main__`'i uygulamayı açtığı için güvenlik
kapılarının testi yoktu; oysa geçmişte hepsi en az bir kez sessizce bozuldu. Bu dosya
E-Stop, ateş, atışa/harekete yasak alan ve uygulanan-delta davranışlarını **pencere açmadan**
dener (`python app/kapi_testleri.py`). Testlerin gerçekten yakaladığı doğrulandı: düzeltme
geri alındığında kırmızıya düşüyor.

**Davranış korundu — nasıl doğrulandı:** temizlik öncesi/sonrası aynı 4 ekran (Manuel,
ayar paneli açık, Aşama 3, Aşama 2) yakalanıp **piksel piksel** karşılaştırıldı; tek fark
saatin ilerlemesiydi. CSS şablonları eski kopyalarla anlamsal olarak eşit çıktı (test edildi).
Tüm modül testleri + E-Stop/ateş/nişan kapıları başsız testle yeniden geçti.

---

## 11. Takım (KTR'den)

10 lisans öğrencisi. Roller: Kaptan (Makine), Organizasyon, Mekanik Tasarım, 3B Baskı,
Yapısal Analiz, Elektronik Entegrasyon, **Kullanıcı Arayüzü (Matematik)**, **Görüntü İşleme
(Matematik)**, **Otonom Takip (Bilgisayar)**, Sistem Entegrasyon Testleri (Bilgisayar).
Takım ID: 948118 · Başvuru ID: 5007261.

---

*Son güncelleme: 2026-08-13 (akşam) · Faz: Video hazırlığı · Durum: Sabah `hedeftakip`
branch'indeki arayüz/algı iyileştirmeleri `otonom_v4`'e taşındı — SAHI (dilimli tespit)
**bilinçli olarak hariç tutuldu** (takım kararı, bkz. §6 madde 11): HEDEFLER kartından
**elle hedef kilitleme** (`algi.hedef_sec`/`kilitli_hedef`), kilit koptuğunda **hayalet hedef**
ile kutu istikrarı, tespit tablosunun tıklanabilir **HEDEFLER kartına** dönüşmesi (yatay liste,
sıra sabit: Füze→Helikopter→F16→İHA), **lazer boresight/paralaks kalibrasyonu**
(`lazer_ofset_x/y` + Qt'de kırmızı referans nişangahı + cv2'de yeşil sabit merkez nişangahı),
"Aynala" (flip) özelliğinin kaldırılması. Ardından **OpenVINO export** ile CPU inference
~4→~15 FPS'e çıkarıldı (§6 madde 12) — ki bu, akşam bulunan iki otonom-takip sorununu ortaya
çıkardı/büyüttü: (a) PD'nin hız tavanı FPS'ten bağımsız değildi, motor hızına göre kırpma
eklendi + türev yumuşatması zaman-sabitli yapıldı (§7.1); (b) **asıl kök sebep**: sabah
taşınan "kendi IoU tracker'ımız" (`model.predict()`+`_iou_id_esle`) SAHI için gerekliydi ama
bu branch'te SAHI yok — otonom modda gimbal kendi hareketiyle görüntüyü kaydırınca hedef ID'si
kararsızlaşıp **"rastgele hareket, hedefi takip etmiyor"** sorununa yol açtı (manuel modda
görünmüyordu, çünkü orada otomatik kilit/nişan devrede değil). **ByteTrack'e (`model.track`)
geri dönüldü**, naif tracker tamamen silindi (§7.2). ByteTrack sonrası kullanıcı "artık takip
ediyor ama ortaladığında durmuyor, karşı tarafa geçip salınıyor" dedi — klasik gecikme
(dead-time) kaynaklı salınım: motor bir komutu yerine getirirken kamera görüntüsü henüz
güncellenmeden yeni kareler AYNI bayat hatadan komut üstüne komut biriktiriyordu. **"Meşgul
kapısı"** eklendi (`_nisan_geldi`): gönderilen komutun tahmini fiziksel tamamlanma süresi
kadar yeni komut kabul edilmiyor (§7.3). ⚠ Bu düzeltme simülasyonda yakınsamayı YAVAŞLATIYOR
(salınım yok ama daha temkinli) — gerçek donanımdaki salınımı laboratuvarda birebir yeniden
üretemedim, UART/inference gecikmesi gibi modellenmemiş etkenler de rol oynuyor olabilir.
Tüm modül testleri geçti; `analiz_et` gerçek OpenVINO modeliyle çok karelik duman testinden
geçti. **Hiçbiri gerçek donanımda (kamera/gimbal) test edilmedi** — bir sonraki iş budur;
"çok yavaş" hissettirirse `arayuz_qt.NISAN_MIN_ARALIK` ayarlanacak yer. Ardından: dwell
mantığı + Aşama-1 zarf sırasının bağlanması + gerçek veriyle 5 sınıflı model.*

*Önceki güncelleme: 2026-08-05 · Faz: Video hazırlığı · Durum: ESP32 İLETİŞİMİ GERÇEK FIRMWARE'E
GÖRE KURULDU (bkz. §5.1) — ekipten gelen AccelStepper kodu esas alındı: Python tarafı ASCII satır
komutlarına ve **mutlak açıya** taşındı (aynı gün yazılan binary/delta protokol karşılığı olmadığı
için atıldı). **3 kademe motor hız düzeyi** (S/A komutları: 150/100 · 400/200 · 800/400) eklendi;
arayüzde her iki modda görünen MOTOR HIZI kartı var. Azimut ekranda sarmalı, karta sürekli açı
gidiyor (350°→10° = `P370`). Firmware `esp32/derin_mavi_esp32/derin_mavi_esp32.ino` olarak repoya girdi ve dört
eksiği tamamlandı: lazer (L1/L0), STOP'ta lazer kesme, S (tavan hız) komutu, tilt yazılımsal limiti.
Aynı gün akşam **donanımsal acil stop butonu (GPIO 15, NO)**, **lazer (o gün GPIO 25 sanıldı;
06.08'de GPIO 18'e düzeltildi — S3'te 22-25 yok, bkz. §5.2/§5.3)** ve gerçek
mekanik değerleri geldi: sürücüler
**6400 step/tur**, yatay eksende **15→83 diş (5.53:1)** redüksiyon → hız komutu step/sn yerine
**derece/sn** oldu (iki eksenin oranı farklı; çevirimi kart yapıyor) ve kademeler pan ekseninin
step/sn tavanına göre yeniden seçildi (15/40/75 °/s). Butona basılınca kart **önce lazeri,
sonra hareketi, sonra sürücü ENABLE hatlarını (pin 16/17)** kesiyor; motorlar tutmuyor,
serbest kalıyor. Buton basılıyken `START` reddediliyor, bırakılınca sistem kendiliğinden
başlamıyor; DEVAM'da **mevcut konum sıfır kabul ediliyor** (hem kartta hem arayüzde). `kapi_testleri.py` mutlak açı
semantiğine göre yenilendi (+ sarmasız azimut, hız düzeyi, kartın kendi durması, donanım butonu);
kırık `AlgiThread` referansı `VideoThread` olarak düzeltildi.
Bir sonraki iş: gerçek portta uçtan uca deneme (ESTOP_PIN/ENA polaritesi/dikey dişli oranı
doğrulanacak) + homing + dwell mantığı + Aşama-1 zarf sırası + gerçek veriyle 5 sınıflı model.*

*Önceki güncelleme: 2026-07-30 · Durum: SADELEŞTİRME DENETLENDİ (bkz. §13.1) —
ekran açısı ↔ cihaz hedefi kopması (tilt limitinde ham delta), eksen tanımı çelişkisi (mock pitch
−30..30 vs arayüz 0..60) ve ateş sırasında atışa-yasak alan denetimi giderildi; kalan tekrarlar tek
kalıba indirildi; ayar varsayılanları tek kaynağa (`algi.VARSAYILAN_AYAR`) bağlandı; güvenlik
kapıları için `app/kapi_testleri.py` eklendi. Bir sonraki iş: dwell mantığı + Aşama-1 zarf sırasının
bağlanması + gerçek veriyle 5 sınıflı model.*

*Önceki güncelleme: 2026-07-29 · Durum: ALGI/ARAYÜZ SAĞLAMLAŞTIRILDI (bkz. §12) —
ham YOLO ile davranış farkı giderildi (sınıf beyaz listesi, ByteTrack yapılandırması, kamera gecikmesi,
görüntü kırpma, ayna), E-Stop artık hareketi de kesiyor, otonom nişan döngüsü (`nisan.py`) yazıldı.
30.07'de KOD SADELEŞTİRİLDİ (§13): ölü kod + spekülatif parçalar silindi, davranış birebir korundu
(ekran görüntüleri piksel piksel karşılaştırıldı). Bir sonraki iş: dwell mantığı + gerçek veriyle
5 sınıflı model (şu anki model yalnız 2 sınıf) + donanım gelince Kp/FOV kalibrasyonu.*

*Önceki güncelleme: 2026-07-24 · Durum: Proje GitHub public repo için temizlendi
(2 doküman: CLAUDE.md + README.md; model/veri/legacy Flask yedeğe taşındı, repo modelsiz gelir,
`models/` klasörüne konan best.pt otomatik bulunur). mock-ESP32 kontrol iskeleti çalışıyor (ATEŞ/E-Stop
arayüze bağlı), mesafe/menzil UI'ı gerçek ölçüm gelene kadar devre dışı. Model/veri current yaklaşımdan
vazgeçildi → gerçek veri gelince eğitilecek. Bir sonraki iş: repoyu GitHub'a push; paralelde gimbal
matematiği + yasak alan + gerçek mesafe ölçüm özelliği (kalibrasyon/derinlik).*
