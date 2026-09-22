# v3 inceleme ve düzeltme

Kullanıcı bildirimi: W basılıyken kısa gidip duruyor, kalibrasyon çok yavaş.
Kök neden motion_core.h'deki pos+64 hedefi ve 100 darbe/s jog hızıydı.
Tekrarlanan W komutları hedefi uzatmıyordu; arayüz de W'yi yalnızca ilk basışta yolluyordu.

Düzeltme: kalibrasyonda sürekli jog, 50 ms yön yenilemesi ve firmware'de ayrı 250 ms
jog süresi. H mesajı tek başına jogu sürdürmez. Kayıtlı alt/üst sınırlar korunur;
kalibrasyon sırasında fiziksel üst sınır kullanıcı ölçümüyle belirlenir.
Normal jog 400, ince 100, hızlı 800 darbe/s; hedef üst hız 1600, ivme 3200 darbe/s².

Diğer bulgular/düzeltmeler:
- Arayüz kalibrasyon aktifken de 'Kalibrasyon gerekli' yazıyordu: açık aşama göstergesi eklendi.
- OK yanıtları işlenmiyordu: komut adıyla eşleşen ACK ve kayıt sonuç mesajları eklendi.
- Kontrol onayı için 300 ms tahmini gecikme vardı: OK,E beklenmeden K gönderilmez.
- DUR yalnızca PC'yi kapatıyordu: D firmware'i de kilitler.
- Kayıt hatası ardından OK basılabiliyordu: artık başarısız kayıt için OK gönderilmez.
- Yön her darbede tekrar kuruluyor, pulse yüksek süresi periyoda tekrar ekleniyordu:
  yön sadece değiştiğinde kurulur, aralık yükselen kenardan hesaplanır.

17 C++ test grubu ve 14 Python testi geçti. Testler gerçek kullanıcı akışını,
uzun basılı tutmayı, hız seçeneklerini ve zaman aşımını kapsıyor.
Motorun gerçek açı/hız ölçümü yapılmadı; enkoder hâlâ sadece HSD57'dedir.

İki USB soketi arasında port değişimi de gözlendi. UART0 ve yerel USB birlikte
desteklendi; seri giriş tamponları ayrıldı, hareket yetkisi tek porta verildi.
Arayüzde bağlı port ve Yeniden bağlan düğmesi eklendi; eski durum güncelmiş gibi gösterilmez.
5 .ino entegrasyon testi de geçti. COM4 yükleme/komut onayı ve COM3 durum akışı doğrulandı.
