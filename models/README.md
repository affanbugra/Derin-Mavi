# models/ — Eğitilmiş model buraya

Bu klasör repo ile **boş** gelir. Görüntü işleme modeli (YOLO ağırlığı) burada durur.

## Modelini nasıl eklersin?

1. Kendi modelini eğit (Colab / lokal — bkz. [ROADMAP.md](../ROADMAP.md)).
2. Eğitim çıktısındaki **`best.pt`** dosyasını bu klasöre kopyala:
   ```
   models/best.pt
   ```
3. Uygulamayı başlat. Model **otomatik** bulunur — hiçbir kod değişikliği gerekmez.

## Uygulama modeli nasıl bulur? (öncelik sırası)

1. `DERINMAVI_MODEL=<dosya yolu>` env değişkeni varsa → o dosya.
2. `DERINMAVI_MODEL=onnx` → `models/best.onnx`.
3. Aksi halde `models/` içinde sırayla: `best.pt` → `best.onnx` → ilk `*.pt` → ilk `*.onnx`.

Hiçbir model yoksa uygulama yine açılır: **kamera + OpenCV çalışır**, sadece tespit
yapılmaz ve alt çubukta "Model yok" uyarısı görünür.

## Not

- Model dosyaları (`*.pt`, `*.onnx`) `.gitignore` ile repoya **girmez** — herkes kendi
  modelini lokalde tutar. Bu dosya (`README.md`) ve `.gitkeep` klasörün var olması için kalır.
- ONNX kullanacaksan `best.onnx` dosyası `best.pt` ile **aynı eğitimden** olmalı.
