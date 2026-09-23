# models/ — Görüntü işleme modeli

Takımın ortak hedef ağırlığı **`models/best.pt`** olarak repoda durur. Ayrı bir balon
ağırlığı da aynı klasöre konabilir (ör. **`models/bestb2.pt`**); uygulama sınıf adlarına
bakarak iki modeli aynı kamera karesinde otomatik çalıştırır.

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
2. Ana hedef modeli için `models/` içinde sırayla:
   **`best.engine` → `best_openvino_model/` → `best.onnx` → `best.pt`**
3. Bunlar yoksa aynı sırayla ilk eşleşen `*.engine` / `*_openvino_model` / `*.onnx` / `*.pt`.
4. Ana model balon sınıfı içermiyorsa diğer ağırlıklar taranır; `balon`, `balloon`,
   `green-balloon`, `red-balloon` benzeri sınıfları içeren modeller ek balon modeli olur.

Ek balon modeli tam kareyi tek başına taramaz. Ana model önce bir F-16, helikopter, İHA veya
füze tanır; ardından balon modeli yalnızca bulunan maketin gövdesi ve altındaki sınırlı bölgede
çalışır. Bu bölgenin dışında kalan bağımsız balonlar gösterilmez. Aynı modelin `best.pt`,
`best.onnx`, `best.engine` gibi farklı çıktıları dosya adına göre tek aile sayılır ve gereksiz
yere iki kez belleğe alınmaz.

Balon **yalnız düşman hedefin altında** aranır (Aşama 3'te rengi "Dost" okunan makete ateş
edilmez; onun balonunu bulmak boşuna işlem demektir — Aşama 1–2'de taraf hiç okunmaz, her
hedefin altı taranır). Bulunan balon sadece çizilmez, **nişan noktası olur**: lazer balonun
merkezine kilitlenir, birden fazla aday varsa maketin asılma noktasına en yakın olan seçilir.
Balon bulunamazsa nişan eskisi gibi gövdeden kestirilir (`balon_ofset` ayarı).

Yalnızca `models/` **kökü** taranır — alt klasördeki model **bulunmaz**.

Hiç model yoksa uygulama yine açılır: kamera + OpenCV çalışır, sadece tespit yapılmaz ve
alt çubukta "Model yok" uyarısı görünür.

## ⚠ Şu anki modelin bildiği sınıflar

```
DRONE · F16 · FUZE · HELIKOPTER
```

**`balon` sınıfı ana modelde YOK.** Balonlar ayrı bir ağırlıktan da algılanıp canlı görüntüde
gösterilebilir. Alt çubuktaki sınıf özeti, yüklenen modellerin birleşik sınıf listesini yazar.

Yeni model eğitildiğinde **5 sınıfın tamamı** (`f16, helikopter, drone, fuze, balon`)
bulunmalı. Yeni `best.pt`'yi bu klasöre koyup commit'lemen yeterli; alt çubuk modelin
gerçekten kaç sınıf tanıdığını yazar.
