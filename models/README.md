# models/ — Görüntü işleme modeli

Takımın ortak YOLO ağırlığı **`models/best.pt`** olarak repoda durur. Klonlayınca gelir,
hiçbir şey indirmen gerekmez — uygulamayı başlat, model otomatik bulunur.

## Repoda ne var, ne yok

| Dosya | Repoda? | Neden |
|---|---|---|
| `best.pt` | ✅ **var** | Ortak ağırlık. 18 MB, taşınabilir; her makinede aynı. |
| `best.onnx` / `best_openvino_model/` | ❌ yok | `best.pt`'den üretilir, repoda tutmak tekrar olur. |
| `best.engine` | ❌ yok | **TensorRT çıktısı GPU modeline, TensorRT sürümüne ve sürücüye bağlıdır — başka makinede açılmaz bile.** Herkes kendisi üretmeli. |

## Hızlandırma — kendi biçimini üret

Model `.pt` hâlinde de çalışır; aşağıdakiler yalnızca **hız** içindir (asıl darboğaz CPU/GPU
inference'ı). Bir kez çevir, `models/` içine bırak, uygulama otomatik tercih eder:

```bash
# NVIDIA GPU varsa (en hızlısı):
yolo export model=models/best.pt format=engine

# GPU yoksa, Intel CPU'da tipik 2-3x:
yolo export model=models/best.pt format=openvino
```

⚠ Ürettiğin `.engine` / `.onnx` dosyalarını **commit etme** — `.gitignore` zaten engelliyor.

## Uygulama modeli nasıl bulur? (öncelik sırası)

1. `DERINMAVI_MODEL` env değişkeni: bir **dosya yolu** ya da kısayol
   (`engine` / `trt`, `openvino`, `onnx`, `pt` / `torch`).
2. Aksi halde `models/` içinde sırayla:
   **`best.engine` → `best_openvino_model/` → `best.onnx` → `best.pt`**
3. Bunlar yoksa aynı sırayla ilk eşleşen `*.engine` / `*_openvino_model` / `*.onnx` / `*.pt`.

Yalnızca `models/` **kökü** taranır — alt klasördeki model **bulunmaz**.

Hiç model yoksa uygulama yine açılır: kamera + OpenCV çalışır, sadece tespit yapılmaz ve
alt çubukta "Model yok" uyarısı görünür.

## ⚠ Şu anki modelin bildiği sınıflar

```
DRONE · F16 · FUZE · HELIKOPTER
```

**`balon` sınıfı YOK.** Nişan noktası balon olmalı (maketlerin altında, bkz. CLAUDE.md §7);
balon tespit edilemediği için nişan şimdilik gövde merkezine düşüyor. Nişan zinciri hazır —
balonlu model gelince kod değişmeden devreye girer.

Yeni model eğitildiğinde **5 sınıfın tamamı** (`f16, helikopter, drone, fuze, balon`)
bulunmalı. Yeni `best.pt`'yi bu klasöre koyup commit'lemen yeterli; alt çubuk modelin
gerçekten kaç sınıf tanıdığını yazar.
