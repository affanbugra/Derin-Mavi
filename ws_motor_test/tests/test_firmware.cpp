#include "stubs/Arduino.h"
#include <assert.h>
#include <iostream>
#include <cmath>
uint32_t fakeUs=0;
int physicalPulses=0;
int panPulses=0,panDirLevel=-1,panEnLevel=-1;
int lazerCikis=0,estopSeviye=HIGH;
bool ledcBasarili=true;
Stream Serial,Serial0;
#include "../esp32_ws_test/esp32_ws_test.ino"
void reset(){motion=MotionCore{};owner=-1;inputs[0]=PortInput{};inputs[1]=PortInput{};Serial=Stream{};Serial0=Stream{};prefs.fail=false;prefs.clear();fakeUs=0;physicalPulses=0;pan=PanCore{};yorTilt=Yorunge{};yorPan=Yorunge{};panEnable=-1;panPulses=0;panDirLevel=-1;panEnLevel=-1;lazerYuzde=40;lazerAcik=false;lazerPwmHazir=true;acilKilit=false;estopButon=false;sonAtesMs=0;lazerCikis=0;estopSeviye=HIGH;ledcBasarili=true;}
void command(Stream& port,const char* s){port.incoming+=s;port.incoming+='\n';while(port.available())readSerial(&port==&Serial?0:1);}
int main(){
  reset();command(Serial,"E");command(Serial,"K");assert(motion.calibrating);assert(Serial.out.find("OK,K")!=std::string::npos);
  command(Serial,"W");uint32_t nextRenew=50000;
  while(fakeUs<1000000){if(fakeUs>=nextRenew){command(Serial,"W");nextRenew+=50000;}loop();fakeUs+=50;}
  assert(motion.pos>300 && physicalPulses==motion.pos);
  command(Serial,"X");int p=physicalPulses;for(int i=0;i<100;++i){loop();fakeUs+=1000;}assert(physicalPulses==p);
  std::cout<<"Firmware continuous jog / physical pulse commits: passed\n";
  reset();command(Serial,"E");command(Serial0,"E");assert(Serial0.out.find("OTHER_PORT_ACTIVE")!=std::string::npos);command(Serial0,"D");assert(!motion.armed);command(Serial0,"E");assert(owner==1 && motion.armed);
  std::cout<<"Dual-port ownership and emergency stop: passed\n";
  reset();command(Serial,"E");prefs.fail=true;command(Serial,"K");assert(Serial.out.find("CAL_SAVE_FAILED")!=std::string::npos);assert(Serial.out.find("OK,K")==std::string::npos);assert(!motion.armed);
  std::cout<<"Flash failure does not acknowledge success: passed\n";
  reset();command(Serial,"E");command(Serial,(std::string(80,'G')+"10").c_str());assert(!motion.armed);assert(Serial.out.find("LINE_TOO_LONG")!=std::string::npos);assert(!physicalPulses);
  std::cout<<"Overlong serial input stops safely: passed\n";
  reset();command(Serial,"E");command(Serial,"K");command(Serial,"W");for(int i=0;i<6000;++i){if(i%1000==0)command(Serial,"H");loop();fakeUs+=50;}assert(!motion.armed);
  std::cout<<"Firmware H heartbeat cannot prolong lost jog: passed\n";
  // --- PAN (GPIO10/11) ---
  reset();command(Serial,"P10");assert(Serial.out.find("ERR,P10,DISABLED")!=std::string::npos);assert(!pan.moving());
  reset();command(Serial,"E");command(Serial,"P10");assert(Serial.out.find("OK,P10")!=std::string::npos);
  for(int i=0;i<400000 && pan.moving();++i){if(i%2000==0)command(Serial,"H");loop();fakeUs+=10;}
  assert(!pan.moving());assert(pan.pos==PanCore::steps(10));assert(panPulses==PanCore::steps(10));assert(!physicalPulses);assert(panDirLevel==(PAN_DIR_POS_HIGH?HIGH:LOW));
  assert(Serial.out.find("PAN1,")!=std::string::npos);
  std::cout<<"Pan P10 emits exact pulses on GPIO10 only: passed\n";
  command(Serial,"P-5");for(int i=0;i<400000 && pan.moving();++i){if(i%2000==0)command(Serial,"H");loop();fakeUs+=10;}
  assert(pan.pos==PanCore::steps(-5));assert(panDirLevel==(PAN_DIR_POS_HIGH?LOW:HIGH));
  command(Serial,"PR");assert(pan.pos==0 && pan.target==0);
  std::cout<<"Pan negative move flips DIR, PR zeroes: passed\n";
  reset();command(Serial,"E");command(Serial,"P90");for(int i=0;i<2000;++i){loop();fakeUs+=10;}assert(pan.moving());command(Serial,"X");assert(!pan.moving());assert(motion.armed);
  command(Serial,"P90");for(int i=0;i<2000;++i){loop();fakeUs+=10;}command(Serial,"D");assert(!pan.moving());
  std::cout<<"Pan stops on X and D: passed\n";
  reset();command(Serial,"E");command(Serial,"P90");{int before=0;for(int i=0;i<60000;++i){loop();fakeUs+=10;if(i==1000)before=panPulses;}assert(!motion.armed);assert(!pan.moving());assert(panPulses>before);}
  std::cout<<"Pan stops when heartbeat watchdog disarms: passed\n";
  reset();command(Serial,"E");command(Serial,"P401");assert(Serial.out.find("BAD_ANGLE")!=std::string::npos);command(Serial,"Pabc");assert(Serial.out.find("ERR,Pabc,BAD_ANGLE")!=std::string::npos);
  command(Serial,"PZ3000,9000");assert(pan.maxSpeed==3000 && pan.accel==9000);command(Serial,"PZ99999,1");assert(Serial.out.find("BAD_PROFILE")!=std::string::npos);
  command(Serial,"PE0");assert(panEnLevel==LOW && panEnable==0);command(Serial,"PE-");assert(panEnable==-1);command(Serial0,"P5");assert(Serial0.out.find("OTHER_PORT_ACTIVE")!=std::string::npos);
  assert(motion.pos==0 && !motion.changed);
  std::cout<<"Pan validation, profile, ENA, ownership, tilt untouched: passed\n";
  reset();command(Serial,"E");command(Serial,"P20");for(int i=0;i<30000;++i){if(i%2000==0)command(Serial,"H");loop();fakeUs+=10;}assert(pan.moving());
  command(Serial,"P30");assert(pan.target>PanCore::steps(20)-1);for(int i=0;i<400000 && pan.moving();++i){if(i%2000==0)command(Serial,"H");loop();fakeUs+=10;}assert(pan.pos==PanCore::steps(30));assert(panPulses==PanCore::steps(30));
  command(Serial,"P0");for(int i=0;i<30000;++i){if(i%2000==0)command(Serial,"H");loop();fakeUs+=10;}command(Serial,"P25");for(int i=0;i<600000 && pan.moving();++i){if(i%2000==0)command(Serial,"H");loop();fakeUs+=10;}assert(pan.pos==PanCore::steps(25));
  std::cout<<"Pan retarget same-direction and reversal land exactly: passed\n";
  reset();command(Serial,"E");command(Serial,"PZ11800,59000");assert(Serial.out.find("OK,PZ11800,59000")!=std::string::npos);command(Serial,"P90");
  {uint32_t t0=fakeUs;for(int i=0;i<2000000 && pan.moving();++i){if(i%2000==0)command(Serial,"H");loop();fakeUs+=10;}
   assert(pan.pos==PanCore::steps(90));assert(panPulses==PanCore::steps(90));double sn=(fakeUs-t0)/1e6;assert(sn<1.3);
   std::cout<<"Pan fast profile 90 deg in "<<sn<<" s (stub loop), exact landing: passed"<<std::endl;}
  // ---------------- YORUNGE KIPI (Y / PY) ----------------
  {
    auto kalibre=[](){motion.count=2; motion.points[1]={60,2675};};
    auto tekrar=[](const char* c,uint32_t us){uint32_t bit=fakeUs+us, g=0, h=fakeUs; while(fakeUs<bit){if(fakeUs-g>=40000){command(Serial,c);g=fakeUs;} if(fakeUs-h>=100000){command(Serial,"H");h=fakeUs;} loop(); fakeUs+=10;}};
    auto kos=[](uint32_t us){uint32_t bit=fakeUs+us; uint32_t h=fakeUs; while(fakeUs<bit){if(fakeUs-h>=100000){command(Serial,"H");h=fakeUs;} loop(); fakeUs+=10;}};
    // Rampa: 20 der/sn, 40 ms'de bir guncelleme; ogrenilen: 20 ms pencerelerde duran var mi
    auto rampa=[&](bool yorunge,int& duranPencere,double& azamiHata,double hz=20,double* dalga=nullptr){
      double sT=0,sT2=0; int nT=0;
      reset(); kalibre(); command(Serial,"E"); command(Serial,"G10"); kos(1500000);
      duranPencere=0; azamiHata=0; int onceki=physicalPulses; uint32_t t0=fakeUs, pencere=fakeUs, guncel=0;
      while(fakeUs-t0<1500000){
        double t=(fakeUs-t0)*1e-6, ref=10+hz*t; char b[40];
        if(fakeUs-guncel>=40000){
          if(yorunge) snprintf(b,sizeof b,"Y%.3f,%.1f",ref,hz); else snprintf(b,sizeof b,"G%.3f",ref);
          command(Serial,b); guncel=fakeUs;
        }
        if((fakeUs-t0)%100000<10) command(Serial,"H");
        loop(); fakeUs+=10;
        if(fakeUs-pencere>=20000){
          if(t>0.3){ if(physicalPulses==onceki) ++duranPencere;
            double k=physicalPulses-onceki; sT+=k; sT2+=k*k; ++nT;
            double h=fabs(motion.angle(motion.pos)-ref); if(h>azamiHata) azamiHata=h; }
          onceki=physicalPulses; pencere=fakeUs;
        }
      }
      if(dalga){double m=sT/nT; *dalga=sqrt(fmax(0.0,sT2/nT-m*m))/m;}
    };
    int durY,durG; double hY,hG;
    rampa(true,durY,hY); rampa(false,durG,hG);
    std::cout<<"Rampa 20 der/sn: YORUNGE duran 20ms pencere="<<durY<<" azami hata "<<hY<<" der | KONUM(G) duran="<<durG<<" hata "<<hG<<" der\n";
    assert(durY==0); assert(hY<1.0);
    for(double hz: {3.0,10.0,20.0}){
      int a1,a2; double h1,h2,d1,d2; rampa(true,a1,h1,hz,&d1); rampa(false,a2,h2,hz,&d2);
      std::cout<<"Rampa "<<hz<<" der/sn hiz dalgalanmasi (std/ort, 20 ms): YORUNGE "<<d1<<" | KONUM(G) "<<d2<<std::endl;
      // Yavas hedefte (el hareketi) yorunge belirgin daha duzgun; hizlida ikisi de
      // 20 ms sayim cozunurlugu sinirinda (ayrim yok), yorunge yine de puruzsuz kalmali.
      if(hz<5) assert(d1<0.5*d2); else assert(d1<0.1);
    }
    std::cout<<"Yorunge: sabit hizli hedefte motor hic durmuyor, hata <1 der: passed\n";

    reset(); kalibre(); command(Serial,"E"); command(Serial,"YQ"); assert(Serial.out.find("OK,YQ")!=std::string::npos);
    tekrar("Y10,0",1500000); assert(Serial.out.find("OK,Y10")==std::string::npos);   // sessiz
    assert(abs(motion.pos-motion.toSteps(10))<=2);
    command(Serial,"Y12,20");                                 // tek komut, sonra sessizlik
    kos(1000000); assert(!yorTilt.aktif && motion.armed);
    double son=motion.angle(motion.pos); assert(son>10.2 && son<16.0);
    std::cout<<"Yorunge: 150 ms komut gelmezse yumusak durus (durdugu aci "<<son<<"): passed\n";

    tekrar("Y10,0",1000000); command(Serial,"Y40,60"); kos(100000); assert(yorTilt.aktif);
    command(Serial,"X"); int p0=physicalPulses; kos(200000); assert(!yorTilt.aktif && physicalPulses==p0);
    std::cout<<"Yorunge: X aninda durdurur: passed\n";

    tekrar("Y60,200",2400000);
    assert(motion.pos<=motion.upper() && motion.armed);
    command(Serial,"G30"); assert(!yorTilt.aktif);
    std::cout<<"Yorunge: ust sinira fren, asmaz; G yorungeyi keser: passed\n";

    reset(); kalibre(); command(Serial,"E"); command(Serial,"Y20,0");
    for(int i=0;i<5000;++i){loop(); fakeUs+=100;}            // nabiz YOK
    assert(!motion.armed && !yorTilt.aktif);
    std::cout<<"Yorunge: nabiz kesilince eksen kapanir: passed\n";

    reset(); command(Serial,"PY5,0"); assert(Serial.out.find("DISABLED")!=std::string::npos);
    command(Serial,"E"); uint32_t t0=fakeUs, g=0;
    while(fakeUs-t0<1500000){ double t=(fakeUs-t0)*1e-6; if(fakeUs-g>=40000){char b[40]; snprintf(b,sizeof b,"PY%.3f,30",30*t); command(Serial,b); g=fakeUs;} if((fakeUs-t0)%100000<10) command(Serial,"H"); loop(); fakeUs+=10; }
    assert(fabs(pan.angle()-45.0)<1.0); assert(!physicalPulses);
    command(Serial,"D"); assert(!yorPan.aktif);
    std::cout<<"Pan yorunge: 30 der/sn rampa izlenir ("<<pan.angle()<<"), D durdurur, tilt'e darbe yok: passed\n";
  }

  // ---------------- LAZER (GPIO 18) + ACIL DURDURMA (GPIO 15) ----------------
  {
    auto kos=[](uint32_t us,bool nabiz=true,const char* tazele=nullptr){uint32_t bit=fakeUs+us,h=fakeUs,l=fakeUs;
      while(fakeUs<bit){if(nabiz&&fakeUs-h>=100000){command(Serial,"H");h=fakeUs;}
        if(tazele&&fakeUs-l>=250000){command(Serial,tazele);l=fakeUs;} loop(); fakeUs+=100;}};
    const int D40=(40*256)/100;
    // Acilis: pin sonuk; PWM kurulamazsa L1 reddedilir ve pin yine sonuk.
    reset(); lazerCikis=123; setup(); assert(lazerCikis==0 && lazerPwmHazir && !acilKilit);
    reset(); ledcBasarili=false; setup(); assert(!lazerPwmHazir && Serial.out.find("ERR,LASER_PWM")!=std::string::npos);
    command(Serial,"E"); command(Serial,"L1"); assert(lazerCikis==0 && Serial.out.find("ERR,L1,LASER_PWM")!=std::string::npos);
    reset(); estopSeviye=LOW; setup(); assert(acilKilit && estopButon);      // buton basiliyken acilis
    std::cout<<"Lazer: acilista sonuk, PWM hatasi ve basili buton kilitli baslar: passed\n";

    // Kontrol acilmadan (E) ates yok; E + L1 ayarli gucte yakar; L1 tazelemesi sessiz.
    reset(); command(Serial,"L1"); assert(lazerCikis==0 && Serial.out.find("ERR,L1,DISARMED")!=std::string::npos);
    command(Serial,"E"); command(Serial,"L1"); assert(lazerAcik && lazerCikis==D40 && Serial.out.find("OK,L1")!=std::string::npos);
    size_t n=Serial.out.size(); command(Serial,"L1"); assert(Serial.out.find("OK,L1",n)==std::string::npos);
    command(Serial,"LP100"); assert(lazerCikis==256); command(Serial,"LP0"); assert(lazerCikis==0 && lazerAcik);
    command(Serial,"LP101"); assert(Serial.out.find("ERR,LP101,BAD_POWER")!=std::string::npos && lazerYuzde==0);
    command(Serial,"LP40"); command(Serial,"L0"); assert(!lazerAcik && lazerCikis==0);
    std::cout<<"Lazer: E sarti, %40 guc, LP aninda uygulanir, L0 keser: passed\n";

    // OLU ADAM ANAHTARI: nabiz surse bile L1 tazelemesi 1 sn kesilirse lazer soner;
    // tazeleme suruyorsa yanik kalir.
    reset(); command(Serial,"E"); command(Serial,"L1"); kos(3000000,true,"L1"); assert(lazerAcik && lazerCikis==D40);
    kos(1200000); assert(!lazerAcik && lazerCikis==0 && motion.armed);
    assert(Serial.out.find("olu adam")!=std::string::npos);
    // Nabiz (H) kesilirse kart 350 ms'de kilitlenir, lazer de soner (tazeleme olsa bile).
    reset(); command(Serial,"E"); command(Serial,"L1"); kos(600000,false,"L1"); assert(!motion.armed && !lazerAcik && lazerCikis==0);
    // PC tamamen sustu (kablo koptu: ne H ne L1): 350 ms'de kontrol kapanir ve lazer
    // O AN soner — olu adam anahtarinin 1 sn'sini beklemez.
    reset(); command(Serial,"E"); command(Serial,"L1"); kos(500000,false); assert(!motion.armed && !lazerAcik && lazerCikis==0);
    reset(); command(Serial,"E"); command(Serial,"L1"); command(Serial,"D"); assert(!lazerAcik && lazerCikis==0);
    // X (hareketi durdur — tus birakma) atesi KESMEZ.
    reset(); command(Serial,"E"); command(Serial,"L1"); command(Serial,"X"); assert(lazerAcik);
    std::cout<<"Lazer: olu adam anahtari 1 sn, nabiz kaybi ve D keser, X kesmez: passed\n";

    // SERI ACIL DURDURMA: lazer soner, hareket ve L1 reddedilir, E (PC'nin otomatik
    // yeniden acmasi) kilidi KALDIRMAZ; START kaldirir.
    reset(); motion.count=2; motion.points[1]={60,2675}; command(Serial,"E"); command(Serial,"L1"); command(Serial,"G30");
    kos(200000); assert(motion.moving());
    command(Serial,"STOP"); assert(acilKilit && !lazerAcik && lazerCikis==0 && !motion.moving());
    assert(Serial.out.find("SISTEM DURDURULDU")!=std::string::npos);
    int p=physicalPulses; kos(300000); assert(physicalPulses==p);
    for(const char* c:{"G10","W","S","Y10,0","P5","PY5,0","L1"}) {size_t m=Serial.out.size(); command(Serial,c);
      assert(Serial.out.find("ESTOP",m)!=std::string::npos);} 
    command(Serial,"E"); assert(acilKilit); command(Serial,"L1"); assert(!lazerAcik);
    command(Serial,"START"); assert(!acilKilit && Serial.out.find("SISTEM BASLATILDI")!=std::string::npos);
    command(Serial,"G10"); assert(motion.moving()); command(Serial,"L1"); assert(lazerAcik);
    std::cout<<"Acil: STOP lazeri ve iki ekseni durdurur, hareket/ates reddedilir, E kaldirmaz, START kaldirir: passed\n";

    // Durdurma ve kesme HER PORTTAN; ates yalniz sahibinden.
    reset(); command(Serial,"E"); command(Serial,"L1"); command(Serial0,"L1"); assert(Serial0.out.find("OTHER_PORT_ACTIVE")!=std::string::npos);
    command(Serial0,"L0"); assert(!lazerAcik); command(Serial,"L1"); command(Serial0,"STOP"); assert(acilKilit && !lazerAcik);
    std::cout<<"Acil: STOP/L0 diger porttan da gecer, L1 gecmez: passed\n";

    // DONANIM BUTONU: basinca (sicrama filtresinden sonra) kilit + lazer soner; basiliyken
    // START REDDEDILIR; birakinca kendiliginden KALKMAZ, START ister.
    reset(); command(Serial,"E"); command(Serial,"L1"); estopSeviye=LOW; kos(10000); assert(!acilKilit);  // 10 ms: sicrama
    kos(50000); assert(acilKilit && estopButon && !lazerAcik && lazerCikis==0);
    command(Serial,"START"); assert(acilKilit && Serial.out.find("START REDDEDILDI")!=std::string::npos);
    estopSeviye=HIGH; kos(100000); assert(!estopButon && acilKilit);
    command(Serial,"START"); assert(!acilKilit);
    std::cout<<"Acil buton: sicrama filtresi, basiliyken START ret, birakinca kendiliginden kalkmaz: passed\n";

    // LZR1 yayini: PC lazer destegini/durumunu buradan okur.
    reset(); command(Serial,"E"); command(Serial,"L1"); kos(30000);
    assert(Serial.out.find("LZR1,1,40,0,0,1")!=std::string::npos);
    std::cout<<"LZR1 durum yayini: passed\n";
  }
}
