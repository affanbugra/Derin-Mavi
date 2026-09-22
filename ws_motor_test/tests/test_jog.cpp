#include "../esp32_ws_test/motion_core.h"
#include <assert.h>
#include <iostream>
#include <random>
struct Rig {
  MotionCore m; uint32_t ms=0,us=0; uint64_t elapsed=0; int pulses=0; const char* hold=nullptr;
  void cmd(const char* s) {const char* e=m.command(s,ms,us); if(e)std::cerr<<s<<":"<<e<<"\n";assert(!e);}
  void setup() {m.points[0]={0,0};m.points[1]={10,100};m.points[2]={30,500};m.points[3]={60,1600};m.count=4;cmd("E");}
  void tick(bool heartbeat=true,bool jog=true) {
    us+=50; elapsed+=50;
    if(elapsed%1000==0) ++ms;
    if(heartbeat && elapsed%50000==0)cmd("H");
    if(jog && hold && elapsed%50000==0)cmd(hold);
    int d=m.next(ms,us);
    if(d) {m.emitted(d,us);++pulses;assert(!m.next(ms,us));}
    assert(m.pos>=0);if(m.calibrated())assert(m.pos<=m.upper());
  }
  void wait(int milliseconds,bool heartbeat=true,bool jog=true) {for(int i=0;i<milliseconds*20;++i)tick(heartbeat,jog);}
  void finish() {for(int i=0;i<2000000 && m.moving();++i)tick();assert(!m.moving());}
};
int main() {
  int groups=0;
  {Rig r;r.setup();r.cmd("G10");r.finish();assert(r.m.pos==100 && r.pulses==100);r.cmd("G30");r.finish();assert(r.m.pos==500);r.cmd("G0");r.finish();assert(r.m.pos==0);++groups;}
  {Rig r;r.setup();for(auto s:{"Gnan","Ginf","G-1","G61","G","G10xyz","G1e99","Z","Wjunk","V0","V800junk"})assert(r.m.command(s,0,0));assert(!r.m.moving());++groups;}
  {Rig r;r.setup();r.cmd("G60");r.wait(200);r.cmd("G0");r.cmd("G30");r.finish();assert(r.m.pos==500);++groups;}
  {Rig r;r.setup();r.cmd("G60");r.wait(200);r.cmd("G0");r.cmd("X");int p=r.m.pos;r.wait(1000);assert(r.m.pos==p);++groups;}
  {Rig r;r.setup();r.cmd("G60");r.wait(351,false);assert(!r.m.armed);int p=r.m.pos;r.wait(500,false);assert(r.m.pos==p);assert(r.m.command("G0",r.ms,r.us));r.cmd("H");assert(!r.m.armed);++groups;}
  // Regression: sustained jog must no longer stop at 64 pulses.
  {Rig r;r.cmd("E");assert(r.m.command("W",0,0));r.cmd("K");r.hold="W";r.cmd("W");r.wait(1000);assert(r.m.pos>300 && r.m.moving());r.hold=nullptr;r.cmd("X");int p=r.m.pos;r.wait(1000);assert(r.m.pos==p);++groups;}
  // Heartbeats alone cannot keep a released/lost jog alive.
  {Rig r;r.cmd("E");r.cmd("K");r.hold="W";r.cmd("W");r.wait(500);r.hold=nullptr;r.wait(251);assert(!r.m.armed && !r.m.moving());++groups;}
  {Rig r;r.setup();r.cmd("S");r.finish();assert(r.m.pos==0);r.cmd("X");r.hold="W";r.cmd("W");r.finish();assert(r.m.pos==1600);++groups;}
  {Rig r;r.setup();r.cmd("G60");r.ms=300;r.us=300000;int d=r.m.next(r.ms,r.us);assert(d==1);r.m.emitted(d,r.us);assert(!r.m.next(r.ms,r.us));assert(r.m.pos==1);++groups;}
  {Rig r;r.ms=0xfffffff0u;r.us=0xfffffff0u;r.setup();r.cmd("G10");r.finish();assert(r.m.pos==100);++groups;}
  {Rig r;r.setup();std::mt19937 rng(42);for(int i=0;i<300;++i){int a=rng()%61;char s[20];snprintf(s,sizeof(s),"G%d",a);r.cmd(s);r.finish();assert(r.m.pos==r.m.toSteps(a));}++groups;}
  // Complete real sequence: begin, hold, release, record, final record, G30.
  {Rig r;r.cmd("E");r.cmd("K");r.hold="W";r.cmd("W");r.wait(500);r.hold=nullptr;r.cmd("X");r.cmd("C10");int p=r.m.pos;r.hold="W";r.cmd("W");r.wait(700);r.hold=nullptr;r.cmd("X");assert(r.m.pos>p);r.cmd("C60");assert(r.m.calibrated());r.cmd("G30");r.finish();assert(r.m.pos==r.m.toSteps(30));++groups;}
  {Rig r;r.setup();r.cmd("G60");assert(r.m.command("V800",r.ms,r.us));r.cmd("D");assert(!r.m.armed);r.cmd("V800");assert(r.m.jogSpeed==800);++groups;}
  {Rig r;r.cmd("E");r.cmd("K");r.hold="W";r.cmd("W");r.wait(300);assert(r.m.command("C10",r.ms,r.us));r.hold=nullptr;r.cmd("X");r.cmd("C10");assert(r.m.command("C10",r.ms,r.us));assert(r.m.command("C5",r.ms,r.us));++groups;}
  {int speeds[]={100,400,800};int positions[3];for(int j=0;j<3;++j){Rig r;r.cmd("E");r.cmd("K");char s[16];snprintf(s,sizeof(s),"V%d",speeds[j]);r.cmd(s);r.hold="W";r.cmd("W");r.wait(1000);positions[j]=r.m.pos;std::cout<<"Jog "<<speeds[j]<<" pulses/s: "<<positions[j]<<" pulses in 1 simulated second\n";}assert(positions[1]>3*positions[0]);assert(positions[2]>positions[1]);++groups;}
  // Hedef suresi SABITLERDEN turetilir; hiz/ivme degisince test kendi kendini gunceller.
  // Yamuk profil: t = v/a + D/v ; ucgen profil (tepe hiza ulasilamiyorsa): t = 2*sqrt(D/a).
  {Rig r;r.setup();r.cmd("G60");r.finish();double seconds=r.elapsed/1000000.0;
   const double v=MotionCore::MAX_SPEED_VARSAYILAN,a=MotionCore::ACCEL_VARSAYILAN,D=1600.0;
   double beklenen=(D>=v*v/a)?(v/a+D/v):(2.0*sqrt(D/a));
   std::cout<<"1600-pulse target: "<<seconds<<" s (beklenen ~"<<beklenen<<" s)\n";
   assert(seconds>beklenen*0.75 && seconds<beklenen*1.35);++groups;}
  // Z<hiz>,<ivme>: calisma aninda hiz profili. Yeniden yukleme olmadan denenebilmeli.
  {Rig r;r.setup();
   assert(r.m.command("Z",0,0));                       // deger yok
   assert(r.m.command("Z3200",0,0));                   // ivme yok
   assert(r.m.command("Z3200,",0,0));                  // ivme bos
   assert(r.m.command("Z3200,12800x",0,0));            // artik karakter
   assert(r.m.command("Z99,12800",0,0));               // hiz tabanin altinda
   assert(r.m.command("Z99999,12800",0,0));            // hiz tavanin ustunde
   assert(r.m.command("Z3200,100",0,0));               // ivme tabanin altinda
   assert(r.m.command("Z3200,999999",0,0));            // ivme tavanin ustunde
   assert(r.m.maxSpeed==MotionCore::MAX_SPEED_VARSAYILAN);  // hicbiri sizmadi
   r.cmd("Z2000,8000");assert(r.m.maxSpeed==2000 && r.m.accel==8000);
   r.cmd("G60");assert(r.m.command("Z3000,9000",r.ms,r.us));  // hareket ortasinda YOK
   r.finish();r.cmd("Z3000,9000");assert(r.m.maxSpeed==3000);++groups;}
  // RETARGET 1: ayni yonde yeni hedef -> kol eski hedefte DURMAZ. Olcut: eski hedefin
  // (G30 = 500 darbe) cevresinde darbeler arasi en buyuk bosluk. Eski davranista kol
  // 500'de durup hizi 0'dan kaldiriyordu -> ilk bosluk ~6250 us (160 darbe/s).
  {Rig r;r.setup();r.cmd("G30");r.wait(80);assert(r.m.moving());r.cmd("G60");
   uint32_t son=r.us,enBuyuk=0;
   for(int i=0;i<4000000 && r.m.moving();++i){int32_t p=r.m.pos;r.tick();
     if(r.m.pos!=p){if(r.m.pos>450 && r.m.pos<550){uint32_t b=r.us-son;if(b>enBuyuk)enBuyuk=b;}son=r.us;}}
   std::cout<<"retarget ayni yon: eski hedef civarinda en buyuk darbe boslugu "<<enBuyuk<<" us\n";
   assert(r.m.pos==1600 && enBuyuk<1500);++groups;}
  // RETARGET 2: ters yon -> izin verilen ivmeyle en kisa fren, sonra yeni hedef.
  // Asma, fizigin izin verdigi fren mesafesini gecmemeli.
  {Rig r;r.setup();r.cmd("G60");r.wait(200);assert(r.m.moving());int32_t p0=r.m.pos,enYuksek=p0;
   r.cmd("G10");
   for(int i=0;i<4000000 && r.m.moving();++i){r.tick();if(r.m.pos>enYuksek)enYuksek=r.m.pos;}
   double fren=MotionCore::MAX_SPEED_VARSAYILAN*MotionCore::MAX_SPEED_VARSAYILAN/(2*MotionCore::ACCEL_VARSAYILAN);
   std::cout<<"retarget ters yon: "<<(enYuksek-p0)<<" darbe asma (fren tavani "<<fren<<")\n";
   assert(r.m.pos==r.m.toSteps(10) && enYuksek-p0<=(int32_t)fren+2);++groups;}
  // RETARGET 3: kalkistan hemen sonra ters komut (hiz ~0) -> dogrudan yeni hedef.
  {Rig r;r.setup();r.cmd("G30");r.finish();r.cmd("G60");r.tick();r.cmd("G0");r.finish();
   assert(r.m.pos==0);++groups;}
  // RETARGET 4: sinira yakin frende hedef kalibrasyon araligini asmaz.
  {Rig r;r.setup();r.cmd("G60");for(int i=0;i<4000000 && r.m.pos<1500;++i)r.tick();
   r.cmd("G0");int32_t enYuksek=r.m.pos;
   for(int i=0;i<4000000 && r.m.moving();++i){r.tick();if(r.m.pos>enYuksek)enYuksek=r.m.pos;}
   assert(enYuksek<=r.m.upper() && r.m.pos==0);++groups;}
  // Q: yetenek sorgusu (PC retarget'i bununla anlar).
  {Rig r;r.setup();r.cmd("Q");++groups;}
  // R: sayaci 0 kabul et, kalibrasyonu KORU, hareket ortasinda reddet.
  {Rig r;r.setup();r.cmd("G30");r.finish();assert(r.m.pos>0);
   r.cmd("R");assert(r.m.pos==0 && r.m.target==0 && !r.m.moving());
   assert(r.m.calibrated() && r.m.count==4);                 // tablo silinmedi
   r.cmd("G60");assert(r.m.command("R",r.ms,r.us));          // hareket ortasinda YOK
   r.finish();r.cmd("R");assert(r.m.pos==0);
   r.cmd("G10");r.finish();assert(r.m.pos==100);              // yeni sifirdan dogru gider
   {Rig d;d.setup();d.cmd("D");d.cmd("R");assert(d.m.pos==0);} // kilitliyken de sifirlanabilir
   ++groups;}
  // Yuksek profil GERCEKTEN daha hizli bitirmeli (sabitleri yukseltmenin anlami bu).
  {Rig yavas;yavas.setup();yavas.cmd("Z1600,3200");yavas.cmd("G60");yavas.finish();
   Rig hizli;hizli.setup();hizli.cmd("Z3200,12800");hizli.cmd("G60");hizli.finish();
   double ty=yavas.elapsed/1000000.0,th=hizli.elapsed/1000000.0;
   std::cout<<"1600 darbe: eski profil "<<ty<<" s, yeni profil "<<th<<" s\n";
   assert(yavas.m.pos==hizli.m.pos && th<ty*0.7);++groups;}
  {Rig r;r.cmd("E");r.cmd("K");r.hold="W";r.cmd("W");r.wait(500);r.hold=nullptr;r.cmd("D");assert(!r.m.armed);r.cmd("E");r.hold="S";r.cmd("S");r.finish();assert(r.m.pos==0);r.cmd("X");r.cmd("K");assert(r.m.count==1);++groups;}
  std::cout<<groups<<" motion test groups passed; no hardware movement tested.\n";
}
