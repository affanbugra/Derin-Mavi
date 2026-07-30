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
- **Kontrolcü:** ESP32, UART **115200 baud**, PySerial. Paket: `0xAA | mod | X | Y | ateş | XOR`.
  Mod 0=Manuel, 1=Otonom. Açı 0.1° çözünürlük. ESP32 geri: konum + durum (hazır/hareket/ateş/estop/hata).
- **İmha:** LaserTree 80W-AA-PRO lazer (24V, PWM tetik). Odak merceği 5–15 m için kalibre.
- **Güç:** Mean Well LRS-350-24 (24V). Buck → 5V (kamera+ESP32). E-Stop + şalter + sigorta.
- **Kontrol algoritması:** PD kontrol (piksel hatası → yaw/pitch); homing için limit switch.
- **Manuel kontrol:** USB gamepad (Aşama 1).
- **Otonom mod modelleri:** tespit YOLOv11 + takip (KTR: Macar/Hungarian ID eşleme + öngörülü kestirim).

**Güvenlik (şartname zorunlu):** harekete-yasak alan + atışa-yasak alan tanımı; sadece hedef
tarafına bakabilme; donanımsal E-Stop + yazılımsal E-Stop; homing ile bilinen başlangıç.

---

## 6. Mevcut yazılım ve KRİTİK BOŞLUKLAR (yapılacaklar)

> **GÜNCEL DURUM (24.07.2026 — GitHub temizliği):** Proje GitHub'a **public repo** olarak
> hazırlandı. Repo **modelsiz/verisiz** gelir; kamera + OpenCV çalışır. Model/veri seti current
> yaklaşımdan (düşük doğruluk) VAZGEÇİLDİ → gerçek veri gelince eğitilecek. Ağır/gizli her şey
> `d:\Masaüstü\Derin Mavi - YEDEK\`'e taşındı: `sentetik_veri/` (dataset+model+eğitim scriptleri),
> `Analiz/` (Şartname/KTR/parkur PDF — GİZLİ), `Modeller_Kil6t/` (3mf), `Arayuz_legacy/` (Flask).
> **Model artık `models/` klasörüne konur** → `arayuz_qt.py` `_model_bul()` otomatik bulur, kod
> değişmez. Model yoksa uygulama açılır, alt çubukta "Model yok" uyarısı çıkar.

**Var olan (temiz repo):**
- **ARAYÜZ (native, ANA):** `app/arayuz_qt.py` → PySide6 masaüstü kontrol istasyonu.
  Algı çekirdeği `app/algi.py` (kamera + YOLO + renk taraf = TEK KAYNAK). Tarayıcı/Flask
  GEREKTİRMEZ; ileride PyInstaller ile tek `.exe` → her laptopta kurulumsuz. Çalıştır: kökteki `Baslat.bat`.
- **Kontrol iskeleti:** `protokol.py` (UART) + `mock_esp32.py` + `kontrol.py`
  (`DERINMAVI_ESP=mock|COM<n>|off`). ATEŞ/E-Stop zinciri arayüze bağlı, donanımsız test edilebilir.
- **Model:** `models/` klasörü (repoda boş). Ekip kendi `best.pt`'sini buraya atar → otomatik yüklenir.
  Eski Flask arayüzü (`arayuz_app.py`) emekli edildi, yedeğe taşındı.
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
  ediyordu** (takip + ateş aynı anda çalışmıyordu). Delta artık **mevcut hedefe** eklenir,
  konuma değil. ⚠ **ESP32 C kodunu yazan arkadaş `protokol.py` başındaki DELTA SEMANTİĞİ
  notunu okumalı** — kural: `yeni_hedef = mevcut_hedef + delta`.

**Tasarım ilkesi (bundan sonra korunacak):** ayarların varsayılanları **Ultralytics'in kendi
varsayılanlarıdır.** Hiçbir kaydırıcıya dokunmayan biri, ham `yolo track source=0` ile aynı
davranışı görür. Kodun içinde gizli "iyileştirme" YOKTUR; sapmak isteyen **ayar panelinden** sapar.

**Bu makinede ölçülenler (29.07):** kamera 1280×720 @ **10 FPS** (YUY2; dahili kamera MJPG
desteklemiyor, çözünürlük düşürmek FPS'i ARTIRMIYOR — ölçüldü) · inference 640px'te ~20 FPS ·
**darboğaz KAMERA.** → Takip akıcılığı için **30 FPS'lik USB kamera** en yüksek getirili
donanım yatırımı. CPU tarafında OpenVINO (`yolo export ... format=openvino`) 2-3× ek pay verir;
`models/best_openvino_model/` varsa uygulama **otomatik** tercih eder.

**⚠ MODEL GERÇEĞİ:** `models/best.pt` şu an **yalnızca 2 sınıf** tanıyor: `fuze`, `helikopter`.
**F-16, İHA ve BALON modelde YOK → tespit edilemiyor.** Balon olmadığı için nişan noktası
gövde merkezine düşüyor (nişan zinciri hazır, balon gelince otomatik devreye girer).
Arayüz artık bu gerçeği alt çubukta açıkça yazıyor. Gerçek maket fotoğraflarıyla eğitilecek
yeni modelde **5 sınıfın tamamı** bulunmalı.

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

*Son güncelleme: 2026-07-29 · Faz: Video hazırlığı · Durum: ALGI/ARAYÜZ SAĞLAMLAŞTIRILDI (bkz. §12) —
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
