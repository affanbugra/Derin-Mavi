// MUZIK (muzik.h) gercek firmware'le birlikte: MZ<n> komutu, MZK1 yayini. Kanitlanan:
// MZ1 ile HEMEN calar, notalar dogru sira ve surede, loop'u BEKLETMEZ (kol hareketi +
// nabiz surer), TILT YORUNGESINI KESMEZ (bilinmeyen komut keserdi), lazer cikisina
// dokunmaz, ACIL DURDUR'da susar, acil kilitliyken calmaz, lazerle ayni LEDC
// zamanlayicisina dusecekse hic kurulmaz. Sarkilar test sarkilaridir (stubs/test_sarkilari.h);
// gercek notalar yerel sarkilar.h'de, repoda yok.
#include "stubs/Arduino.h"
#include <assert.h>
#include <cstdlib>
#include <iostream>
#include <vector>
uint32_t fakeUs=0;
int physicalPulses=0;
int panPulses=0,panDirLevel=-1,panEnLevel=-1;
int lazerCikis=0,estopSeviye=HIGH;
bool ledcBasarili=true;
int buzzerFrek=0,buzzerZamanlayici=1,tonDegisimi=0;
Stream Serial,Serial0;
#define MUZIK_SARKI_DOSYASI "test_sarkilari.h"
#include "../esp32_ws_test/esp32_ws_test.ino"

void reset(){motion=MotionCore{};owner=-1;inputs[0]=PortInput{};inputs[1]=PortInput{};Serial=Stream{};Serial0=Stream{};prefs.fail=false;prefs.clear();fakeUs=0;physicalPulses=0;pan=PanCore{};yorTilt=Yorunge{};yorPan=Yorunge{};panEnable=-1;panPulses=0;panDirLevel=-1;panEnLevel=-1;lazerYuzde=40;lazerAcik=false;lazerPwmHazir=true;acilKilit=false;estopButon=false;sonAtesMs=0;lazerCikis=0;estopSeviye=HIGH;ledcBasarili=true;
  buzzerFrek=0;buzzerZamanlayici=1;tonDegisimi=0;muzik::hazir=false;muzik::sira=-1;muzik::calan=0;}
void command(Stream& port,const char* s){port.incoming+=s;port.incoming+='\n';while(port.available())readSerial(&port==&Serial?0:1);}

std::vector<std::pair<uint32_t,int>> kayit;   // (an us, yeni ton)
// us boyunca loop; 100 ms'de bir H nabzi, istenirse 250 ms'de bir L1 tazelemesi.
void kos(uint32_t us,bool lazer=false){
  uint32_t bit=fakeUs+us,h=fakeUs,l=fakeUs; int son=buzzerFrek;
  while(fakeUs<bit){
    if(fakeUs-h>=100000){command(Serial,"H");h=fakeUs;}
    if(lazer && fakeUs-l>=250000){command(Serial,"L1");l=fakeUs;}
    loop(); fakeUs+=50;
    if(buzzerFrek!=son){kayit.push_back({fakeUs,buzzerFrek});son=buzzerFrek;}
  }
}
bool var(const Stream& s,const char* t){return s.out.find(t)!=std::string::npos;}

int main(){
  // 1. Kurulum + MZ1 -> ilk nota HEMEN; durum yayini ne caldigini soyler
  reset(); muzik::kur(LAZER_PIN); assert(muzik::hazir);
  command(Serial,"E"); assert(buzzerFrek==0);
  kos(150000); assert(var(Serial,"MZK1,0,2,1"));
  command(Serial,"MZ1"); assert(var(Serial,"OK,MZ1")); assert(buzzerFrek==880 && muzik::calan==1);
  Serial.out.clear(); kos(150000); assert(var(Serial,"MZK1,1,2,1"));
  std::cout<<"MZ1 -> sarki hemen basliyor, MZK1 yayini calani soyluyor: passed\n";

  // 2. Adimlar: ayni nota tekrari 12 ms boslukla ayri duyulur; sus tek adim
  { const muzik::Adim bek[]={{880,288},{0,12},{880,288},{0,12},{0,200},{1047,388},{0,12}};
    assert(muzik::ADET==7);
    for(int i=0;i<7;++i) assert(muzik::ADIMLAR[i].frekans==bek[i].frekans && muzik::ADIMLAR[i].ms==bek[i].ms); }
  // Tum sarki: dogru sira, dogru an (+-2 ms), sonunda sessiz ve bitmis
  reset(); muzik::kur(LAZER_PIN); command(Serial,"E"); command(Serial,"MZ1");
  kayit.clear(); { uint32_t t0=fakeUs; kos(2000000);
    uint32_t bek=0; size_t k=0;
    for(int i=1;i<muzik::ADET;++i){
      bek+=muzik::ADIMLAR[i-1].ms;
      if(muzik::ADIMLAR[i].frekans==muzik::ADIMLAR[i-1].frekans) continue;   // ses degismez
      assert(k<kayit.size()); assert(kayit[k].second==(int)muzik::ADIMLAR[i].frekans);
      long fark=(long)(kayit[k].first-t0)/1000-(long)bek; assert(labs(fark)<=2); ++k;
    }
    assert(k==kayit.size()); }
  assert(muzik::sira==-1 && muzik::calan==0 && buzzerFrek==0 && motion.armed);
  Serial.out.clear(); kos(150000); assert(var(Serial,"MZK1,0,2,1"));
  std::cout<<"Sarki sira ve sureleri dogru, ayni notalar ayri, sonunda sessiz: passed\n";

  // 3. BEKLETMEZ: sarki calarken kol 30 dereceye kalkar
  reset(); muzik::kur(LAZER_PIN); motion.count=2; motion.points[1]={60,2675};
  command(Serial,"E"); command(Serial,"MZ2"); command(Serial,"G30");
  kos(3000000);
  assert(muzik::calan==2);                                // hala caliyor (4 sn'lik sarki)
  assert(!motion.moving() && motion.pos==motion.target && motion.pos>1300);
  assert(physicalPulses==motion.pos && motion.armed);
  std::cout<<"Sarki calarken kol 30 dereceye kalkti, nabiz kopmadi: passed\n";

  // 4. TILT YORUNGESINI KESMEZ (otonom takip sirasinda sarki sarsinti yapmasin). Karsilastirma:
  //    bilinmeyen bir komut hareket yolundaki else dalina gider ve yorungeyi KESER.
  { auto yorungede=[](){ reset(); muzik::kur(LAZER_PIN); motion.count=2; motion.points[1]={60,2675};
      command(Serial,"E"); command(Serial,"G10");
      for(uint32_t bit=fakeUs+1500000,h=fakeUs;fakeUs<bit;){if(fakeUs-h>=100000){command(Serial,"H");h=fakeUs;}loop();fakeUs+=10;}
      command(Serial,"Y12,5"); for(int i=0;i<2000;++i){loop();fakeUs+=10;} assert(yorTilt.aktif); };
    yorungede(); command(Serial,"MZ2"); assert(var(Serial,"OK,MZ2")); assert(yorTilt.aktif && muzik::calan==2);
    command(Serial,"MZ0"); assert(yorTilt.aktif && muzik::calan==0);
    yorungede(); command(Serial,"MQ"); assert(var(Serial,"ERR,MQ,UNKNOWN_COMMAND")); assert(!yorTilt.aktif); }
  std::cout<<"MZ tilt yorungesini kesmiyor (bilinmeyen komut keserdi): passed\n";

  // 5. Lazer cikisi sarkidan etkilenmez (ton degisimleri lazer duty'sine dokunmaz)
  reset(); muzik::kur(LAZER_PIN); command(Serial,"E"); command(Serial,"L1");
  int duty=lazerCikis; assert(duty>0);
  command(Serial,"MZ2"); tonDegisimi=0;
  { uint32_t bit=fakeUs+3000000,h=fakeUs,l=fakeUs;
    while(fakeUs<bit){ if(fakeUs-h>=100000){command(Serial,"H");h=fakeUs;}
      if(fakeUs-l>=250000){command(Serial,"L1");l=fakeUs;}
      loop(); fakeUs+=50; assert(lazerCikis==duty); } }
  assert(tonDegisimi>10);
  command(Serial,"L0"); assert(lazerCikis==0);
  std::cout<<"Lazer cikisi sarki boyunca sabit: passed\n";

  // 6. ACIL DURDUR susturur; kilitliyken MZ reddedilir; START sonrasi yine calar; buton da susturur
  reset(); muzik::kur(LAZER_PIN); command(Serial,"E"); command(Serial,"MZ2"); kos(500000);
  assert(muzik::calan==2);
  command(Serial,"STOP"); assert(muzik::calan==0 && buzzerFrek==0);
  command(Serial,"MZ1"); assert(var(Serial,"ERR,MZ1,ESTOP")); kos(300000); assert(muzik::calan==0 && buzzerFrek==0);
  command(Serial,"START"); command(Serial,"E"); command(Serial,"MZ2"); assert(buzzerFrek==659);
  kos(300000); assert(muzik::calan==2);
  estopSeviye=LOW; kos(100000); assert(muzik::calan==0 && buzzerFrek==0);
  std::cout<<"STOP / buton susturur, acil kilitte calmaz: passed\n";

  // 7. MZ0 susturur; sarki degisimi; hatali numara / bicim
  reset(); muzik::kur(LAZER_PIN); command(Serial,"E"); command(Serial,"MZ1"); kos(100000);
  command(Serial,"MZ2"); assert(muzik::calan==2 && buzzerFrek==659);
  command(Serial,"MZ0"); assert(var(Serial,"OK,MZ0")); assert(muzik::calan==0 && buzzerFrek==0);
  command(Serial,"MZ3"); assert(var(Serial,"ERR,MZ3,NO_SONG")); assert(muzik::calan==0);
  command(Serial,"MZx"); assert(var(Serial,"ERR,MZx,BAD_SONG"));
  command(Serial,"MZ"); assert(var(Serial,"ERR,MZ,BAD_SONG"));
  std::cout<<"MZ0 susturur, sarki degisir, hatali numara reddedilir: passed\n";

  // 8. Lazerle AYNI LEDC zamanlayicisi -> hic kurulmaz, MZ reddedilir (lazer korunur)
  reset(); buzzerZamanlayici=0; muzik::kur(LAZER_PIN); assert(!muzik::hazir);
  command(Serial,"E"); command(Serial,"MZ1"); assert(var(Serial,"ERR,MZ1,NO_BUZZER"));
  kos(300000); assert(buzzerFrek==0 && tonDegisimi==0); assert(var(Serial,"MZK1,0,2,0"));
  reset(); ledcBasarili=false; muzik::kur(LAZER_PIN); assert(!muzik::hazir);
  command(Serial,"E"); command(Serial,"MZ1"); kos(300000); assert(tonDegisimi==0);
  std::cout<<"Lazerle ortak zamanlayici / LEDC hatasi -> sarki kapali: passed\n";

  std::cout<<"MUZIK testleri OK\n";
  return 0;
}
