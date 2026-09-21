# -*- coding: utf-8 -*-
"""DERIN MAVI — TILT KARTI TESHIS ARACI (arayuzsuz, kamerasiz, modelsiz).

"Motor donmuyor" dendiginde ilk calistirilacak sey budur. Arayuzun kullandigi
GERCEK surucuyle (tilt_surucu.TiltSurucu) konusur, ama Qt/kamera/YOLO yuklemez —
yani sorunun arayuzde mi yoksa kart hattinda mi oldugunu ayirir.

Kullanim:
    python app/tilt_tani.py                 # portlari listele
    python app/tilt_tani.py COM3            # baglan ve tesihis et (MOTOR DONMEZ)
    python app/tilt_tani.py COM3 --git 10   # 10 dereceye git (⚠ MOTOR DONER)
    python app/tilt_tani.py mock            # araci kendi kendine dene
    python app/tilt_tani.py auto --sifirla  # KOL EN ALTTAYKEN: sayaci 0 kabul ettir

⚠ --git verilmeden MOTOR DONDURULMEZ. Once kolun onunde kimse/engel olmadigini
  dogrula; kol 0..60 derece arasinda hareket eder.
"""
import sys
import time

import tilt_surucu as T

IYI, KOTU, BILGI = "[ OK ]", "[HATA]", "[bilgi]"


def portlari_yaz():
    try:
        from serial.tools import list_ports
    except ImportError:
        print(f"{KOTU} pyserial kurulu degil:  python -m pip install pyserial")
        return
    portlar = list(list_ports.comports())
    if not portlar:
        print(f"{KOTU} Hic seri port bulunamadi. USB kablosunu ve surucuyu kontrol et.")
        return
    print("Bulunan seri portlar:")
    for p in portlar:
        print(f"   {p.device:8} {p.description}")


def teshis(kaynak, hedef_aci=None, sure=3.0):
    print(f"\n=== TILT KARTI TESHISI — kaynak: {kaynak} ===\n")

    s = T.TiltSurucu(kaynak)
    if not s.bagli:
        print(f"{KOTU} Port acilamadi: {s.hata}")
        print("      • Port adi dogru mu? (Aygit Yoneticisi > Baglanti noktalari)")
        print("      • ws_motor_test/keyboard_control.py veya Arduino Seri Monitoru")
        print("        ACIK MI? Ayni portu iki uygulama acamaz — kapat.")
        return False
    print(f"{IYI} Port acildi.")

    # --- 1. Kart konusuyor mu? ---
    baslangic = time.time()
    while time.time() - baslangic < sure:
        s.yokla()
        time.sleep(0.05)

    if not s.taze:
        print(f"{KOTU} Karttan STATE3 durum paketi GELMIYOR ({sure:.0f} sn beklendi).")
        print("      Gorulen ham satirlar:", s.satirlar[-5:] or "(hicbiri)")
        print("      • Yanlis port olabilir (kartin IKI portu gorunebilir: COM3/COM4).")
        print("      • Kartta ESKI firmware olabilir: ws_motor_test/esp32_ws_test")
        print("        yuklenmeli (eski surum 'STATE,' yazar, yenisi 'STATE3,').")
        print("      • Baud 115200 olmali.")
        s.kapat(kalici=True)
        return False
    print(f"{IYI} Kart konusuyor — STATE3 aliniyor.")

    # --- 2. Kalibrasyon ---
    if not s.kalibre:
        print(f"{KOTU} Kart KALIBRE DEGIL. Bu durumda firmware hicbir hareket")
        print("      komutunu kabul etmez (CAL_REQUIRED) — motorun donmemesinin")
        print("      en sik sebebi budur.")
        print("      Cozum: kolu fiziksel olarak en alta indir, sonra")
        print("        python ws_motor_test/keyboard_control.py --port " + str(kaynak))
        print("      ile 0 -> 60 derece kalibrasyonunu yap (bir kez; kart saklar).")
        s.kapat(kalici=True)
        return False
    print(f"{IYI} Kart kalibre — kayitli nokta: {s.durum['nokta']}, "
          f"ust sinir: {s.durum['upper']} darbe.")

    # --- 3. Kontrol acildi mi? ---
    if not s.acik:
        print(f"{KOTU} Kontrol ACILMADI (armed=0). Surucu 'E' yolluyor ama kart")
        print("      kabul etmiyor. Gorulen satirlar:", s.satirlar[-5:] or "(hicbiri)")
        print("      • Baska bir uygulama kartta kontrolu acmis olabilir")
        print("        (OTHER_PORT_ACTIVE) — keyboard_control.py'yi kapat.")
        s.kapat(kalici=True)
        return False
    print(f"{IYI} Kontrol acik (armed).")
    print(f"{IYI} Kolun BILDIRDIGI aci: {s.aci:.2f}°   (hedef {s.hedef_aci:.2f}°)")

    if s.satirlar:
        print(f"{BILGI} Karttan gelen son metinler: {s.satirlar[-5:]}")

    # --- 4. Hareket testi (yalniz istenirse) ---
    if hedef_aci is None:
        print(f"\n{BILGI} Hareket denenmedi. Denemek icin:  "
              f"python app/tilt_tani.py {kaynak} --git <aci>")
        s.kapat(kalici=True)
        return True

    hedef = T.aci_kirp(hedef_aci)
    basla = s.aci
    print(f"\n{BILGI} HAREKET TESTI: {basla:.2f}° -> {hedef:.2f}°  (DIKKAT: kol donuyor)")
    s.git(hedef)

    son_yazma, zaman_asimi = 0.0, time.time() + 25.0
    while time.time() < zaman_asimi:
        s.yokla()
        time.sleep(0.05)
        if time.time() - son_yazma >= 0.5:
            son_yazma = time.time()
            print(f"      aci {s.aci:6.2f}°   hedef {s.hedef_aci:6.2f}°   "
                  f"{'HAREKET' if s.hareket else 'duruyor '}")
        if not s.hareket and s._bekleyen_hedef is None and abs(s.aci - hedef) < 0.2:
            break

    varilan = s.aci
    oynadi = abs(varilan - basla)
    if oynadi < 0.2 and abs(hedef - basla) >= 0.2:
        print(f"{KOTU} Kol HIC OYNAMADI ({basla:.2f}° -> {varilan:.2f}°).")
        print("      Kart komutu kabul etti ama mil donmedi ise sorun ELEKTRIK/MEKANIK:")
        print("      • HSD57 sürücüye ENABLE veriliyor mu, alarm LED'i yaniyor mu?")
        print("      • GPIO4=PULSE, GPIO5=DIR kablolari ve ORTAK GND baglilar mi?")
        print("      • Surucu 6400 pulse/tur ayarinda mi (DIP anahtarlar)?")
        print("      • Motor besleme gerilimi var mi?")
        print("      Gorulen satirlar:", s.satirlar[-5:] or "(hicbiri)")
        s.kapat(kalici=True)
        return False

    print(f"{IYI} Kol hareket etti: {basla:.2f}° -> {varilan:.2f}° (hedef {hedef:.2f}°)")
    if abs(varilan - hedef) > 1.0:
        print(f"{BILGI} Hedefe tam oturmadi ({abs(varilan - hedef):.2f}° fark). "
              f"Kalibrasyon tablosu veya mekanik dayama gozden gecirilmeli.")
    s.kapat(kalici=True)
    return True


if __name__ == "__main__":
    args = [a for a in sys.argv[1:]]
    if not args:
        portlari_yaz()
        print("\nKullanim:  python app/tilt_tani.py COM3  [--git <aci>]")
        raise SystemExit(0)

    kaynak = args[0]
    if "--sifirla" in args:
        # Kol fiziksel olarak en alttayken: kartin sayacini 0 kabul ettir (R).
        s = T.TiltSurucu(kaynak)
        t0 = time.time()
        while time.time() - t0 < 1.0:
            s.yokla(); time.sleep(0.02)
        print(f"sifirlamadan once kartin sandigi aci: {s.aci}")
        s.sifirla()
        t0 = time.time()
        while time.time() - t0 < 0.6:
            s.yokla(); time.sleep(0.02)
        print(f"sifirlamadan sonra: {s.aci}  | {s.hata or 'OK'}")
        s.kapat(kalici=True)
        raise SystemExit(0)
    hedef = None
    if "--git" in args:
        i = args.index("--git")
        if i + 1 >= len(args):
            raise SystemExit("--git bir aci ister, ornek: --git 10")
        hedef = float(args[i + 1].replace(",", "."))

    raise SystemExit(0 if teshis(kaynak, hedef) else 1)
