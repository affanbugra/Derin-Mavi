# models/ — Görüntü işleme modeli

Takımın ortak hedef ağırlığı **`models/best.pt`**, balon ağırlığı **`models/bestb2.pt`**
olarak repoda durur. Uygulama sınıf adlarına bakarak iki modeli aynı kamera karesinde
otomatik çalıştırır.

## Repoda ne var, ne yok

| Dosya | Repoda? | Neden |
|---|---|---|
| `best.pt` | ✅ **var** | Ortak ağırlık. 18 MB, taşınabilir; her makinede aynı. |
| `bestb2.pt` | ✅ **var** | Balon modeli (YOLO11n, 5 MB, 640). Aşama 2/3'te kilit ve nişan buna dayanır. |
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

**Balon takibi (`app/balon_takip.py`, 24.09):** Aşama 2/3'te kilit ve nişan **balona**
kurulur; araç yalnız balonun kimliğini söyler. Balon modeli her karede tam kareyi ve (küçük
balonda) balonun çevresini büyüterek tarar — kare başına tek toplu çıkarım. Araç göründüğü
karelerde hemen altındaki balonun kimlik kartına taraf (gövde rengi) ve tip yazılır; araç
modeli okuyamazsa balonun hemen üstündeki gövdenin rengi taraf oyu verir (mavi öncelikli). Kart
bir kez kesinleşince araç görünmese de geçerlidir. Aşama 2'de her balon hedeftir, Aşama 3'te yalnız
kartı "Düşman" olan balona ateş edilir. Ateş edilen balon kaybolursa imha sayılır. Ayrıntı ve
eşikler modülün başında.

Balon modeli yoksa ya da ayar panelinde "Balon takibi" kapalıysa eski yol çalışır: araca
kilitlenilir, balonun yeri gövdeden kestirilir (`balon_ofset`). Aynı modelin `best.pt`,
`best.onnx`, `best.engine` gibi farklı çıktıları dosya adına göre tek aile sayılır ve gereksiz
yere iki kez belleğe alınmaz.

Yalnızca `models/` **kökü** taranır — alt klasördeki model **bulunmaz**.

Hiç model yoksa uygulama yine açılır: kamera + OpenCV çalışır, sadece tespit yapılmaz ve
alt çubukta "Model yok" uyarısı görünür.

## ⚠ Şu anki modelin bildiği sınıflar

```
DRONE · F16 · FUZE · HELIKOPTER
```

**`balon` sınıfı ana modelde YOK** — balonu `bestb2.pt` tanır (`green-balloon`,
`red-balloon`; ikisi de "balon" sayılır, şartname: balon rengi değişebilir, hepsi aynı renkte).
⚠ Balon modeli renge çok dayanıyor: düzensiz kırmızı bir leke de %93 "balon" çıkabiliyor;
koridor videosunda (24.09) gri cam kapıyı %57, kırmızı tişörtü ve zemindeki yansımayı da
"balon" buldu. `balon_takip` bunlara karşı kırmızı oranı + en/boy süzgeci, gövde ve dikey
devir kurallarını uygular. Küçük balonu **büyütülmüş pencerede** iyi görür (128 px pencere).
⚠ Aynı videoda altında drone asılı ~18 m'deki balonu hiçbir ölçekte görmedi — yeniden eğitimde
bu tür kareler (uzak, gövdeye yapışık balon) eklenmeli. `best.pt` el yapımı drone/F16'yı da
neredeyse hiç okumadı. Alt çubuktaki
sınıf özeti, yüklenen modellerin birleşik sınıf listesini yazar.

Yeni model eğitildiğinde **5 sınıfın tamamı** (`f16, helikopter, drone, fuze, balon`)
bulunmalı. Yeni `best.pt`'yi bu klasöre koyup commit'lemen yeterli; alt çubuk modelin
gerçekten kaç sınıf tanıdığını yazar.
