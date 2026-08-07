/*
  DERIN MAVI — ESP32 gimbal + lazer surusu
  ----------------------------------------
  Laptop (app/) ile konusulan protokolun TEK KAYNAGI: app/protokol.py
  Bir komut eklenecek/degistirilecekse ONCE orasi guncellenir, sonra burasi.

  Donanim:
    pan  motoru  : YATAY eksen (azimut)   — STEP 6, DIR 7, ENABLE 16
                   motor 15 disli -> buyuk cark 83 disli = 5.533:1 rediksiyon
    tilt motoru  : DIKEY eksen (yukselis) — STEP 4, DIR 5, ENABLE 17
    acil stop    : GPIO 15 — NO buton, GND'ye ceker (basili = LOW), dahili pull-up
    lazer        : GPIO 18 — **PWM tetik** (1 kHz), guc %0-100 arasi ayarlanir
    Surucu cozunurlugu: 6400 step/tur (1/32 mikroadim)

  Komutlar (ASCII satir, '\n' ile biter, buyuk/kucuk fark etmez):
    P<derece>   pan  MUTLAK hedef acisi      "P45.00"
    T<derece>   tilt MUTLAK hedef acisi      "T12.50"  (0..TILT_MAX arasina kirpilir)
    S<der/sn>   tavan hiz                    "S40.0"   ┐ hiz duzeyi (3 kademe)
    A<der/sn2>  ivme                         "A100.0"  ┘
    G<yuzde>    lazer GUCU (%0-100)          "G40"     — "ne kadar", kalici ayar
    L1 / L0     lazer ac / kes               — "ne zaman", ayarli gucte tetikler
                ⚠ L1 SUREKLI TAZELENMELIDIR: 1 sn tazeleme gelmezse kart lazeri kendi
                  keser (olu adam anahtari — kablo koparsa lazer yanik kalmasin).
    STOP        acil durdur: lazer kesilir, HER IKI EKSEN DE OLDUGU YERDE DONAR, komutlar
                reddedilir. Kart durulan konumu bildirir ("Konum P.. / T..").
                ⚠ Surucu ENABLE **KESILMEZ** (asagi bak).
    START       devam (acil stop BUTONU basiliyken REDDEDILIR)
    P<derece>N<sapma>  merkez etrafinda rastgele salinim (gosterim/test; hedef simulasyonu)

  ⚠ HIZ DERECE/SN ALINIR, step/sn DEGIL: iki eksenin disli orani farkli (pan'da 5.533:1
    rediksiyon var), ayni step/sn iki eksende bambaska aci hizi olurdu. Cevirimi burasi
    yapar; laptop her yerde DERECE konusur.

  KART: **ESP32-S3** (esptool ile dogrulandi: QFN56 rev v0.2, 8 MB PSRAM, CH343 USB-seri).
  Arduino IDE'de secilecek kart: "ESP32S3 Dev Module" (FQBN esp32:esp32:esp32s3).
  ⚠ "USB CDC On Boot" KAPALI kalmali: kart laptopa harici CH343 cipi (UART0) uzerinden
    bagli. Acik olursa Serial USB'ye gider ve laptop hicbir sey duymaz.

  ⚠ PIN NOTLARI (ESP32-S3'e gore — klasik ESP32'den FARKLI):
    - S3'te strapping pinleri: GPIO 0, 3, 45, 46. Kullandigimiz pinlerin HICBIRI bunlarda
      degil; yani acil stop butonu basiliyken reset atmak boot'u etkilemez ve lazer pini
      acilista kacak tetiklenmez. (Klasik ESP32'de GPIO 15 strapping'dir — orada bu iki
      uyari gecerliydi, S3'te degil.)
    - **S3'te GPIO 22/23/24/25 HIC YOKTUR** (klasik ESP32'de vardilar). Bu numaralara yazmak
      sessizce hicbir sey yapar — derleme hata VERMEZ. Lazer bu yuzden 25'ten 18'e alindi.
    - S3'te GPIO 26-32 dahili SPI flash icin, oktal PSRAM'li modullerde 33-37 de PSRAM icin
      ayrilidir. GPIO 43/44 = UART0 (CH343 uzerinden laptop), 19/20 = USB D-/D+.
      Kullandigimiz 4/5/6/7/15/16/17/18 pinlerinin tamami bu bolgelerin DISINDA ve gecerli.
*/

#include <AccelStepper.h>

// ---- Pinler ----
AccelStepper tiltMotor(AccelStepper::DRIVER, 4, 5);   // DIKEY eksen (STEP, DIR)
AccelStepper panMotor(AccelStepper::DRIVER, 6, 7);    // YATAY eksen (STEP, DIR)
const int PAN_EN_PIN  = 16;                           // pan surucusu ENABLE hatti
const int TILT_EN_PIN = 17;                           // tilt surucusu ENABLE hatti
const int ESTOP_PIN   = 15;                           // ACIL STOP BUTONU (NO, GND'ye ceker)
// ⚠ LAZER PINI **18**, 25 DEGIL. ESP32-S3'te GPIO 22/23/24/25 FIZIKSEL OLARAK YOKTUR
//   (soc_caps.h: SOC_GPIO_VALID_GPIO_MASK bu dordunu maskeden cikarir) — klasik ESP32'de
//   vardilar, S3'te yoklar. 25'e yazmak sessizce hicbir sey yapar: derleme hata vermez,
//   ledcAttach false doner, lazer hic tetiklenmez.
const int LAZER_PIN   = 18;                           // lazer PWM tetigi

// ---- LAZER GUCU (PWM) ----
// Lazer surucusunun PWM/TTL girisi duty oraniyla gucu belirler: %40 duty ≈ %40 ortalama
// optik guc. Tam guc istemiyoruz — G komutuyla ayarlanir, varsayilan %40.
// ⚠ FREKANS [VARSAYIM]: CNC lazer surucileri tipik olarak ~1 kHz PWM ile surulur (GRBL
//   varsayilani da budur). Modul tepki vermezse ONCE bu degeri deneyin (200 Hz / 5 kHz /
//   20 kHz); yanlis frekansta surucu sinyali hic gormeyebilir ya da titresim yapar.
const int LAZER_PWM_FREK = 1000;                      // Hz
const int LAZER_PWM_COZ  = 8;                         // bit -> 0..256 duty
const int LAZER_GUC_VARSAYILAN = 40;                  // % (app/protokol.py ile AYNI)
int lazerYuzde = LAZER_GUC_VARSAYILAN;

// ---- ATES OLU ADAM ANAHTARI (dead-man switch) ----
// Lazer ACIK kalmak icin laptop'tan SUREKLI "L1" tazelemesi bekler. Tazeleme kesilirse
// (seri kablo kopar, laptop coker, arayuz donar, USB cikar) kart lazeri KENDI KESER.
// Aksi halde "ates ac" komutu gitmis, "kes" komutu gidememis olur ve lazer sonsuza dek
// yanar — E-Stop butonuna basacak birinin orada olmasina bel baglanamaz.
// Laptop tarafi 250 ms'de bir tazeler (app/arayuz_qt.py ESP yoklamasi); 1 sn, birkac
// tazelemenin kacmasina tolerans birakir ama gercek kopmayi hizla yakalar.
const unsigned long ATES_ZAMAN_ASIMI_MS = 1000;
unsigned long sonAtesKomutu = 0;

// Surucu ENABLE polaritesi.
//   Olculen: ENABLE hatlarina HICBIR SEY BAGLI DEGILKEN motorlar calisiyor.
//   Bu, iki yaygin surucu ailesinde de boyledir (A4988/DRV8825'te EN dahili pull-down'li,
//   TB6600/HBS57'de opto akim yok) ve tek basina polariteyi BELIRLEMEZ. Asagidaki deger
//   yayginin (LOW = motor enerjili, HIGH = surucu serbest); motorlar E-Stop'ta serbest
//   kalmiyorsa false yapin.
//   ⚠ Yanlis polarite HAREKETI DURDURMAYI ENGELLEMEZ: acil durdurmada systemActive=false
//     olur ve run() hic cagrilmaz. ENABLE, ustune binen IKINCI guvenlik katmanidir.
const bool ENA_AKTIF_LOW = true;

// Acil stop butonu: NO (normalde acik), GND'ye ceker -> INPUT_PULLUP ile basili = LOW.
// ⚠ NO butonun zaafi: KABLO KOPARSA hat HIGH kalir ve buton "basilmamis" gorunur — yani
//   ariza sessizce E-Stop'u devre disi birakir. NC (normalde kapali) buton kablo kopmasinda
//   da sistemi durdurur; yarisma oncesi NC'ye gecmeniz onerilir (o zaman bu sabit false).
const bool ESTOP_AKTIF_LOW = true;
const unsigned long ESTOP_DEBOUNCE_MS = 30;

// ---- Mekanik (app/protokol.py'deki sabitlerle AYNI olmali) ----
const float STEP_PER_REV   = 6400.0;                  // surucu cozunurlugu (1/32)
const float PAN_GEAR_RATIO = 83.0 / 15.0;             // motor 15 disli -> cark 83 disli
// ⚠ GECICI: dikey eksende de rediksiyon VAR ama orani heniz olculmedi (ekip bildirecek).
//   1:1 kaldigi surece tilt acilari GERCEK acilar degildir — "60°" komutu gercekte
//   60/oran kadar dondurur. Oran gelince BU SATIR ve app/protokol.py TILT_DISLI birlikte
//   duzeltilecek.
const float TILT_GEAR_RATIO = 1.0;
const float PAN_STEPS_PER_DEG  = STEP_PER_REV * PAN_GEAR_RATIO / 360.0;   // ~98.37
const float TILT_STEPS_PER_DEG = STEP_PER_REV * TILT_GEAR_RATIO / 360.0;  // ~17.78

// AccelStepper adimlari yazilimla uretir; ESP32'de guvenli ust sinir kabaca budur.
// (app/protokol.py MAKS_STEP_SN ile ayni deger.)
const float MAX_STEP_SN = 8000.0;

// ---- Yazilimsal aci limitleri (app/protokol.py: TILT_MIN/TILT_MAX) ----
const float TILT_MIN = 0.0;                           // 0° = ufuk
const float TILT_MAX = 180.0;                         // tavan; negatif tilt YOK
// ⚠ app/protokol.py TILT_MAX ile AYNI olmali. 07.08'de 60 -> 90 -> 180 yukseltildi.
//   Arayuz acilista 90'da baslar; operator daha yukarisini ⚙ panelinden acar.

bool systemActive = true;
bool laserOn = false;
bool estopButonBasili = false;

// Hiz duzeyi "Normal" degerleri (app/protokol.py HIZ_TABLO)
float hizDerSn = 40.0;
float ivmeDerSn2 = 100.0;

// Pan Hafizasi
float panBaseDegree = 0;
float panNoiseDegree = 0;
bool panNoiseActive = false;

// Tilt Hafizasi
float tiltBaseDegree = 0;
float tiltNoiseDegree = 0;
bool tiltNoiseActive = false;

// ---- Tekil kapilar: lazer ve surucu enerjisi TEK yerden surulur ----
// Lazer duty'si TEK yerden hesaplanir: kapaliyken 0 (pin surekli LOW), acikken ayarli yuzde.
// %100 istendiginde 2^COZ yazilir (255 degil): 8 bit'te 255 hala kisa bir LOW darbesi
// birakir, 256 pini SUREKLI HIGH yapar.
int lazerDuty() {
  if (lazerYuzde >= 100) return (1 << LAZER_PWM_COZ);
  return ((long)lazerYuzde * (1 << LAZER_PWM_COZ)) / 100;
}

void setLaser(bool on) {
  laserOn = on;
  if (on) sonAtesKomutu = millis();        // olu adam anahtarini tazele
  ledcWrite(LAZER_PIN, on ? lazerDuty() : 0);
}

// ⚠ SURUCU ENABLE **HIC KESILMEZ** (07.08 takim karari). setup()'ta bir kez enerjilenir
//   ve bir daha DOKUNULMAZ — bu yuzden `setDrivers(false)` diye bir yol YOKTUR.
//
//   NEDEN: kapali cevrim (closed-loop) surucude ENABLE kesilince rotor serbest kalir,
//   mil kayar (dikey eksen yer cekimiyle duser) ve surucunun encoder'i bu kaymayi
//   izlemeye devam eder. ENABLE geri verildiginde servo dongusu biriken pozisyon
//   hatasini KENDI maksimum hiziyla kapatir -> acil durdurmadan cikista gimbal ANIDEN
//   FIRLAR. Bu hareketi ESP32 uretmez (distanceToGo() sifirdir), dolayisiyla hiz
//   kademesi de sinirlamaz. Sahada gozlendi ve ENABLE kesmenin bedeli oldugu dogrulandi.
//
//   Hareketi durduran sey zaten `systemActive = false`: o durumda komut kabul edilmez ve
//   pan hedefi konumuna kilitlenir. ENABLE ikinci bir katmandi; bedeli faydasindan buyuktu.
void enableAc() {
  int seviye = ENA_AKTIF_LOW ? LOW : HIGH;
  digitalWrite(PAN_EN_PIN, seviye);
  digitalWrite(TILT_EN_PIN, seviye);
}

// Hiz duzeyini iki eksene de uygular (derece -> step cevirimi burada).
void hizUygula() {
  float panHiz  = min(hizDerSn * PAN_STEPS_PER_DEG,  MAX_STEP_SN);
  float tiltHiz = min(hizDerSn * TILT_STEPS_PER_DEG, MAX_STEP_SN);
  panMotor.setMaxSpeed(panHiz);
  tiltMotor.setMaxSpeed(tiltHiz);
  panMotor.setAcceleration(ivmeDerSn2 * PAN_STEPS_PER_DEG);
  tiltMotor.setAcceleration(ivmeDerSn2 * TILT_STEPS_PER_DEG);
}

// ACIL DURDURMA — seri STOP ve donanim butonu AYNI yoldan gecer (tek kapi).
// Sira onemli: once ATES kesilir, sonra hareket.
void acilDurdur(const char* sebep) {
  setLaser(false);                                    // 1. ONCE ATES KESILIR

  // 2. IKI EKSEN DE OLDUGU YERDE DONAR: hedef = o anki konum -> distanceToGo() sifir.
  //    ⚠ SARTNAME (Yetenek 3): "hareket ederken E-Stop -> SISTEM DURUR". Bir sure
  //    tilt'i 0° park konumuna indiriyorduk (lazerli namlu yukarida kalmasin diye); o
  //    da bir HAREKETTIR ve videoda "durmadi" gibi degerlendirilebilirdi. Kaldirildi:
  //    acil durdurmada sistemin ureettigi hicbir hareket YOKTUR.
  float panKonum = panMotor.currentPosition() / PAN_STEPS_PER_DEG;
  float tiltKonum = tiltMotor.currentPosition() / TILT_STEPS_PER_DEG;
  panMotor.moveTo(panMotor.currentPosition());
  tiltMotor.moveTo(tiltMotor.currentPosition());
  panBaseDegree = panKonum;
  tiltBaseDegree = tiltKonum;

  panNoiseActive = false;
  tiltNoiseActive = false;

  // ⚠ ENABLE'A DOKUNULMAZ ve konum sayaci SIFIRLANMAZ: motorlar tuttugu icin mil
  //   kaymaz, dolayisiyla referans gecerli kalir. (Eskiden ENABLE kesiliyor, mil
  //   kayiyor ve bu yuzden konumu sifir kabul etmek ZORUNDA kaliyorduk — o da her
  //   acil durdurmada mutlak acilari kaydiriyordu. Ikisi de artik gerekmiyor.)
  systemActive = false;                               // 3. KOMUTLAR REDDEDILIR

  // 4. DURULAN KONUM BILDIRILIR. Laptop'un hedefi ile kartin hedefi burada AYRISIR:
  //    kart hedefi "durdugum yer"e ceker, laptop ise son komut ettigi aciyi bilir.
  //    Bildirilmezse acil durdurmadan sonra ekrandaki aci gercek konumu gostermez.
  //    ⚠ Seri cikti SAF ASCII: laptop 'ascii' ile cozuyor, Windows konsolu (cp1254)
  //      '°' gibi karakterlerde patliyor.
  Serial.print("SISTEM DURDURULDU! ");
  Serial.print(sebep);
  Serial.print(" Konum P");
  Serial.print(panKonum, 2);
  Serial.print(" / T");
  Serial.print(tiltKonum, 2);
  Serial.println();
}

// NOT (07.08): Bu bolumde eskiden "acil durdurmada motorlar serbest birakilir, DEVAM'da
// mevcut konum sifir kabul edilir" yazardi. Kapali cevrim surucude bunun bedeli sahada
// gorulunce (ENABLE geri gelince gimbal aniden firliyordu) iki kural da kaldirildi:
// motorlar artik TUTAR, mil kaymaz, referans korunur.

void estopButonuOku() {
  static bool sonOkuma = false;
  static unsigned long sonDegisim = 0;

  bool ham = (digitalRead(ESTOP_PIN) == (ESTOP_AKTIF_LOW ? LOW : HIGH));
  if (ham != sonOkuma) {                    // sicrama (bounce) filtresi
    sonOkuma = ham;
    sonDegisim = millis();
    return;
  }
  if (millis() - sonDegisim < ESTOP_DEBOUNCE_MS) return;

  if (ham && !estopButonBasili) {
    estopButonBasili = true;
    acilDurdur("(ACIL STOP BUTONU)");
  } else if (!ham && estopButonBasili) {
    // Buton birakildi: sistem KENDILIGINDEN BASLAMAZ. Operator arayuzden DEVAM ET
    // demeli — acil durdurmadan cikis her zaman bilincli bir eylem olmalidir.
    estopButonBasili = false;
    Serial.println("ACIL STOP BUTONU BIRAKILDI — devam icin START bekleniyor.");
  }
}

void setup() {
  // ⚠ ILK IS: LAZER PININI ASAGI CEK. Seri porttan once, her seyden once. Kart reset
  //   attigi anda (yukleme, guc dalgalanmasi, watchdog) pin ROM bootloader boyunca
  //   YUKSEK EMPEDANSTA (float) kalir; lazer surucusunun girisi pull-down'li degilse
  //   bu sure boyunca kacak tetiklenebilir. Buradaki iki satir o sureyi kullanici
  //   kodunun basladigi ana kadar KISALTIR ama SIFIRLAMAZ — ROM bootloader'i etkileyemeyiz.
  //   ⚠ TEK GERCEK COZUM DONANIMSAL: sinyal hattina 10 kΩ pull-down (LAZER_PIN <-> GND).
  pinMode(LAZER_PIN, OUTPUT);
  digitalWrite(LAZER_PIN, LOW);

  Serial.begin(115200);
  // readStringUntil VARSAYILAN OLARAK 1 SANIYE bloklar. Bir komut parcali gelirse
  // (satir sonu heniz ulasmadiysa) loop() o sure boyunca durur ve AccelStepper.run()
  // cagrilmadigi icin motorlar adim kacirir — takip sirasinda gorunur bir takilma olur.
  // 20 ms, 115200 baud'da bir satirin gelmesi icin fazlasiyla yeterli (~10 bayt ≈ 1 ms).
  Serial.setTimeout(20);

  // Donusu KONTROL EDILIYOR: gecersiz bir GPIO verilirse (or. S3'te olmayan 25) ledcAttach
  // sessizce false doner ve lazer hic tetiklenmez — bir kez basimiza geldi, banner'da gorelim.
  bool pwmTamam = ledcAttach(LAZER_PIN, LAZER_PWM_FREK, LAZER_PWM_COZ);
  setLaser(false);                                    // acilista lazer KAPALI (duty 0)
  pinMode(PAN_EN_PIN, OUTPUT);
  pinMode(TILT_EN_PIN, OUTPUT);
  enableAc();                                         // ILK VE SON KEZ: bir daha kesilmez
  pinMode(ESTOP_PIN, ESTOP_AKTIF_LOW ? INPUT_PULLUP : INPUT_PULLDOWN);

  hizUygula();                                        // Normal duzey
  randomSeed(analogRead(0));

  Serial.println("-------------------------------------------------");
  Serial.println("SISTEM AKTIF! (Gimbal + Lazer + Acil Stop)");
  Serial.println("Komutlar: P<der> T<der> S<der/sn> A<der/sn2> G<%> L1/L0 STOP START");
  // Laptop bu satiri okuyup KENDI TILT_MAX'i ile karsilastirir. Firmware guncellenmeyi
  // unutulursa iki taraf farkli tavan bilir ve gimbal sessizce eski limitte takilir
  // (07.08'de tam bu yasandi: ekran 120 yaziyordu, kart 90'da kirpiyordu).
  Serial.print("TILT_MAX: "); Serial.println(TILT_MAX, 1);
  Serial.print("Lazer: GPIO "); Serial.print(LAZER_PIN);
  Serial.print(" PWM "); Serial.print(LAZER_PWM_FREK); Serial.print(" Hz, guc %");
  Serial.println(lazerYuzde);
  if (!pwmTamam) {
    Serial.print("!!! LAZER PWM KURULAMADI — GPIO "); Serial.print(LAZER_PIN);
    Serial.println(" bu kartta gecersiz olabilir (S3'te 22/23/24/25 YOKTUR)");
  }
  Serial.println("-------------------------------------------------");

  // Acilista buton zaten basiliysa hemen durdur (reset sonrasi hareket etmesin).
  if (digitalRead(ESTOP_PIN) == (ESTOP_AKTIF_LOW ? LOW : HIGH)) {
    estopButonBasili = true;
    acilDurdur("(ACIL STOP BUTONU — acilista basili)");
  }
}

void loop() {
  // 0. DONANIM ACIL STOP — her seyden once, her donguda okunur.
  estopButonuOku();

  // 0.5 ATES OLU ADAM ANAHTARI — laptop tazelemeyi kesmisse lazeri kart KENDI keser.
  if (laserOn && millis() - sonAtesKomutu > ATES_ZAMAN_ASIMI_MS) {
    setLaser(false);
    Serial.println("LAZER KESILDI — laptop tazelemesi durdu (olu adam anahtari)");
  }

  // 1. SERI KOMUTLAR
  if (Serial.available() > 0) {
    String komut = Serial.readStringUntil('\n');
    komut.trim();
    komut.toUpperCase();

    if (komut == "STOP") {
      acilDurdur("Motorlar kilitli, lazer kapali.");
    }
    else if (komut == "START") {
      if (estopButonBasili) {
        // Fiziksel buton basiliyken yazilimdan devam ETTIRILEMEZ. Metinde "DURDURUL"
        // gecer ki laptop tarafi E-Stop'ta kaldigimizi gorsun (app/protokol.py).
        Serial.println("START REDDEDILDI — ACIL STOP BUTONU BASILI (SISTEM DURDURULDU)");
      } else {
        // ⚠ KONUM SIFIRLANMAZ. Motorlar acil durdurma boyunca ENERJILI kaldi (ENABLE
        //   hic kesilmiyor), yani mil kaymadi ve sayac gercegi gostermeye devam ediyor.
        //   Sifir kabulu, ENABLE'in kesildigi eski tasarimin ZORUNLU telafisiydi; artik
        //   hem gereksiz hem zararli olurdu (her acil durdurma mutlak acilari kaydirirdi).
        //   Hedefler oldugu gibi kalir: pan konumuna kilitliydi, tilt 0° parkinda.
        panNoiseActive = false;
        tiltNoiseActive = false;
        systemActive = true;
        Serial.print("SISTEM BASLATILDI! Referans korundu (P");
        Serial.print(panMotor.currentPosition() / PAN_STEPS_PER_DEG, 2);
        Serial.print(" / T");
        Serial.print(tiltMotor.currentPosition() / TILT_STEPS_PER_DEG, 2);
        Serial.println(")");
      }
    }
    else if (systemActive && komut.length() > 0) {
      char eksen = komut.charAt(0);

      // --- TESHIS: X<pin> — verilen GPIO'ya dogrudan adim darbesi gonder ---
      // AccelStepper'i BYPASS eder. "Motor donmuyor" durumunda soruyu ikiye ayirir:
      // darbe gonderince motor donuyorsa ESP32 pini + kablo + surucu saglamdir, sorun
      // yazilim yapilandirmasindadir; donmuyorsa o hat fiziksel olarak kopuktur.
      // Or. "X4" = tilt STEP pini, "X6" = pan STEP pini (calisan eksen, kiyas icin).
      if (eksen == 'X') {
        int pin = komut.substring(1).toInt();
        pinMode(pin, OUTPUT);
        for (int i = 0; i < 2000; i++) {        // 2000 adim ≈ 1/3 tur (6400 step/tur)
          digitalWrite(pin, HIGH); delayMicroseconds(300);
          digitalWrite(pin, LOW);  delayMicroseconds(300);
        }
        Serial.print(">>> TESHIS: GPIO "); Serial.print(pin);
        Serial.println(" pinine 2000 adim darbesi gonderildi");
      }
      // --- LAZER GUCU (%) ---
      // "Ne kadar" (G) ile "ne zaman" (L) ayri tutuldu — hiz duzeyindeki S/A ile P/T
      // ayrimiyla ayni desen. L<yuzde> yapilsaydi mevcut "L1" sessizce %1 guce duserdi:
      // kod calisir gorunur, lazer yanmazdi.
      else if (eksen == 'G') {
        int yeni = komut.substring(1).toInt();
        lazerYuzde = constrain(yeni, 0, 100);
        if (laserOn) setLaser(true);            // ates sirasinda degisirse aninda uygulanir
        Serial.print(">>> LAZER GUCU: %"); Serial.println(lazerYuzde);
      }
      // --- LAZER AC/KES ---
      else if (eksen == 'L') {
        setLaser(komut.substring(1).toFloat() != 0);
        Serial.print(laserOn ? "LAZER ACIK (%" : "LAZER KAPALI (%");
        Serial.print(lazerYuzde); Serial.println(")");
      }
      // --- TAVAN HIZ (derece/sn) ---
      else if (eksen == 'S') {
        float yeni = komut.substring(1).toFloat();
        if (yeni > 0) {
          hizDerSn = yeni;
          hizUygula();
          Serial.print(">>> YENI TAVAN HIZ AYARLANDI: ");
          Serial.print(hizDerSn); Serial.println(" der/sn");
        }
      }
      // --- IVME (derece/sn2) ---
      else if (eksen == 'A') {
        float yeni = komut.substring(1).toFloat();
        if (yeni > 0) {
          ivmeDerSn2 = yeni;
          hizUygula();
          Serial.print(">>> YENI IVME AYARLANDI: ");
          Serial.print(ivmeDerSn2); Serial.println(" der/sn2");
        }
      }
      // --- PAN VE TILT KONTROLU (MUTLAK aci) ---
      else if (eksen == 'P' || eksen == 'T') {
        int nIndex = komut.indexOf('N');
        float derece = 0;
        float noise = 0;
        bool hasNoise = false;

        if (nIndex != -1) {
          derece = komut.substring(1, nIndex).toFloat();
          noise = komut.substring(nIndex + 1).toFloat();
          hasNoise = true;
        } else {
          derece = komut.substring(1).toFloat();
        }

        if (eksen == 'P') {
          // Pan SARMASIZ gelir (350 -> 370), boylece kisa yoldan doner.
          panBaseDegree = derece;
          panNoiseDegree = noise;
          panNoiseActive = hasNoise;

          panMotor.moveTo(panBaseDegree * PAN_STEPS_PER_DEG);

          Serial.print("PAN Merkez: "); Serial.print(derece);
          if (hasNoise) { Serial.print(" | Sinir: "); Serial.print(derece - noise); Serial.print(" ile "); Serial.print(derece + noise); }
          Serial.println();
        }
        else if (eksen == 'T') {
          // Yazilimsal limit: mekanigi elle verilen komuttan da koru.
          derece = constrain(derece, TILT_MIN, TILT_MAX);
          noise = constrain(noise, 0.0, TILT_MAX - TILT_MIN);

          tiltBaseDegree = derece;
          tiltNoiseDegree = noise;
          tiltNoiseActive = hasNoise;

          tiltMotor.moveTo(tiltBaseDegree * TILT_STEPS_PER_DEG);

          Serial.print("TILT Merkez: "); Serial.print(derece);
          if (hasNoise) { Serial.print(" | Sinir: "); Serial.print(derece - noise); Serial.print(" ile "); Serial.print(derece + noise); }
          Serial.println();
        }
      }
    }
  }

  // 2. MERKEZE KILITLI NOISE URETIMI (gosterim/test: hareketli hedef taklidi)
  if (systemActive) {

    if (panNoiseActive && panMotor.distanceToGo() == 0) {
      long minPos = (panBaseDegree - panNoiseDegree) * PAN_STEPS_PER_DEG;
      long maxPos = (panBaseDegree + panNoiseDegree) * PAN_STEPS_PER_DEG;
      long randPos = random(minPos, maxPos + 1);
      panMotor.moveTo(randPos);
    }

    if (tiltNoiseActive && tiltMotor.distanceToGo() == 0) {
      long minPos = constrain(tiltBaseDegree - tiltNoiseDegree, TILT_MIN, TILT_MAX) * TILT_STEPS_PER_DEG;
      long maxPos = constrain(tiltBaseDegree + tiltNoiseDegree, TILT_MIN, TILT_MAX) * TILT_STEPS_PER_DEG;
      long randPos = random(minPos, maxPos + 1);
      tiltMotor.moveTo(randPos);
    }

    // 3. MOTORLARI SUR
    panMotor.run();
    tiltMotor.run();
  }
  // ACIL DURDURMADA hicbir motor SURULMEZ: run() cagrilmadigi icin tek bir adim bile
  // uretilmez (sartname Yetenek 3 — "sistem durur"). Bir sure burada tilt'i park
  // konumuna indiren bir dal vardi; sartnameye uygunluk icin kaldirildi.
}
