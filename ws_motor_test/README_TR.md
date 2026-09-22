# Kamera kolu v3 — ESP32-S3 / HSD57

Encoder HSD57'de kalır. ESP32 GPIO4=PULSE, GPIO5=DIR.
Sürücü 6400 pulse/motor turu ayarında olmalı. ESP32 PID veya gerçek açı ölçümü yapmaz;
hedef darbeleri ivmeli üretir. Ekrandaki açı kalibrasyondan hesaplanan konumdur.

## Bu sürümde düzelen sorun

Önceki kalibrasyon her basışta 64 darbede duruyor, 100 darbe/s ile çok yavaş ilerliyordu.
Artık W/S basılı tutuldukça hareket devam eder; tuş bırakılınca durur.
PC, basılı tutulan yönü 50 ms'de bir yeniler. Yön yenilemesi 250 ms kesilirse firmware
kontrolü kapatır; yalnızca H canlılık mesajı gelmesi jog hareketini sürdüremez.
Bütün hareketlerde 350 ms bağlantı zaman aşımı ayrıca korunur.

Jog seçenekleri: İnce=100, Normal=400 (varsayılan), Hızlı=800 darbe/s.

Hedef hareketi üst hızı ve ivmesi **artık sabit değil**: `Z<hız>,<ivme>` komutuyla
çalışma anında değiştirilir (100–5000 darbe/s, 200–60000 darbe/s²), böylece hız
denemesi için her seferinde yeniden yükleme gerekmez. Açılış değerleri
**3200 darbe/s ve 12800 darbe/s²** (eskiden 1600 / 3200 idi).

⚠ Asıl fark ivmeden gelir: tepe hıza çıkma süresi = hız/ivme. Eskiden 0.5 s idi,
yani kısa hareketlerde tepe hıza **hiç** ulaşılmıyor, hareket ağır hissettiriyordu.
Şimdi 0.25 s. Ölçülen kalibrasyonla (60° = 2675 darbe) 0→20° hareketi
1.04 s yerine 0.53 s sürer.

Bunlar hâlâ motor/yük üzerinde optimum ayar değildir. 6400 pulse/tur ile 400 darbe/s,
22.5 derece/s MOTOR hızıdır; kol hızı mekanizma oranına bağlıdır. Tavan 5000 darbe/s'de
tutuldu çünkü darbeler yazılımla üretiliyor ve gerçek darboğaz ESP32'nin döngü hızıdır —
mekanik değil (2675 darbe/60° ile 3200 darbe/s yalnızca ~30 rpm motor hızıdır).

## Çalıştırma

1. Kol her açılış, reset ve yüklemede fiziksel olarak en aşağıdaki 0° konumunda olmalı.
   Firmware sayacı açılışta 0 kabul eder; otomatik homing ve otomatik hareket yoktur.
2. Firmware: `esp32_ws_test/esp32_ws_test.ino`, yanında `motion_core.h`.
   Arduino ESP32 kart paketi gerekir, ek hareket kütüphanesi gerekmez.
3. Bu sistemin son bağlantısı ESP32-S3 yerel USB-Serial/JTAG üzerinden COM3'tür.
   Arduino IDE: ESP32S3 Dev Module, USB Mode=Hardware CDC and JTAG,
   USB CDC On Boot=Enabled. Son firmware aynı anda UART0/COM4 soketini de destekler;
   soket değişimi için yeniden derleme gerekmez. İki porttan eşzamanlı kontrol engellenir.
   Port numarası değişirse arayüzde Yeniden bağlan düğmesini kullan; hareket otomatik açılmaz.
4. Arduino Seri Monitörünü kapat. Aynı seri portu iki uygulama açamaz.
5. Bu klasörde:

```text
python -m pip install -r requirements.txt
python keyboard_control.py --port COM3
```

Tek port varsa `python keyboard_control.py` veya `BASLAT.cmd` yeterlidir.
V3 arayüz ve v3 firmware birlikte kullanılmalı; eski STATE protokolü reddedilir.

## İlk kalibrasyon

1. Kol altta, darbe sayacı 0 iken “Kontrolü aç”, ardından “0 konumunda kalibrasyona başla”.
   Onay sorusunu yalnızca kol fiziksel olarak alttaysa kabul et.
2. Ekranda **Kalibrasyon AKTİF** görünmesini bekle. Böylece komutun alındığı doğrulanır.
3. İlk yön kontrolünde İnce hızla W/Yukarı düğmesine çok kısa basıp bırak.
   Doğru yönü fiziksel olarak gözle. Ters yön varsa dur; DIR_UP_HIGH düzeltilip
   fiziksel alttan yeniden başlatılmalı. Motoru enerjiliyken zorlayarak döndürme.
4. Yön doğruysa dururken Normal veya Hızlı seç. W basılıyken kesintisiz yükselir;
   bıraktığında durur. S ile aşağı düzeltilebilir, sayaç 0'ın altına inmez.
5. Kol açısını haricen ölç. Bir ara noktadaysan örneğin 10 yazıp kaydet.
   **“10 derece noktası kaydedildi”** mesajını ve nokta sayısının arttığını gör.
   Bir sonraki önerilen değer otomatik artırılır. Ara noktalar isteğe bağlıdır.
6. Kol gerçekten 60° olduğunda dur, 60 kaydet. “Kalibrasyon tamamlandı ve kaydedildi”
   mesajıyla işlem biter; tablo ESP32'nin kalıcı belleğinde saklanır.
7. Hedef kutusuna 10/30 gibi bir açı yazıp dereceye git düğmesine bas.

Sadece 0 ve 60 noktalarıyla kalibrasyon yapılabilir; bu yöntem arayı doğrusal varsayar.
Fotoğraftaki mekanizma doğrusal olmayabilir. Doğru ara açı hedefleri için ölçülmüş
10,20,30,40,50 gibi noktalar önerilir. Maksimum 16 nokta (0 dahil), açı ve darbe sayıları
artan sırada olmalı. Motor mikrostep ayarı veya mekanizma değişirse kalibrasyonu yenile.

Kalibrasyon sırasında üst sınır henüz bilinmez. Sürekli jog otomatik 60° koruması
sağlamaz; kolu izleyerek ilerle ve dayamaya yük bindirme. 60° sert mekanik dayamaysa
ölçüm ve güvenli çalışma payı ayrıca belirlenmeli. 58° konuma 60° etiketi yazmak tüm
hedef ölçeğini bozar. İki uç veya çok nokta kalibrasyonu mekanik esnemeyi ölçmez.

## Kalibrasyon yeniden başlatma

Sayaç sıfır değilken K/yeni kalibrasyon reddedilir; hareket ortasında sayacı sıfırlayıp
sınırları kaydırmaz. Mevcut kalibrasyon oturumunda S ile alt sayaca dönüp dur,
kolun da gerçekten altta olduğunu doğrula; sonra yeni kalibrasyonu başlat.
Fiziksel konum ile sayaç uyuşmuyorsa hareketi durdur; fiziksel alt referansı yeniden
kurmadan dereceye gitme. Kartı kol yukarıdayken resetlemek doğru sıfır oluşturmaz.

## Durdurma ve davranış

- Tuş bırakma, iki tuş birlikte, DUR, Space/Esc ve pencere odağı kaybı hareketi durdurur.
- DUR ve odak kaybı D komutuyla firmware'i de anında kilitler; tekrar Kontrolü aç gerekir.
- Jog yenilemesi 250 ms, bütün canlılık 350 ms kesilirse kilitlenir. USB gecikmesiyle
  birlikte uçtan uca kesin fiziksel durma süresi garantisi değildir.
- PC 600 ms durum veya kontrol açma onayı alamazsa kontrolü kapatır.
- Normal hedef duruşunda yavaşlama vardır. X/D/zaman aşımı yeni darbeleri hemen keser;
  mekanik anlık durma garanti edilmez. Sert duruş sonrası fiziksel konum kontrol edilmeli.
- Her çevrimde en fazla bir darbe üretilir. Gecikmeler toplu darbe patlamasıyla telafi edilmez.
- Hareket sırasında yeni hedef gelirse mevcut hedefte durup en son bekleyen hedefe gider.
  Sürekli kamera takibi için kesintisiz yeniden planlama henüz yoktur.
- ENA ve alarm geri bildirimi bağlı değildir. Darbe kesilmesi tutma torkunu kapatmaz.
- STEP yüksek darbe 20 us, yön kurulum süresi 20 us. Yön yalnızca gerektiğinde değiştirilir.
  Darbe aralığı yükselen kenardan ölçülür, pulse süresi aralığa ikinci kez eklenmez.
  Gerçek giriş seviyesi/polaritesi kendi sürücü arayüzüyle doğrulanmalıdır.
- Yazılım hâlâ loop tabanlıdır; yük altında maksimum hız ve titreşim motor üzerinde ölçülmeli.

## Seri protokol (115200, ASCII satır + LF)

E: kontrol aç (OK,E gelmeden arayüz hareket göndermez).
D: durdur ve kontrolü kapat. X: durdur, bekleyen hedefi iptal et.
H: canlılık. W/S: jog ve jog süresini yenile.
V100/V400/V800: yalnızca dururken jog hızı.
Z<hız>,<ivme>: yalnızca dururken hedef hareketi profili (darbe/s, darbe/s²).
K: sayaç 0 ve dururken kalibrasyon başlat (önceki tablo silinir).
C10/C60: ölçülen noktayı kaydet, 60 tamamlar. G10/G30: derece hedefi.

Yanıt: OK,komut veya ERR,komut,neden. H/W/S için başarılı yanıt gönderilmez.
STATE3,pos,target,upper,cal,moving,armed,commissioning,angle,goal,count,last_angle,speed
Firmware kayıt hatasında başarı yanıtı göndermez. Arayüz hataları Türkçe açıklar.
Protokol yerel USB içindir, CRC/oturum kimliği yoktur.

## Test

```text
python -B -m unittest discover -s tests -p test_keyboard.py -v
run_cpp_tests.cmd
```

17 C++ test grubu: 300 rastgele hedef, sınırlar, zaman sayacı taşması, 64-darbe
regresyonu, uzun basılı tutma, H gelirken W kaybı, durdurma ve kalibrasyon/yeniden başlatma.
14 Python testi: kontrol onayı sıralaması, kayıt sonucu, tuş yenileme/bırakma,
bağlantı hatası ve eski firmware reddi.
Simülasyonda ilk saniyede İnce=99, Normal=381, Hızlı=711 darbe üretildi.
1600 darbeli hedef, eski profille (1600/3200) ~1.50 s; yeni açılış profiliyle
(3200/12800) ~0.78 s sürer. Test bu süreyi sabitlerden **türetir**, elle yazmaz —
hız değiştirilince kendini günceller. Bunlar gerçek motor ölçümü değildir.

⚠ `Z` komutu eklendikten sonra `run_cpp_tests.cmd` **yüklemeden önce** çalıştırılmalı.

## Son gerçek kart doğrulaması

Son firmware ESP32-S3 core 3.3.11 ile derlendi ve COM4 üzerinden yüklendi; flash hash
doğrulaması geçti. COM4 üzerinden E/V400/D komut onayları doğrulandı. COM3 yerel USB
üzerinden ayrıca beş düzenli STATE3 mesajı alındı. Bu aşamada motor hareketi verilmedi.
5 ek firmware entegrasyon testi gerçek .ino kodunu sahte seri/bellek/GPIO ile çalıştırdı:
sürekli jog, iki port yetkisi, bellek hatası, taşan satır ve jog süresi kontrol edildi.
