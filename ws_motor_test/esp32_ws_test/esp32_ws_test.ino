#include <Arduino.h>
#include <Preferences.h>
#include "motion_core.h"
#include "pan_core.h"
#include "yorunge_core.h"
#if !ARDUINO_USB_CDC_ON_BOOT
#error "Enable USB CDC On Boot (CDCOnBoot=cdc); firmware supports both native USB and UART0."
#endif
constexpr int STEP_PIN=4, DIR_PIN=5;
constexpr bool DIR_UP_HIGH=true;
// PAN (sag-sol) surucusu AYNI karta bagli: PUL=GPIO10, DIR=GPIO11, ENA=GPIO16.
// PAN_DIR_POS_HIGH: pozitif aci (saga) icin DIR seviyesi — kamerayla dogrulanir.
// ENA pini VARSAYILAN olarak SURULMEZ (giris/bosta): ENA hangi uca baglanmis olursa
// olsun bosta ENA surucuyu etkin birakir (tilt'te de ENA surulmuyor ve calisiyor).
// Teshis icin "PE0"/"PE1" pini LOW/HIGH surer, "PE-" tekrar bosa alir.
constexpr int PAN_STEP_PIN=10, PAN_DIR_PIN=11, PAN_EN_PIN=16;
constexpr bool PAN_DIR_POS_HIGH=true; // sahada takiple dogrulandi (21.09.2026): false iken hedeften kaciyordu
constexpr int PULSES_PER_MOTOR_REV=6400;
constexpr uint32_t STEP_HIGH_US=20, DIR_SETUP_US=20;
// Confirm electrical interface and pulse polarity with your exact driver.
// EVERY RESET assumes the arm is physically at the lower 0-degree position.
// ---- LAZER + ACIL DURDURMA (24.09: tek kart — eski ESP32 kartindaki kurallar aynen) ----
// Lazer GPIO 18 PWM tetik (1 kHz, 8 bit), guc %0-100 (varsayilan %40, app/protokol.py ile ayni).
// ⚠ DONANIM SARTI: GPIO 18 <-> GND 10 kOhm pull-down. Reset/yukleme sirasinda pin ROM
//   bootloader boyunca bostadir; lazer surucusunun girisi kacak tetiklenmesin. Lazer
//   pinden BESLENMEZ: pin yalniz surucu modulunun TTL/PWM girisini surer.
// Acil durdurma butonu GPIO 15: NO buton GND'ye ceker (basili = LOW), dahili pull-up.
//   Buton takili degilse pin HIGH kalir = basili degil (zararsiz). Sartname [KESIN]:
//   disari cikan kabloyla donanimsal acil durdurma butonu zorunlu.
// Komutlar:
//   L1  lazeri ac / TAZELE — 1 sn tazelenmezse kart lazeri KENDI keser (olu adam anahtari)
//   L0  lazeri kes (her porttan kabul edilir: kesmek her zaman serbest)
//   LP<yuzde>  lazer gucu %0-100
//   STOP   acil durdur: once lazer, sonra iki eksen oldugu yerde durur; kart KILITLENIR —
//          hareket ve L1 reddedilir ("ESTOP"). Her porttan kabul edilir.
//   START  kilidi kaldir (buton basiliyken REDDEDILIR). Bilincli eylem: buton birakilinca
//          kendiliginden kalkmaz.
// Durum yayini (50 Hz): LZR1,<lazer acik>,<guc %>,<acil kilit>,<buton basili>,<pwm hazir>
constexpr int LAZER_PIN=18, ESTOP_PIN=15;
constexpr int LAZER_PWM_FREK=1000, LAZER_PWM_COZ=8;
constexpr uint32_t ATES_ZAMAN_ASIMI_MS=1000, ESTOP_DEBOUNCE_MS=30;
int lazerYuzde=40;
bool lazerAcik=false, lazerPwmHazir=false, acilKilit=false, estopButon=false;
uint32_t sonAtesMs=0;
MotionCore motion;
PanCore pan;
Yorunge yorTilt, yorPan;   // otonom takip: (konum, hiz) izleyen kip — bkz. yorunge_core.h
int panEnable=-1; // -1: ENA bosta, 0/1: surulen seviye
Preferences prefs;
struct PortInput {char text[40]; size_t used=0; bool overflow=false;};
PortInput inputs[2];
Stream* links[]={&Serial,&Serial0};
int owner=-1; // Only the port which enabled control may issue motion/calibration commands.
bool saveCalibration() {
  if(!motion.changed) return true;
  motion.changed=false;
  if(!motion.calibrated()) {
    if(!prefs.clear()) {motion.stop(true); return false;}
    return true;
  }
  size_t size=motion.count*sizeof(MotionCore::Point);
  if(prefs.putInt("ppr",PULSES_PER_MOTOR_REV)!=sizeof(int32_t) ||
     prefs.putBytes("points",motion.points,size)!=size) {
    motion.stop(true); motion.count=1; prefs.clear();
    return false;
  }
  return true;
}
void loadCalibration() {
  size_t n=prefs.getBytesLength("points");
  if(prefs.getInt("ppr",0)!=PULSES_PER_MOTOR_REV || n<2*sizeof(MotionCore::Point) ||
     n>sizeof(motion.points) || n%sizeof(MotionCore::Point)) return;
  MotionCore::Point p[MotionCore::CAPACITY];
  if(prefs.getBytes("points",p,n)!=n) return;
  int c=n/sizeof(MotionCore::Point);
  if(p[0].angle!=0 || p[0].steps!=0 || p[c-1].angle!=60) return;
  for(int i=1;i<c;++i) if(!isfinite(p[i].angle) || p[i].angle<=p[i-1].angle ||
    p[i].angle>60 || p[i].steps<=p[i-1].steps || p[i].steps>1000000) return;
  memcpy(motion.points,p,n); motion.count=c;
}
// Pan komutlari ("P" ile baslar). Tilt kalibrasyonuna/NVS'ye dokunmaz.
//  P<derece>   mutlak pan acisi (tilt'teki gibi once E gerekir; H nabzi ikisini de canli tutar)
//  PR          pan sayacini sifirla (mevcut konum = 0), yalniz dururken
//  PZ<h>,<iv>  pan hiz/ivme (darbe/sn, darbe/sn^2), yalniz dururken
//  PE0/PE1/PE- ENA pinini LOW/HIGH sur / bosa al (teshis)
// YORUNGE komutlari: "Y<derece>,<derece/sn>" (tilt), "PY<derece>,<derece/sn>" (pan).
// Kart referansi kendisi ilerletir; 150 ms yeni komut gelmezse yumusakca durur.
// "YQ": yetenek sorgusu (eski firmware UNKNOWN_COMMAND der, PC konum kipine doner).
bool ikiSayi(const char* s,double& a,double& b) {
  char* e; a=strtod(s,&e);
  if(e==s || *e!=',') return false;
  const char* s2=e+1; b=strtod(s2,&e);
  return e!=s2 && !*e && isfinite(a) && isfinite(b);
}
const char* tiltYorunge(const char* s,uint32_t us) {
  if(!motion.armed) return "DISARMED";
  if(!motion.calibrated() || motion.calibrating) return "CAL_REQUIRED";
  double a,v;
  if(!ikiSayi(s+1,a,v) || a<0 || a>60 || fabs(v)>400) return "BAD_ANGLE";
  // Kalibrasyon dogrusal degil (kol-biyel): hizi o noktadaki yerel egimle darbeye cevir.
  double a0=fmax(0.0,a-0.5), a1=fmin(60.0,a+0.5);
  double egim=(motion.toSteps(a1)-motion.toSteps(a0))/(a1-a0);
  motion.stop();                                   // konum kipi bosta
  yorTilt.guncelle(motion.toSteps(a),v*egim,us);
  return nullptr;
}
const char* panYorunge(const char* s,uint32_t us) {
  if(!motion.armed) return "DISABLED";
  double a,v;
  if(!ikiSayi(s+2,a,v) || fabs(a)>PanCore::ACI_SINIR || fabs(v)>400) return "BAD_ANGLE";
  pan.stop();
  yorPan.guncelle(a*PanCore::STEP_PER_DEG,v*PanCore::STEP_PER_DEG,us);
  return nullptr;
}
const char* panCommand(const char* s,uint32_t us) {
  if(s[1]=='Y') return panYorunge(s,us);
  yorPan.durdur();                                 // her diger pan komutu yorungeyi keser
  if(!strcmp(s,"PR")) {if(pan.moving()) return "MOVING"; pan.zero(); return nullptr;}
  if(s[1]=='Z') {
    char* e; double h=strtod(s+2,&e);
    if(*e!=',') return "BAD_PROFILE";
    double iv=strtod(e+1,&e);
    if(*e) return "BAD_PROFILE";
    if(pan.moving()) return "MOVING";
    return pan.profile(h,iv)?nullptr:"BAD_PROFILE";
  }
  if(s[1]=='E') {
    if(!strcmp(s+2,"-")) {pinMode(PAN_EN_PIN,INPUT); panEnable=-1; return nullptr;}
    if(strcmp(s+2,"0") && strcmp(s+2,"1")) return "BAD_ENABLE";
    panEnable=s[2]-'0'; digitalWrite(PAN_EN_PIN,panEnable?HIGH:LOW); pinMode(PAN_EN_PIN,OUTPUT);
    return nullptr;
  }
  if(!motion.armed) return "DISABLED";
  char* e; double deg=strtod(s+1,&e);
  if(e==s+1 || *e) return "BAD_ANGLE";
  return pan.go(deg,us)?nullptr:"BAD_ANGLE";
}
// Lazer TEK yerden surulur. %100'de 2^COZ yazilir: 255 hala kisa bir LOW darbesi birakir.
int lazerDuty() {
  if(lazerYuzde>=100) return 1<<LAZER_PWM_COZ;
  return (lazerYuzde*(1<<LAZER_PWM_COZ))/100;
}
void lazerYaz(bool ac) {
  lazerAcik=ac && lazerPwmHazir;
  if(lazerAcik) sonAtesMs=millis();
  if(lazerPwmHazir) ledcWrite(LAZER_PIN,lazerAcik?lazerDuty():0);
  else digitalWrite(LAZER_PIN,LOW);
}
void herPortaYaz(const char* s) {for(Stream* io:links) io->println(s);}
// ACIL DURDURMA — seri STOP ve donanim butonu AYNI yoldan. Sira: once ates, sonra hareket.
// Kontrol (armed) KAPATILMAZ: nabiz surer, START'tan sonra hareket hemen devam edebilir;
// kilit ise ayri bayrakla (acilKilit) tutulur — PC'nin otomatik "E"si onu kaldiramaz.
void acilDurdur(const char* sebep) {
  lazerYaz(false);
  motion.stop(); pan.stop(); yorTilt.durdur(); yorPan.durdur();
  acilKilit=true;
  char s[96]; snprintf(s,sizeof(s),"SISTEM DURDURULDU %s",sebep); herPortaYaz(s);
}
void estopButonuOku() {
  static bool sonHam=false; static uint32_t degisim=0;
  bool ham=digitalRead(ESTOP_PIN)==LOW;
  if(ham!=sonHam) {sonHam=ham; degisim=millis(); return;}
  if(uint32_t(millis()-degisim)<ESTOP_DEBOUNCE_MS) return;
  if(ham && !estopButon) {estopButon=true; acilDurdur("(ACIL STOP BUTONU)");}
  else if(!ham && estopButon) {estopButon=false; herPortaYaz("ACIL STOP BUTONU BIRAKILDI - devam icin START");}
}
// Acil kilitte reddedilen HAREKET komutlari. X/D/H/E/Q/R/Z/V/PR/PZ/PE hareket baslatmaz.
bool hareketKomutu(const char* c) {
  if(!strcmp(c,"W") || !strcmp(c,"S") || !strcmp(c,"K")) return true;
  if(c[0]=='G' || c[0]=='C') return true;
  if(c[0]=='Y') return c[1]!='Q';
  if(c[0]=='P') return c[1]=='Y' || c[1]=='-' || c[1]=='+' || c[1]=='.' || (c[1]>='0' && c[1]<='9');
  return false;
}
// Lazer ve acil komutlari. Doner: true = komut burada islendi (err/sessiz ayarlanir).
bool lazerKomutu(const char* c,const char*& err,bool& sessiz) {
  if(!strcmp(c,"STOP")) {acilDurdur("(seri STOP)"); sessiz=true; return true;}
  if(!strcmp(c,"START")) {
    if(estopButon) {herPortaYaz("START REDDEDILDI - ACIL STOP BUTONU BASILI (SISTEM DURDURULDU)"); sessiz=true;}
    else {acilKilit=false; herPortaYaz("SISTEM BASLATILDI"); sessiz=true;}
    return true;
  }
  if(!strcmp(c,"L0")) {lazerYaz(false); return true;}
  if(!strcmp(c,"L1")) {
    if(acilKilit) err="ESTOP";
    else if(!motion.armed) err="DISARMED";
    else if(!lazerPwmHazir) err="LASER_PWM";
    else {sessiz=lazerAcik; lazerYaz(true);}   // tazeleme sessiz, ilk acilis OK yazar
    return true;
  }
  if(c[0]=='L' && c[1]=='P') {
    char* e; long y=strtol(c+2,&e,10);
    if(e==c+2 || *e || y<0 || y>100) {err="BAD_POWER"; return true;}
    lazerYuzde=(int)y; if(lazerAcik) lazerYaz(true);
    return true;
  }
  return false;
}
void readSerial(int port) {
  Stream& io=*links[port];
  PortInput& rx=inputs[port];
  for(int budget=0;budget<32 && io.available();++budget) {
    char c=(char)io.read();
    if(c=='\n') {
      if(rx.overflow) {motion.stop(true); io.println("ERR,LINE_TOO_LONG");}
      else if(rx.used) {
        rx.text[rx.used]=0;
        const char* command=rx.text;
        const char* err=nullptr;
        bool sessiz=false;
        if(!strcmp(command,"E")) {
          if(motion.armed && owner!=port) err="OTHER_PORT_ACTIVE";
          else owner=port;
        } else if(strcmp(command,"X") && strcmp(command,"D") && strcmp(command,"STOP") &&
                  strcmp(command,"L0") && owner>=0 && owner!=port) {
          // Durdurmak/kesmek (X, D, STOP, L0) HER porttan serbest; gerisi yalniz sahibinden.
          err="OTHER_PORT_ACTIVE";
        }
        if(!err && lazerKomutu(command,err,sessiz)) {}
        else if(!err && acilKilit && hareketKomutu(command)) err="ESTOP";
        else if(!err && !strcmp(command,"YQ")) {}
        else if(!err && command[0]=='P') err=panCommand(command,micros());
        else if(!err && command[0]=='Y') err=tiltYorunge(command,micros());
        else if(!err) {
          // H ve Q disindaki HER tilt komutu (G, X, D, E, R, K, W/S...) tilt yorungesini
          // keser; X/D ikisini birden (acil durdurma iki ekseni de durdurur).
          if(strcmp(command,"H") && strcmp(command,"Q")) yorTilt.durdur();
          if(!strcmp(command,"X") || !strcmp(command,"D")) yorPan.durdur();
          err=motion.command(command,millis(),micros());
          if(!err && !saveCalibration()) err="CAL_SAVE_FAILED";
          if(!strcmp(command,"X")) pan.stop();
        }
        // Kontrol kapandiysa (D, bozuk satir) lazer de soner: kilitli kart ates etmez.
        if(!motion.armed) {pan.stop(); yorTilt.durdur(); yorPan.durdur(); lazerYaz(false);}
        if(err) {io.print("ERR,");io.print(command);io.print(",");io.println(err);}
        // Sessiz komutlar: H (nabiz), W/S (jog kirasi), Y/PY (yorunge, 25-50 Hz), L1
        // tazelemesi (4 Hz), STOP/START (kendi metnini yazar) — her birine OK yazmak
        // UART0'in (115200) cogunu yemekteydi.
        else if(!sessiz && strcmp(command,"H") && strcmp(command,"W") && strcmp(command,"S") &&
                !(command[0]=='Y' && command[1]!='Q') && strncmp(command,"PY",2)) {
          io.print("OK,");io.println(command);
        }
      }
      rx.used=0;rx.overflow=false;
    } else if(c!='\r') {
      if(c<32 || c>126) rx.overflow=true;
      else if(rx.used<sizeof(rx.text)-1 && !rx.overflow) rx.text[rx.used++]=c;
      else rx.overflow=true;
    }
  }
}
void setup() {
  // ⚠ ILK IS: LAZER PININI ASAGI CEK (her seyden, seri porttan once). Kalan kacak sure
  // (ROM bootloader) yalniz donanimsal 10 kOhm pull-down ile kapanir.
  pinMode(LAZER_PIN,OUTPUT); digitalWrite(LAZER_PIN,LOW);
  lazerPwmHazir=ledcAttach(LAZER_PIN,LAZER_PWM_FREK,LAZER_PWM_COZ);
  lazerYaz(false);
  pinMode(ESTOP_PIN,INPUT_PULLUP);
  digitalWrite(STEP_PIN,LOW); pinMode(STEP_PIN,OUTPUT);
  digitalWrite(DIR_PIN,DIR_UP_HIGH?HIGH:LOW); pinMode(DIR_PIN,OUTPUT);
  digitalWrite(PAN_STEP_PIN,LOW); pinMode(PAN_STEP_PIN,OUTPUT);
  digitalWrite(PAN_DIR_PIN,PAN_DIR_POS_HIGH?HIGH:LOW); pinMode(PAN_DIR_PIN,OUTPUT);
  pinMode(PAN_EN_PIN,INPUT);
  Serial.begin(115200);
  Serial0.begin(115200);
  prefs.begin("cat-arm-v2",false); loadCalibration();
  if(!lazerPwmHazir) herPortaYaz("ERR,LASER_PWM,GPIO18");
  // Acilista buton zaten basiliysa kart KILITLI baslar (reset sonrasi hareket/ates yok).
  if(digitalRead(ESTOP_PIN)==LOW) {estopButon=true; acilDurdur("(ACIL STOP BUTONU - acilista basili)");}
}
// Tek fiziksel darbe (yon degisiminde DIR once oturur). Doner: yukselen kenar ani.
uint32_t tiltDarbe(int d) {
  static int lastDirection=0;
  if(d!=lastDirection) {
    digitalWrite(DIR_PIN,((d>0)==DIR_UP_HIGH)?HIGH:LOW);
    delayMicroseconds(DIR_SETUP_US); lastDirection=d;
  }
  uint32_t rising=micros();
  digitalWrite(STEP_PIN,HIGH); delayMicroseconds(STEP_HIGH_US);
  digitalWrite(STEP_PIN,LOW);
  return rising;
}
uint32_t panDarbe(int d) {
  static int lastPanDirection=0;
  if(d!=lastPanDirection) {
    digitalWrite(PAN_DIR_PIN,((d>0)==PAN_DIR_POS_HIGH)?HIGH:LOW);
    delayMicroseconds(DIR_SETUP_US); lastPanDirection=d;
  }
  uint32_t rising=micros();
  digitalWrite(PAN_STEP_PIN,HIGH); delayMicroseconds(STEP_HIGH_US);
  digitalWrite(PAN_STEP_PIN,LOW);
  return rising;
}
void loop() {
  estopButonuOku();                       // donanim acil stop: her seyden ONCE
  // Olu adam anahtari: PC L1 tazelemesini kesmisse (kablo, cokme, donma) lazer kart
  // tarafinda soner — "kes" komutunun gidebilecegine guvenilmez.
  if(lazerAcik && uint32_t(millis()-sonAtesMs)>ATES_ZAMAN_ASIMI_MS) {
    lazerYaz(false); herPortaYaz("LAZER KESILDI - tazeleme durdu (olu adam anahtari)");
  }
  motion.watchdog(millis()); readSerial(0); readSerial(1);
  // Watchdog (nabiz kaybi) veya D tilt'i kapattiysa pan, yorungeler ve LAZER de durur.
  if(!motion.armed) {pan.stop(); yorTilt.durdur(); yorPan.durdur(); if(lazerAcik) lazerYaz(false);}
  if(yorTilt.aktif) {
    int d=yorTilt.adim(micros(),motion.pos,motion.maxSpeed,motion.accel,0,motion.upper());
    if(d) {tiltDarbe(d); motion.izle(d);}
  } else {
    int d=motion.next(millis(),micros());
    if(d) motion.emitted(d,tiltDarbe(d));
  }
  if(yorPan.aktif) {
    int pd=yorPan.adim(micros(),pan.pos,pan.maxSpeed,pan.accel,-PanCore::SINIR,PanCore::SINIR);
    if(pd) {panDarbe(pd); pan.izle(pd);}
  } else {
    int pd=pan.next(micros());
    if(pd) pan.emitted(pd,panDarbe(pd));
  }
  static uint32_t last=0;
  // Durum yayini 20 ms'de bir (50 Hz; eskiden 100 ms). Otonom takip, kameranin gordugu
  // hatayi kolun O ANKI acisina ekler; aci 100 ms'de bir gelince ortalama 50 ms bayat
  // oluyor ve takip hesabi bozuluyordu. ~65 baytlik satir 50 Hz'de ~3.3 kB/s eder,
  // 115200 baud'un (~11.5 kB/s) rahatca altinda.
  if(uint32_t(millis()-last)>=20) {
    char out[150];
    int n=snprintf(out,sizeof(out),"STATE3,%ld,%ld,%ld,%d,%d,%d,%d,%.3f,%.3f,%d,%.3f,%d\n",
      (long)motion.pos,(long)motion.target,(long)motion.upper(),motion.calibrated(),
      motion.moving()||yorTilt.aktif,motion.armed,motion.calibrating,
      motion.angle(motion.pos),motion.angle(motion.target),motion.count,
      motion.points[motion.count-1].angle,motion.jogSpeed);
    if(n>0 && n<(int)sizeof(out)) {
      for(Stream* io:links) if(io->availableForWrite()>=n) io->write((uint8_t*)out,n);
    }
    // Pan durumu ayri satirda: STATE3 bicimi degismez (eski araclar bozulmaz).
    n=snprintf(out,sizeof(out),"PAN1,%ld,%ld,%d,%.3f,%.3f,%d\n",
      (long)pan.pos,(long)pan.target,pan.moving()||yorPan.aktif,pan.angle(),pan.goal(),panEnable);
    if(n>0 && n<(int)sizeof(out)) {
      for(Stream* io:links) if(io->availableForWrite()>=n) io->write((uint8_t*)out,n);
    }
    // Lazer/acil durumu: PC "kart lazer destekliyor mu", "gercekten yaniyor mu", "buton
    // basili mi" sorularini tek satirlik metin olayina degil bu surekli yayina dayandirir.
    n=snprintf(out,sizeof(out),"LZR1,%d,%d,%d,%d,%d\n",
      lazerAcik,lazerYuzde,acilKilit,estopButon,lazerPwmHazir);
    if(n>0 && n<(int)sizeof(out)) {
      for(Stream* io:links) if(io->availableForWrite()>=n) io->write((uint8_t*)out,n);
    }
    last=millis();
  }
}
