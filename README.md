# DERİN MAVİ — Görev Kontrol İstasyonu

TEKNOFEST Çelikkubbe Hava Savunma Sistemleri yarışması için geliştirilen **görüntü işleme +
kontrol arayüzü**. Native masaüstü uygulaması (PySide6); kamera akışı üzerinde YOLO tabanlı
hedef tespiti, renkten dost/düşman ayrımı ve gimbal/lazer kontrol iskeleti içerir.

> Bu repo **modelsiz ve verisiz** gelir. Kamera + OpenCV çalışır durumdadır; görüntü işleme
> için kendi eğittiğin YOLO ağırlığını `models/` klasörüne eklemen yeterlidir (aşağıya bak).

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
- **Modelsiz çalışma** — model yoksa kamera yine akar, alt çubukta "Model yok" uyarısı görünür.

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

## Modelini ekleme (görüntü işlemeyi aktif etme)

Uygulama **`models/`** klasörüne konan YOLO ağırlığını otomatik bulur:

1. Kendi modelini eğit (detaylı yol haritası: [CLAUDE.md](CLAUDE.md)).
2. `best.pt` dosyasını `models/` klasörüne kopyala → `models/best.pt`
3. Uygulamayı başlat. Model otomatik yüklenir, tespit başlar. **Kod değişmez.**

Detay ve öncelik sırası: [models/README.md](models/README.md).

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
│   ├── renk_analizi.py     #   HSV ile dost/düşman (renk tarafı)
│   ├── kontrol.py          #   Yüksek seviye kontrol API'si
│   ├── protokol.py         #   UART paket protokolü (XOR checksum)
│   ├── mock_esp32.py       #   Sahte ESP32 (donanımsız test)
│   ├── mesafe_kalibrasyon.py  # Monoküler mesafe kalibrasyon yardımcısı
│   ├── kamera_tara.py      #   Kamera teşhis aracı
│   └── Grafik/             #   Logo + arayüz ikonları
└── models/                 # Eğitilmiş model buraya (repoda boş gelir)
```

---

## Donanım mimarisi (özet)

```
Kamera → Laptop (görüntü işleme + karar) → UART → ESP32 (motor + lazer) → 2 eksen gimbal + lazer
```

Yazılım **donanım bağımsız** yazılmıştır: gerçek ESP32 yokken `mock` ile uçtan uca test edilir.
Gerçek donanım gelince `DERINMAVI_ESP=COM<n>` yeterlidir, uygulama kodu değişmez.

---

## Katkı ve ekip çalışması (ÖNEMLİ)

- **Doğrudan `main`'e push YOK.** Her geliştirme alt branch'te yapılır, `main`'e almadan önce
  **Pull Request açılır ve ekibe sorulur** ("herkesin haberi var mı, emin miyiz?"). En az 1
  kişi onaylamadan merge edilmez. Kural detayı: [CLAUDE.md → Ekip Çalışma Kuralları](CLAUDE.md).
- **Her PC'de çalışsın:** makineye özel mutlak yol yazma; yeni kütüphane kullandıysan
  `requirements.txt`'e ekle. Kodda her yol `__file__`'a görelidir → indir-çalıştır.
- Model dosyaları (`*.pt`, `*.onnx`) ve veri setleri `.gitignore` ile repoya **girmez** —
  herkes kendi modelini lokalde tutar veya ekiple ayrı bir kanaldan paylaşır.

---

## Daha fazlası

Projenin tüm detayı — amaç, şartname özeti, hedef/dost-düşman kuralları, puanlama, mimari,
kararlar ve yol haritası — tek yerde: **[CLAUDE.md](CLAUDE.md)** (proje beyni).
