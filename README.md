# DERİN MAVİ — Görev Kontrol İstasyonu

TEKNOFEST Çelikkubbe Hava Savunma Sistemleri yarışması için geliştirilen **görüntü işleme +
kontrol arayüzü**. Native masaüstü uygulaması (PySide6); kamera akışı üzerinde YOLO tabanlı
hedef tespiti, renkten dost/düşman ayrımı ve gimbal/lazer kontrol iskeleti içerir.

> **Model repoda geliyor** (`models/best.pt`) — klonla, kur, çalıştır; ayrıca bir şey indirmen
> gerekmez. Veri seti ve türetilmiş model biçimleri (`.onnx`, `.engine`) repoya girmez.

---

## Özellikler

- **Canlı kamera akışı** — donanım bağımsız; kamera otomatik bulunur, arayüzden seçilebilir
  (`DERINMAVI_CAM` env ile de zorlanabilir: index / dosya / RTSP-URL).
- **YOLO hedef tespiti** — tip tespiti (F-16 / Helikopter / İHA / Füze) + balon (nişan noktası).
- **Renkten dost/düşman ayrımı** — HSV ile kırmızı = düşman, camgöbeği (cyan) = dost.
  Deterministik ve açıklanabilir; tip değil **renk** tarafı belirler.
- **Çalışma modları** — Manuel (Aşama 1) / Otonom (Aşama 2-3), aşamaya duyarlı görev paneli.
- **Kontrol iskeleti** — UART protokolü + mock ESP32 (donanımsız uçtan uca test).
  ATEŞ ve **Acil Durdur (E-Stop)** zinciri arayüze bağlı.
- **Modelsiz de çalışır** — model silinse bile kamera yine akar, alt çubukta "Model yok" uyarısı görünür.

---

## Kurulum

Gereksinim: **Python 3.10+** (3.12/3.14 test edildi).

```bash
# 1) Repoyu indir
git clone <REPO_URL>
cd "Derin Mavi"

# 2) (Önerilir) sanal ortam
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

# 3) Bağımlılıklar
pip install -r requirements.txt
```

## Çalıştırma

**Windows (en kolay):** repo kökündeki **`Baslat.bat`** dosyasına çift tıkla.

**Her platform (terminal):**
```bash
python app/arayuz_qt.py
```

---

## Model

Ortak ağırlık **`models/best.pt`** repoda gelir — bir şey yapmana gerek yok, uygulama açılınca
otomatik yüklenir. Tanıdığı sınıflar: `DRONE`, `F16`, `FUZE`, `HELIKOPTER`
(**`balon` henüz yok** — nişan noktası şimdilik gövde merkezine düşüyor).

**Hızlandırmak istersen** (opsiyonel — asıl darboğaz inference'tır) kendi makinende bir kez
çevir, çıktıyı `models/` içine bırak, uygulama otomatik tercih eder:

```bash
yolo export model=models/best.pt format=engine     # NVIDIA GPU varsa
yolo export model=models/best.pt format=openvino   # GPU yoksa, Intel CPU'da 2-3x
```

⚠ Ürettiğin `.engine`/`.onnx` dosyalarını **commit etme** — `.engine` senin GPU'na ve
TensorRT sürümüne bağlıdır, başka makinede açılmaz. `.gitignore` zaten engelliyor.

Öncelik sırası ve ayrıntı: [models/README.md](models/README.md).

---

## Ortam değişkenleri (opsiyonel)

Hiçbiri zorunlu değildir; hepsinin makul otomatik varsayılanı vardır.

| Değişken | Ne işe yarar | Örnek |
|---|---|---|
| `DERINMAVI_CAM` | Kamera kaynağını sabitler (yoksa otomatik tarama) | `0`, `video.mp4`, `rtsp://...` |
| `DERINMAVI_MODEL` | Belirli model dosyası / ONNX seçer | `onnx`, `C:\yol\best.pt` |
| `DERINMAVI_ESP` | Kontrolcü hedefi | `mock` (varsayılan), `COM5`, `off` |
| `DERINMAVI_FOCAL` | Mesafe kalibrasyon odak (piksel) | `900` |

---

## Proje yapısı

```
Derin Mavi/
├── Baslat.bat              # ÇALIŞTIR — Windows'ta çift tıkla
├── README.md               # bu dosya (ekip için özet)
├── CLAUDE.md               # proje beyni (detay, yol haritası, kararlar)
├── requirements.txt        # bağımlılıklar
├── app/                    # uygulama kodu
│   ├── arayuz_qt.py        #   ANA uygulama (native PySide6 kontrol istasyonu)
│   ├── algi.py             #   Algı çekirdeği: kamera + YOLO + karar (tek kaynak)
│   ├── nisan.py            #   Nişan matematiği: piksel hatası → gimbal açı komutu
│   ├── renk_analizi.py     #   HSV ile dost/düşman (renk tarafı)
│   ├── kontrol.py          #   Yüksek seviye kontrol API'si
│   ├── protokol.py         #   ESP32 satır komutları + hız düzeyi (tek kaynak)
│   ├── mock_esp32.py       #   Sahte ESP32: 2 step motor + lazer (donanımsız test)
│   ├── kapi_testleri.py    #   Güvenlik kapıları testi (E-Stop / ateş / yasak alan)
│   └── Grafik/             #   Logo + arayüz ikonları
├── esp32/                  # Kart tarafı firmware (Arduino IDE / AccelStepper)
│   └── derin_mavi_esp32/   #   Arduino kuralı: klasör adı = .ino adı
│       └── derin_mavi_esp32.ino
└── models/                 # Ortak model — best.pt repoda gelir (.onnx/.engine girmez)
```

---

## Donanım mimarisi (özet)

```
Kamera → Laptop (görüntü işleme + karar) → UART 115200 → ESP32 → 2 step motor + lazer
```

ESP32'ye bağlı olanlar: **pan (yatay) step motoru** (STEP 6/DIR 7/ENABLE 16, 15→83 diş =
5.53:1 redüksiyon), **tilt (dikey) step motoru** (STEP 4/DIR 5/ENABLE 17), **acil stop butonu**
(GPIO 15, normalde açık — basılınca LOW) ve **lazer** (GPIO 18, PWM). Sürücüler 6400 step/tur.
Firmware AccelStepper kullanır ve ASCII satır komutları konuşur:

| Komut | Anlamı |
|---|---|
| `P<derece>` / `T<derece>` | pan / tilt **mutlak** hedef açısı (`P45.00`) |
| `S<derece/sn>` / `A<derece/sn²>` | tavan hız / ivme — hız düzeyi |
| `G<yüzde>` | lazer **gücü** (%0–100, kalıcı) — varsayılan %40, tam güç kullanılmıyor |
| `L1` / `L0` | lazer aç / kes (ayarlı güçte) — `L1` **250 ms'de bir tazelenir**, aşağıya bak |
| `STOP` / `START` | acil durdur (lazer + sürücü ENABLE kesilir) / devam |

Protokolün tek kaynağı [app/protokol.py](app/protokol.py); kart tarafı
[esp32/derin_mavi_esp32/derin_mavi_esp32.ino](esp32/derin_mavi_esp32/derin_mavi_esp32.ino). Biri değişirse diğeri de değişmeli.
Hız **derece/sn** olarak gönderilir; step'e çevirmek kartın işidir (iki eksenin dişli oranı farklı).

**USB gamepad:** Takılıysa otomatik bulunur (uygulama açıkken takarsanız ~2 sn içinde) ve
alt çubukta adı görünür. Sol çubuk / D-pad — gimbal · **A** — ateş aç/kes · **Y** — merkeze
al · **LB/RB** — motor hız kademesi · **Start** — ACİL DURDUR / DEVAM. Buton düzeni SDL
tarafından standarda eşlenir, yani Xbox/PlayStation fark etmez. Teşhis: `python app/gamepad.py`.
Gamepad yoksa uygulama normal çalışır, yalnızca bu özellik kapalı kalır.

**Klavye:** `W/A/S/D` veya ok tuşları — gimbal yönü (basılı tutunca sürekli hareket) ·
`R`/`C`/`Space` — merkeze al · **`L` — ateşi aç/kes.** `L` her iki modda çalışır; ATEŞ butonu
manuel panelde durduğu için Otonom modda görünmez, ama lazeri kesme yolu moda bağlı olmamalı.
E-Stop'ta buton kilitliyse `L` de geçmez — kısayolun butondan fazla yetkisi yoktur.

**Lazer gücü:** arayüzdeki *LAZER* kartından ayarlanır (hem Manuel hem Otonom modda) —
kaydırıcı %0–100 veya hızlı kademeler (%20/%40/%70/%100). Varsayılan **%40**; tam güç
kullanılmıyor. Güç ile ateş ayrı şeylerdir: kart `G<yüzde>` ile "ne kadar"ı, ATEŞ butonu
`L1/L0` ile "ne zaman"ı söyler — bu yüzden **ateş sürerken güç değiştirilebilir.**
⚠ Düşük güç *dwell* süresini uzatır (%40'ta balon ~2,5 kat geç patlar) ve süre puana bağlıdır.

**Motor hız düzeyi (3 kademe):** arayüzdeki *MOTOR HIZI* kartından seçilir (hem Manuel hem
Otonom modda) — Yavaş 15°/s (hassas nişan) · Normal 40°/s · Hızlı 75°/s (geniş tarama).
Tavanı yatay eksen belirler: 98.4 step/derece nedeniyle 75°/s bile ~7400 step/sn demektir.

**Lazer güvenliği (üç katman).** ⚠️ Lazer yüksek güçlüdür; test/çekimde **gözlük zorunlu.**
1. Kart açılışta lazer pinini ilk iş olarak LOW'a çeker — ama reset anında pin kısa süre
   *float* kalır, buna yazılım müdahale edemez: **sinyal hattına 10 kΩ pull-down (GPIO 18 ↔ GND)
   takın** ve firmware yüklerken lazerin beslemesini kapatın.
2. Ateşin tek yolu arayüzdeki **ATEŞ** butonudur; E-Stop, atışa-yasak alan ve kartın kendi
   durması ateşi keser. Kart, E-Stop'tayken `L1` komutunu hiç işlemez.
3. **Ölü adam anahtarı:** lazerin açık kalması için arayüz 250 ms'de bir "hâlâ açıksın" der.
   1 sn bu gelmezse **kart lazeri kendi keser** — kablo koparsa/uygulama donarsa "kes" komutu
   zaten gidemeyeceği için lazer yanık kalmasın diye.

**Acil durdurma:** basılınca kart önce **lazeri** (GPIO 18) keser, **pan'ı olduğu yerde
kilitler**, **tilt'i 0° park konumuna indirir** (lazerli namlu yukarıda asılı kalmasın) ve
tüm komutları reddeder. ⚠ **Sürücü ENABLE hatları KESİLMEZ — motorlar tutar.** Kapalı çevrim
sürücüde ENABLE kesilirse mil kayar, sürücü ENABLE geri gelince biriken pozisyon hatasını
kendi maksimum hızıyla kapatır ve gimbal aniden fırlar (sahada yaşandı). Motorlar tuttuğu
için mil kaymaz, dolayısıyla **açı referansı da korunur** — DEVAM'da sıfırlama yapılmaz.
Buton bırakılınca sistem kendiliğinden başlamaz; arayüzden *DEVAM ET* gerekir (buton
basılıyken yazılımdan devam **edilemez**).

Açılar **mutlaktır** (delta değil): kaybolan bir komut kalıcı sapma yaratmaz ve ateş komutu
süregelen hareketi bozmaz. Azimut ekranda 0–360 gösterilir ama karta **sürekli** açı gider
(350°→10° geçişinde `P370`), yoksa motor kısa yoldan dönmez.

Yazılım **donanım bağımsız** yazılmıştır: gerçek ESP32 yokken `mock` ile uçtan uca test edilir.
Gerçek donanım gelince `DERINMAVI_ESP=COM<n>` yeterlidir, uygulama kodu değişmez.

### Kart tarafı: Arduino IDE kurulumu

1. **Arduino IDE 2.x** kurun.
2. *File → Preferences → Additional boards manager URLs* alanına ekleyin:
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`
3. *Boards Manager*'dan **esp32 (Espressif Systems)** paketini kurun. **Uyarı:** derleyici
   zinciri ~400 MB, yavaş bağlantıda saatler sürebilir.
4. *Library Manager*'dan **AccelStepper**'ı kurun (firmware'in tek harici bağımlılığı).
5. `esp32/derin_mavi_esp32/derin_mavi_esp32.ino` dosyasını açın, kart olarak
   **ESP32S3 Dev Module** seçin (takımın kartı **ESP32-S3**'tür — klasik "ESP32 Dev Module"
   ile yüklenmez) ve yükleyin. *"USB CDC On Boot"* kapalı kalmalı: kart laptopa harici
   CH343 (UART0) çipi üzerinden bağlı, açılırsa `Serial` USB'ye gider ve laptop hiçbir şey
   duymaz.

Doğrulanan ortam: esp32 core **3.3.11** + AccelStepper **1.64.0**; `esp32:esp32:esp32s3` için
uyarısız derlenir (324 KB flash / %24, 22 KB RAM / %6) ve karta yüklenip laptopla konuşması
test edilmiştir.

---

## Katkı ve ekip çalışması (ÖNEMLİ)

- **Doğrudan `main`'e push YOK.** Her geliştirme alt branch'te yapılır, `main`'e almadan önce
  **Pull Request açılır ve ekibe sorulur** ("herkesin haberi var mı, emin miyiz?"). En az 1
  kişi onaylamadan merge edilmez. Kural detayı: [CLAUDE.md → Ekip Çalışma Kuralları](CLAUDE.md).
- **Her PC'de çalışsın:** makineye özel mutlak yol yazma; yeni kütüphane kullandıysan
  `requirements.txt`'e ekle. Kodda her yol `__file__`'a görelidir → indir-çalıştır.
- Model dosyaları (`*.pt`, `*.onnx`) ve veri setleri `.gitignore` ile repoya **girmez** —
  herkes kendi modelini lokalde tutar veya ekiple ayrı bir kanaldan paylaşır.
- **Push'tan önce testleri çalıştır** (donanım/kamera gerektirmez, saniyeler sürer):
  ```bash
  python app/protokol.py && python app/renk_analizi.py && python app/mock_esp32.py
  python app/kontrol.py && python app/nisan.py && python app/algi.py
  python app/kapi_testleri.py     # E-Stop / ateş / yasak alan güvenlik kapıları
  ```
  Her modül kendi kendini test eder; `kapi_testleri.py` ise şartnamenin can alıcı
  davranışlarını (E-Stop hareketi keser, yasak açıda ateş verilmez) pencere açmadan dener.

---

## Daha fazlası

Projenin tüm detayı — amaç, şartname özeti, hedef/dost-düşman kuralları, puanlama, mimari,
kararlar ve yol haritası — tek yerde: **[CLAUDE.md](CLAUDE.md)** (proje beyni).
