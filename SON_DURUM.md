# Derin Mavi — Son Durum

Tarih: 22 Eylül 2026
Çalışma dalı: `final_v2`

## Bu aşamada yapılanlar

- Affan arayüzü ile çoklu hedefli takip sistemi birleştirildi.
- Arayüzden Füze, Helikopter, F-16 ve İHA hedef tipi seçilebiliyor.
- Tilt operatör açısı fiziksel olarak `−30° … +30°`; etkin çalışma sınırı `−25° … +25°` olarak tanımlandı.
- Fiziksel tilt kartı açısı `0° … 60°`; operatör `0°`, fiziksel kolun `30°` konumuna karşılık geliyor.
- Pan çalışma sınırı `−60° … +60°`. Arayüzün hareket pencereleri açılışta bu pan ve tilt sınırlarıyla etkin geliyor; otonom takip de aynı sınırları kullanıyor.
- Kullanıcı fiziksel kolu mekanik alt konuma aldıktan sonra ESP sayacı `R` komutuyla sıfırlandı.
- Gerçek kartla fiziksel `30°` konumuna çıkış doğrulandı; kart `30.000°` bildirdi.
- Açılış yükseltmesindeki hata düzeltildi: kart ilk `STATE3` paketinde hazır değilse `G30` komutu kaybolmuyor, kart hazır olana kadar bekleniyor.
- E-Stop basılırsa bekleyen açılış yükseltmesi iptal ediliyor.
- Açılış davranışı için regresyon testi eklendi.
- Düzeltilmiş açılış akışı gerçek ESP32-S3 üzerinde yeniden doğrulandı: 23:04:56'da `G30.0000` kabul edildi; 23:04:57'de kart fiziksel `30.000°` konumunda durdu.

## Donanım testleri

Bağlı donanım:

- ESP32-S3: `COM3`
- Kamera: `OBSBOT Meet SE StreamCamera`
- Lazer: bağlı değil / testlerde kullanılmadı.

Son güvenli başlangıç testi:

1. Tilt kolu fiziksel alt konuma alındı.
2. Kart açısı `6.872°` iken `R` ile sıfırlandı.
3. Kart `0.000°` bildirdi.
4. `G30.0000` gönderildi.
5. Kart `30.000°` konumuna ulaştı ve durdu.

## Kamera ve hedef tespiti

Fiziksel `30°` kol konumunda, yaklaşık 2–3 m mesafedeki helikopter için 10 saniyelik pasif test:

- Kamera: yaklaşık 29.6 FPS
- İşlenen kare: yaklaşık 29.6 FPS
- Tespitli kare: `%100`
- Gerçek kilit: `%99.3`
- Helikopter kutu sayısı: `299`
- Kilit güveni medyanı: `%84`
- Analiz medyanı: `14.3 ms`

Başlangıç alt konumunda helikopter kadrajın üstünde kesildiği için model helikopteri kilitleyemedi. Bu nedenle hedefin ilk görüntüde kadrajda olması için açılışta fiziksel 30° yükselme zorunlu hale getirildi.

## Takip testleri

İlk geniş takip testinde hedef kaybı ve açı salınımı görüldü:

- 40 örneğin 10'unda kilit korundu.
- Tilt yaklaşık `-6.9° … +6.3°` arasında değişti.

Dar hareket sınırlarıyla tekrarlanan testte:

- 25/25 örnekte helikopter kilidi korundu.
- Pan aralığı: yaklaşık `5.39° … 5.78°`
- Tilt aralığı: yaklaşık `-3.27° … -1.60°`
- Büyük salınım oluşmadı.

### Son gerçek zamanlı tekrar (22 Eylül 2026, 23:07 sonrası)

- Açılış düzeltmesinin donanım doğrulamasından sonra kamera ile 6 saniyelik pasif ölçüm yapıldı: yaklaşık 29.5 FPS, `%100` tespitli kare, `%98.9` gerçek kilit, helikopter güveni medyan `%84`.
- Pan `0…12°`, tilt `−5…+5°` sınırındaki 10 saniyelik otonom takipte 50 örneğin 39'unda helikopter kilidi vardı. Pan `0.417…10.776°`, tilt `−4.591…+1.615°` arasında dolaştı. Son bölümde kilit kayboldu; sistem durduruldu.
- Durduktan sonra yapılan 4 saniyelik pasif ölçümde helikopter yeniden `%98.3` gerçek kilitle görüldü. Bu gözlem, kaybın özellikle hareket sırasında oluştuğuna işaret ediyor; tek başına kök nedeni kanıtlamıyor.
- Pan `0…10°`, tilt `−4…+4°` sınırındaki 6 saniyelik tekrar testinde 30/30 örnekte gerçek helikopter kilidi ve anlık kırmızı kanıtı korundu. Son tilt yaklaşık `−1.17°` idi.
- Testten sonra tilt fiziksel `30.000°` / operatör `0°` konumuna geri alındı; kart durur durumda. Lazer kullanılmadı.

### Geniş hareket alanı doğrulaması (22 Eylül 2026)

- Arayüz ve hareket kapısı varsayılanları pan `−60°…+60°`, tilt `−25°…+25°` olarak güncellendi. Otonom tilt üst sınırı eski `+18°` değerinden `+25°` değerine çıkarıldı.
- Bu tam alan açıkken sabit helikopterle 8 saniyelik gerçek zamanlı takipte `40/40` örnekte kilit korundu. Pan `3.883°` civarında kaldı; tilt `−8.327°…−4.093°` aralığında hareket edip `−7.58°` civarında yerleşti.
- Yavaş hızdaki manuel uç nokta testinde kart pan `+59.998°` ve `−59.998°`, tilt `+25.004°` ve `−24.992°` bildirdi. Her uçtan sonra `0°` operatör konumuna dönüldü.
- Son pasif ESP durumu: pan `0.000°`, tilt fiziksel `30.000°` / operatör `0°`; motorlar hareketsiz ve kontrol kapalı. Lazer kullanılmadı.
- Kart açıları darbe sayacından hesaplanır; bağımsız konum sensörü olmadığından mekanik açı ayrıca ölçülmedi.

Bu sonuç, titreşimin yalnızca sensör gürültüsü olmadığını; hedef kaybı, görüş alanı ve takip komutlarının birlikte değerlendirilmesi gerektiğini gösteriyor. Yarışma öncesi farklı mesafe ve hedef tiplerinde tekrar edilmelidir.

## Saha verileri

Kareler ve takip ölçümü şu klasörde tutuluyor:

`PROJE/Saha_Verisi/2026-09-22_helikopter_2-3m/`

İçerik:

- `01_alt_konum_hedef_kesik.jpg`: alt konumda helikopterin kesildiği görüntü.
- `02_kol_30_hedef_gorunur.jpg`: fiziksel 30° konumunda hedefin görünür olduğu görüntü.
- `03_takip_hit.jpg`: dar sınır takip testinde hedef kilitliyken alınan görüntü.
- `takip_testi.json`: takip açıları ve kilit sonuçları.
- `README.md`: veri kullanım notları.

Bu kareler etiketlenmeden model eğitiminde doğrudan kullanılmamalıdır. Önce insan doğrulamalı bounding-box etiketleri oluşturulmalı, tekrar kareler temizlenmeli ve eğitim/doğrulama ayrımı yapılmalıdır. Görüntülerde kişi bulunduğundan GitHub'a yüklemeden önce izin ve anonimleştirme kontrolü yapılmalıdır.

## Test sonucu

Çalıştırılan regresyon testi:

```text
python app/kapi_testleri.py
Birlesik arayuz kapi testleri OK
```

## Bilinen kalan işler

- Kamera kare alım zaman damgası hâlâ kare tüketim zamanına yakın hesaplanıyor; yakın mesafe takipte bu gecikme ayrıca ölçülüp düzeltilmeli.
- Takip kaybında güvenli durma ve yeniden kilitlenme davranışı farklı hedef tiplerinde test edilmeli.
- Helikopter, füze, F-16 ve İHA için gerçek saha görüntülerinden ayrı etiketli eğitim/validasyon veri seti hazırlanmalı.
- Yakın mesafede önceki uzun testte görülen aralıklı kilit kaybı için kamera zaman damgası, takip ivmesi ve gecikmesi incelenmeli. Yeni tam alanlı 8 saniyelik test kararlı geçti; daha uzun ve hareketli hedef testleri hâlâ gerekli.

## Git kapsamı

`final_v2` dalı açılış düzeltmesini, pan/tilt çalışma sınırlarını, testleri ve bu durum notunu içerir. `PROJE/Saha_Verisi` klasöründeki saha fotoğrafları Git deposunun dışında tutulur.

## 23 Eylül 2026 — takip sağlamlaştırma çalışması (devam ediyor)

- Birleşik Qt arayüzünde kare zamanı, kameranın callback anı yerine video/GUI thread'inin
  kareyi tükettiği anda yazılıyordu. Kare ve zaman damgası artık kamera kaynağında aynı
  kilit altında tutuluyor; takip yolu atomik `(kare, sıra, zaman)` okuyor. Böylece GUI veya
  inference yükünün değişmesi motor açısı–görüntü eşleşmesine değişken gecikme eklemiyor.
- Aynı çözünürlükte 60 FPS istenirken 150 FPS profiline yönelen format seçimi düzeltildi;
  istenen FPS'e en yakın desteklenen profil seçiliyor. Kamera açılış mesajı seçilen profil
  FPS'ini de gösteriyor.
- `app/kamera_pasif_test.py` eklendi. ESP, model ve lazeri açmadan birleşik arayüzün Qt kamera
  yolundaki gerçek çözünürlük, callback FPS, kare yaşı ve parlaklığı ölçüyor.
- Yazılım regresyonları geçti: `kamera.py`, `hedef_kestirici.py`, `algi.py`, `tilt_surucu.py`,
  `kontrol.py`, `nisan.py`, `protokol.py`, `kapi_testleri.py`, `tilt_takip_testi.py` ve tüm
  `ws_motor_test` C++/firmware testleri.
- ESP32-S3 `COM3` salt okunur teşhiste konuşuyor ve 7 noktalı kalibrasyon geçerli. Kart
  operatör `−30°` / fiziksel kol `0°` bildiriyor; hareket komutu gönderilmedi ve test sonunda
  kontrol kapatıldı.
- Gerçek takip testi henüz tamamlanmadı: Windows aygıt durumu OBSBOT Meet SE kamerayı
  `Disconnected` gösteriyor. İlk OpenCV pasif okumadan sonra kamera hem OpenCV hem Qt cihaz
  listesinden kayboldu. Kamera fiziksel olarak yeniden bağlanıp Windows'ta görünmeden motorlu
  takip testi yapılmayacak.

## 23 Eylül 2026 (öğleden sonra) — kod incelemesi, tilt salınımı düzeltmesi, kamera bulguları

### Güvenlik testleri geri getirildi (`app/kapi_testleri.py`: 5 → 19 test)

- Affan arayüzüyle birleştirmede eski arayüzün 23 kapı testinden 5'i kalmıştı. Kalanlar
  sahte bir kontrol nesnesi kullandığı için komutun karta gerçekten gidip gitmediğini
  ölçmüyordu. `kapi_testleri_eski_arayuz.py` artık hiç çalışmıyor (eski arayüz API'si yok).
- 13 yeni test, **gerçek `Kontrol` katmanı + sahte kartlarla** çalışır: E-Stop (hareket ve
  ateş), donanım butonu yazılımdan kaldırılamaz, lazer ölü adam anahtarı, lazer kapalıyken
  tazeleme gitmez, ateş kısayolu E-Stop'u aşamaz, kartın kendi durması, otonom ateşte anlık
  kırmızı kanıtı şartı, E-Stop'ta ve Aşama 1'de otonom ateş yok, operatör açısı → kol açısı,
  sürekli takip (konum kipi / yörünge kipi / hareketli hedef).
- Davranışın kendisi birleştirmeden sonra da doğruydu; eksik olan testlerdi.
- Testlerin gerçekten yakaladığı doğrulandı: güvenlik kodu çalışma anında 10 farklı şekilde
  bozuldu, 9'u yakalandı; kaçan tekinde lazer başka bir katman (kartın E-Stop bildirimi)
  sayesinde yine sönük kaldı.
- Test çalıştırıcısı artık ilk hatada durmuyor; tüm testleri koşup kalanları listeliyor.

### Tilt salınım riski: boşluk modeli ve "duran hedef" kararı (`hedef_kestirici.py`)

**Ne bulundu.** Takip testlerine sahada ölçülen tespit gürültüsü (1.5 px) eklenince, kontrolcü
dişli boşluğunu **gerçekte olduğundan büyük sandığında** yörünge kipinde tilt duran hedef
etrafında sönmeyen salınıma giriyor: ~2.6° (kamera açısı) tepe-tepe, ~1 sn periyot.
Konum kipinde hiç olmuyor.

**Ne kadar gerçek.** ⚠ Arayüzün kendi ayarıyla (`takip_bosluk` 0.8) eski kod da salınmıyor
(8/8 temiz). İlk ölçümde "18 koşunun 9'u salınıyor" sonucu, testin yanlışlıkla sınıfın
varsayılan boşluğunu (1.5) kullanmasından geliyordu; test artık arayüzle aynı değeri kullanıyor.
Risk şurada: kontrolcü boşluğu çalışırken **kendisi öğreniyor** ve bu değer 3°'ye kadar
büyüyebiliyordu. Öğrenilen boşluk büyürse eski kod salınıma girebilir.

**Kök sebep (iki parça).**
1. Boşluk modeli basamak şeklindeydi (`ofset = yön × boşluk/2`): motor yön değiştirdiği
   AN ofset bir uçtan öbür uca sıçrıyordu. Gerçekte namlu sıçramaz; motor önce boşluğu
   kapatır. Sahte sıçrama Kalman'a "hedef kaydı" diye giriyor, hız kestirimi fırlıyor,
   yörünge kipi motoru o hızla sürüp yönü yine çeviriyordu.
2. "Duran hedef" kipine geçiş ANLIK hıza bakıyordu. Salınım hız kestirimini ±5°/s'de
   tuttuğu için geçiş hiç olmuyordu.

**Yapılan üç değişiklik.**
- Boşluk için standart **play modeli**: namlu motorun ±boşluk/2 bandında kalır, ofset sıçramaz.
- Duran hedef kararı hızın kısa pencere **ortalamasına** bakar (giriş 0.5 sn, çıkış 0.2 sn).
  Salınımın ortalaması sıfırdır; gerçekten hareket eden hedefin hızı aynı işarette kalır.
- Öğrenilen boşluğa **1.0° tavan** (eskiden 3.0°). Sahada ölçülen: tilt 0.1–0.9°, pan 0.2–0.7°.

**Ölçüm (boşluk 1.5 varsayımı, −15° ve −5°, 4'er tohum):**

| | salınım |
|---|---|
| eski kod | 6/8 |
| yalnız play modeli | 3/8 |
| play + ortalama hız (şu anki) | 2/8 |
| arayüz ayarında (0.8), üçü de | 0/8 |

Gerçek el hareketi izinde (22.09 kaydı, motor boşluğu 0 / 0.4 / 0.9°) hareketli hedef hatası
değişmedi (yavaş 9.9 → 9.8 px, normal 35.0 → 35.1 px). Boşluklu "titreyen duran hedef"
benzetiminde hata 2.3 → 1.9 px, sarsıntı 12 → 8. Regresyon testi:
`test_surekli_takip_bosluk_buyuk_sanilirsa` (eski kodla kalıyor, yenisiyle geçiyor).
Sahada görülen tilt salınımının (22.09) bu mekanizma olduğu **kanıtlanmadı**.
**Gerçek kartta doğrulandı (COM3, gerçek arayüz takip kodu, sanal hedef + 1.5 px gürültü,
tilt operatör −20 → −12, pan 0 → 4, 8'er sn):**

| | tilt tepe-tepe (kamera) | son tilt hatası |
|---|---|---|
| yeni kod, arayüz ayarı (0.8) — 2 tur | 0.00° / 0.00° | −0.01° / −0.14° |
| yeni kod, boşluk 1.5 | 0.00° | +0.02° |
| **eski kod, boşluk 1.5** | **1.70° salınım** | −0.38° |

Salınım gerçek motorda da oluştu; yeni kod gideriyor. Test sonunda kol operatör −20°'de
(kol 10°) bırakıldı, kart kilitlendi (D).

### Kamera: yeni arayüz 30 FPS'te ve pozlamayı ayarlayamıyor

Ölçüldü (OBSBOT Meet 2, 1280×720):

| Yol | FPS | Pozlama |
|---|---|---|
| Qt (`kamera.py`, birleşik arayüz) | **30** (60 FPS'lik format seçilse bile) | ayarlanamıyor: `ExposureManual` desteklenmiyor |
| OpenCV DSHOW + MJPG (`algi.open_camera`, test araçları) | **60** | −7 (7.8 ms) ayarlanıyor |

- OpenCV'nin ayarladığı pozlama **kamerada kalıcı**: kamera kapatılıp ayarsız açılınca, hatta
  Qt ile açılınca da korunuyor (parlaklık 131 → 73–85). Yani test araçlarından biri
  (`uzak_mesafe_testi.py` ya da `tilt_canli_takip.py`) bir kez çalıştırılırsa arayüz de kısa
  pozlamayla açılır. Kamera güç kesilince (USB çıkarılınca) ayar sıfırlanabilir.
- 30 FPS pozlamadan bağımsız: Qt'nin Media Foundation yolu bu kamerada 60'a çıkmıyor.
  Kalıcı çözüm: arayüzün kamera kaynağını OpenCV (DSHOW + MJPG) ile açmak — ölçülü takip
  60 FPS ve kısa pozlama alır. Saha testinden sonra yapılmalı; şimdilik ölçülü takip testleri
  için `tilt_canli_takip.py` önerilir (OpenCV yolu, 60 FPS).

### Açık kalanlar

- Dokümanlar (`CLAUDE.md`, `README.md`, `ENTEGRASYON.md`, `FINAL_ENTEGRASYON.md`) çalışma
  kopyasında silinmiş; kasıtlı olup olmadığı kullanıcıya soruldu. Bu commit'e silme
  **dahil edilmedi**, depoda duruyorlar.
- Arayüz kamerasının OpenCV'ye geçirilmesi (60 FPS + pozlama).
