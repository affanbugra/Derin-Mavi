# Derin Mavi — final_v1 birleşmesi

Kaynaklar: görünüm, açı karoları, izinli hareket/atış pencereleri, oyun kolu ve
harici kamera katmanı `Affan-arayuz-aci-ikon`; algılama, dört hedef tipi süzgeci,
ölçümlü pan/tilt kontrolü, yörünge takibi ve ESP32-S3 firmware'i
`codex/coklu-hedef-tilt-v1` dalından alınmıştır. Affan dalındaki eski `kontrol.py`,
`algi.py`, `protokol.py` ve `esp32/` sürümleri bu birleşmeye taşınmamıştır.

## Çalışan bağlantı

`app/arayuz_qt.py` → `app/algi.py` → `app/nisan.py` / `app/hedef_kestirici.py`
→ `app/kontrol.py` → `app/tilt_surucu.py` → `ws_motor_test/` firmware'i.
Eski ayrı pan kartı kullanılıyorsa pan komutları `app/protokol.py` üzerinden
o karta gider. Yeni ESP32-S3 `PAN1` bildiriyorsa pan ve tilt aynı kartta
geri bildirimli takip ve `Y`/`PY` yörünge komutlarıyla yürür.

Görünüm `app/tasarim.py`, `app/kol_ikon.py`, `app/bolge.py` ve
`app/Grafik/arac_*.png` varlıklarını kullanır. Kamera `app/kamera.py` üzerinden
harici aygıtlara veya `DERINMAVI_CAM` ile dosya/akış kaynağına bağlanır.
Algı ve görüntü iş parçacıkları son kareyi paylaşır; kamera ölçüm zamanı
pan/tilt geri bildiriminde kullanılır.

## Operatör davranışı

- `ARANAN` satırında füze, helikopter, F-16 veya İHA seçilir. Hiçbiri seçili
  değilse tüm tipler otomatik kilit için uygundur. Seçim tüm tespitleri gizlemez.
- Tilt ekranda ve `Kontrol` API'sinde −30…+30°'dir; 0° yere paraleldir.
  Kartın 0…60° ham açısına dönüşüm yalnız `tilt_surucu.py` içindedir.
  Başlangıç ölçümü alındığında, kol en altta ise ilk görüntü için 0°'ye çıkar.
- Pan arayüzde yapısal ±90° ile sınırlıdır; Affan'ın izinli hareket/atış
  pencereleri bu sınırı yalnız daraltır. Mevcut açı pencere dışındaysa kart
  referansı sıçratılmaz; güvenli tarafa küçük adımlarla dönülür.
- E-Stop ve lazer kesme ortak kapılardan geçer. Otonom ateş için mevcut karede
  kırmızı hedef kanıtı gerekir; hayalet hedef veya eski sınıf belleği yeterli
  değildir. Lazer açıldıktan sonra kanıt kaybolursa kesilir.
- Tilt kartına 100 ms aralıkla nabız gönderilir; arayüz donarsa bu nabız da
  durur ve firmware'in kendi zaman aşımı koruması çalışır.

## Başlatma ve doğrulama

Windows'ta `Baslat.bat` ayrı pan kartı varsa onun portunu, ardından ESP32-S3
portunu sorar. Yeni tek-kart kurulumunda pan portu boş bırakılır; tilt portu
`auto` olabilir. Donanım olmadan `DERINMAVI_ESP=off`, `DERINMAVI_TILT=off`
ile arayüz açılabilir. Model ağırlığı `models/best.pt` altında bulunur.

Donanım gerektirmeyen testler:

```
python app/bolge.py
python app/algi.py
python app/hedef_kestirici.py
python app/tilt_surucu.py
python app/kontrol.py
python app/nisan.py
python app/protokol.py
python app/tilt_takip_testi.py
python app/kapi_testleri.py
```

`app/kapi_testleri_eski_arayuz.py` önceki arayüzün API'sine göre yazılmış
regresyonların tarihsel kopyasıdır; yeni arayüzün çalıştırılabilir kapı testleri
`app/kapi_testleri.py` içindedir.

Gerçek motor/lazer üzerinde uçtan uca doğrulama yapılmadı. İlk fiziksel denemede
lazer beslemesi kapalıyken açılış hizalaması, −30/0/+30, ±90, E-Stop,
izinli pencereler ve kamera-motor işaret yönleri ayrı ayrı kontrol edilmelidir.
Modelin tüm sınıfları ve yarışma menzilleri, sahada ölçüm olmadan doğrulanmış
sayılmamalıdır.
