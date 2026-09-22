#pragma once
#include <stdint.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
// Commanded pulse position only. No encoder feedback or software PID.
class MotionCore {
 public:
  static constexpr int CAPACITY=16;
  static constexpr uint32_t TIMEOUT_MS=350;
  // Hedef hareketinin tepe hizi ve ivmesi. ARTIK SABIT DEGIL: "Z<hiz>,<ivme>"
  // komutuyla calisma aninda degistirilir, boylece hiz denemesi icin her
  // seferinde yeniden yukleme gerekmez.
  //
  // Eski degerler 1600 / 3200 idi ve asil sikayet IVMEDEN geliyordu: tepe hiza
  // cikis suresi = hiz/ivme = 0.5 sn, yani kisa hareketlerde tepe hiza HIC
  // ulasilmiyor, hareket "agir" hissettiriyordu. Yeni varsayilanda bu sure
  // 0.25 sn.
  //
  // Mekanik pay: olculen kalibrasyonda 60 derece = 2675 darbe ve surucu
  // 6400 darbe/tur, yani kol 60 derece icin krank yalnizca 0.42 tur doner.
  // 3200 darbe/s = 30 rpm motor hizi demektir — NEMA23 icin cok dusuk.
  // Gercek darbogaz ESP32'nin dongu hizidir (darbeler yazilimla uretilir),
  // bu yuzden tavan 5000 darbe/s'de tutuldu.
  static constexpr double MAX_SPEED_VARSAYILAN=3200, ACCEL_VARSAYILAN=12800;
  static constexpr double HIZ_TABAN=100, HIZ_TAVAN=5000;
  static constexpr double IVME_TABAN=200, IVME_TAVAN=60000;
  static constexpr uint32_t JOG_LEASE_MS=250;
  double maxSpeed=MAX_SPEED_VARSAYILAN, accel=ACCEL_VARSAYILAN;
  struct Point { double angle; int32_t steps; };
  Point points[CAPACITY]={{0,0}};
  int count=1;
  int32_t pos=0,target=0;
  bool armed=false,calibrating=false,changed=false;
  int jogSpeed=400;
  bool calibrated() const {return count>=2 && points[count-1].angle==60;}
  int32_t upper() const {return calibrated()?points[count-1].steps:0;}
  bool moving() const {return pos!=target;}
  double angle(int32_t p) const {
    if(!calibrated()) return -1;
    for(int i=1;i<count;++i) if(p<=points[i].steps)
      return points[i-1].angle+(p-points[i-1].steps)*
        (points[i].angle-points[i-1].angle)/(points[i].steps-points[i-1].steps);
    return 60;
  }
  int32_t toSteps(double a) const {
    for(int i=1;i<count;++i) if(a<=points[i].angle)
      return (int32_t)lround(points[i-1].steps+(a-points[i-1].angle)*
        (points[i].steps-points[i-1].steps)/(points[i].angle-points[i-1].angle));
    return upper();
  }
  void stop(bool disarm=false) {target=pos; speed_=0; pending_=-1; jog_=0; if(disarm) armed=false;}
  void watchdog(uint32_t ms) {
    if(armed && (uint32_t(ms-lastAlive_)>=TIMEOUT_MS ||
       (jog_ && uint32_t(ms-lastJog_)>=JOG_LEASE_MS))) stop(true);
  }
  const char* command(const char* s,uint32_t ms,uint32_t us) {
    watchdog(ms);
    if(!strcmp(s,"X")) {stop(); return nullptr;}
    if(!strcmp(s,"D")) {stop(true); return nullptr;}
    // Z<hiz>,<ivme> : hedef hareketinin tepe hizi ve ivmesi (darbe/s, darbe/s^2).
    // V gibi yalnizca DURURKEN kabul edilir: hareket ortasinda profil degistirmek
    // o anki rampayi tutarsiz birakir. Iki deger birlikte verilir cunku ayri ayri
    // ayarlanabilseydi "yuksek hiz + dusuk ivme" gibi hedefe hic varamayan bir
    // kombinasyon kurulabilirdi.
    // R : "kol SU AN fiziksel olarak en altta" — darbe sayacini 0 kabul et.
    // Kalibrasyon tablosu SILINMEZ (K'den farki bu). Neden gerekli: ESP32 kolun
    // yerini OLCMEZ, gonderdigi darbeleri sayar. Motor beslemesi kesilince kol yer
    // cekimiyle duser ama USB'den beslenen ESP32 eski sayida kalir; sonraki her
    // komut kaymis referansa gore gider ve kol alt dayamaya bastirilir. Sahada
    // tam olarak bu yasandi (ESP 20 derece derken kol en alttaydi).
    if(!strcmp(s,"R")) {
      if(moving()) return "STOP_FIRST";
      stop(); pos=0; target=0; return nullptr;
    }
    if(s[0]=='Z') {
      if(moving()) return "STOP_FIRST";
      char* end=nullptr; double h=strtod(s+1,&end);
      if(end==s+1 || *end!=',') return "BAD_SPEED";
      char* end2=nullptr; double iv=strtod(end+1,&end2);
      if(end2==end+1 || *end2) return "BAD_SPEED";
      if(!isfinite(h) || !isfinite(iv)) return "BAD_SPEED";
      if(h<HIZ_TABAN || h>HIZ_TAVAN || iv<IVME_TABAN || iv>IVME_TAVAN) return "BAD_SPEED";
      maxSpeed=h; accel=iv; return nullptr;
    }
    if(s[0]=='V') {
      if(moving()) return "STOP_FIRST";
      if(!strcmp(s,"V100")) jogSpeed=100;
      else if(!strcmp(s,"V400")) jogSpeed=400;
      else if(!strcmp(s,"V800")) jogSpeed=800;
      else return "BAD_SPEED";
      return nullptr;
    }
    if(!strcmp(s,"E")) {stop(); armed=true; lastAlive_=ms; return nullptr;}
    if(!strcmp(s,"H")) {if(armed) lastAlive_=ms; return nullptr;}
    // Q : yetenek sorgusu. "OK,Q" donmesi, bu firmware'in hareket halinde yeni
    // hedefi DURMADAN uyguladigini (retarget) PC'ye soyler. Eski surum
    // UNKNOWN_COMMAND der ve PC eski davranisa (kart bosalinca gonder) doner.
    if(!strcmp(s,"Q")) return nullptr;
    if(!armed) return "DISARMED";
    if(!strcmp(s,"K")) {
      if(moving() || pos!=0) return "CAL_REQUIRES_ZERO_IDLE";
      stop(); count=1; points[0]={0,0}; calibrating=true; changed=true; return nullptr;
    }
    if(!strcmp(s,"W") || !strcmp(s,"S")) {
      if(!calibrated() && !calibrating) return "CAL_REQUIRED";
      int d=s[0]=='W'?1:-1; lastAlive_=ms; lastJog_=ms;
      if(jog_==d) return nullptr;
      if(moving()) return "STOP_FIRST";
      int32_t t=d>0?(calibrated()?upper():1000000):0;
      if(t<0) t=0;
      if(t>1000000) return "PULSE_RANGE";
      jog_=d; pending_=-1; begin(t,us); return nullptr;
    }
    if(s[0]=='G' || s[0]=='C') {
      char* end=nullptr; double a=strtod(s+1,&end);
      if(end==s+1 || *end || !isfinite(a) || a<0 || a>60) return "BAD_ANGLE";
      if(s[0]=='C') {
        if(!calibrating || moving() || count>=CAPACITY || a<=points[count-1].angle ||
           pos<=points[count-1].steps) return "BAD_CAL_POINT";
        points[count++]={a,pos}; changed=true;
        if(a==60) calibrating=false;
        return nullptr;
      }
      if(!calibrated()) return "CAL_REQUIRED";
      if(jog_) return "STOP_FIRST";
      lastAlive_=ms; int32_t t=toSteps(a);
      if(moving()) retarget(t,us); else begin(t,us);
      return nullptr;
    }
    return "UNKNOWN_COMMAND";
  }
  int next(uint32_t ms,uint32_t us) {
    watchdog(ms);
    if(!armed || !moving() || uint32_t(us-lastPulse_)<interval_) return 0;
    int d=target>pos?1:-1; int32_t n=pos+d;
    if(n<0 || (calibrated() && n>upper())) {stop(true); return 0;}
    return d;
  }
  // YORUNGE KIPI (yorunge_core.h) bir darbe attiginda sayaci ilerletir. Konum kipi
  // bosta kalir (hedef = konum), boylece iki kip ayni anda darbe uretmez.
  void izle(int d) {pos+=d; target=pos; speed_=0; pending_=-1; jog_=0;}
  // Commit immediately after exactly one physical pulse; never catch up in a burst.
  void emitted(int d,uint32_t us) {
    pos+=d; lastPulse_=us;
    if(pos==target) {
      speed_=0;
      if(pending_>=0) {int32_t p=pending_; pending_=-1; begin(p,us);}
    } else schedule();
  }
 private:
  int jog_=0; int32_t pending_=-1;
  uint32_t lastAlive_=0,lastJog_=0,lastPulse_=0,interval_=0;
  double speed_=0;
  void begin(int32_t t,uint32_t us) {target=t; speed_=0; lastPulse_=us; if(moving()) schedule();}
  // HAREKET HALINDEYKEN YENI HEDEF — DURMADAN yeniden planla.
  // Eskiden yeni hedef bekleme yuvasina giriyor, kol ONCE eski hedefe gidip
  // DURUYOR, sonra hizi 0'dan yeniden kaldiriyordu. Takipte bu saniyede birkac
  // "hizlan-yavasla-dur" dongusu demekti ve namluyu sarsiyordu (sahada olculdu:
  // ~1 sn'lik yaklasmada 6 dur-kalk).
  //  * yeni hedef AYNI yonde ve bu hizla frenleyerek yetisilebilir mesafedeyse:
  //    yalniz hedef degisir, HIZ KORUNUR -> hareket akar.
  //  * ters yonde ya da cok yakinsa: izin verilen ivmeyle en kisa frenle
  //    durulur (asma = fren mesafesi kadar, fizigin izin verdigi en az), sonra
  //    yeni hedefe gidilir. Anlik yon degistirmek adim kacirtir ve mekanigi zorlar.
  void retarget(int32_t t,uint32_t us) {
    int dir=target>pos?1:-1;
    int32_t fren=(int32_t)ceil(speed_*speed_/(2.0*accel));
    int32_t enErken=pos+dir*fren;
    if(calibrated()) {if(enErken<0) enErken=0; if(enErken>upper()) enErken=upper();}
    else if(enErken<0) enErken=0;
    if((int64_t)(t-pos)*dir>0 && (int64_t)(t-enErken)*dir>=0) {target=t; pending_=-1; return;}
    if(enErken==pos) {pending_=-1; begin(t,us); return;}   // zaten neredeyse durmus
    target=enErken; pending_=t;
  }
  void schedule() {
    double remaining=abs(target-pos),cap=jog_?jogSpeed:maxSpeed;
    speed_=fmin(cap,fmin(sqrt(speed_*speed_+2*accel),sqrt(2*accel*remaining)));
    interval_=(uint32_t)ceil(1000000.0/speed_);
  }
};
