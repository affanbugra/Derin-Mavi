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
