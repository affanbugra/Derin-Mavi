# -*- coding: utf-8 -*-
"""DERIN MAVI — CANLI DIKEY TAKIP TESTI (gercek kamera + gercek model + gercek kart).

Arayuzu (PySide6) acmadan otonom dikey takibi gercek donanimda dener ve OLCER:
her karede hedefin kadraj merkezine dikey uzakligi (px), kolun olculen acisi ve
gonderilen komut kaydedilir. Soru: hedefi yakaliyor mu, ne kadar surede, asiyor mu?

Zincir arayuzdekiyle ayni:
    kamera -> algi.analiz_et (YOLO + ByteTrack + kilit) -> algi.nisan_noktasi
      -> nisan.PDNisanci.adim -> [_nisan_geldi aynasi: hiz kirpma + mesgul kapisi,
         taban = olculen aci] -> kontrol.Kontrol.aci -> tilt karti

Kart nabzi AYRI bir is parcaciginda atar: YOLO cikarimi yuzlerce ms surebilir ve
bu sirada nabiz kesilirse kart 350 ms'de kendini kilitler (arayuzde de nabiz
ayri zamanlayicida, bkz. arayuz_qt TILT_NABIZ_MS).

⚠ AYNA UYARISI: _nisan_geldi'nin dikey kismi burada yeniden yazili (Qt olmadan
calissin diye). arayuz_qt._nisan_geldi degisirse burasi da degismeli.

Kullanim:
    python app/tilt_canli_takip.py [sure_sn=10] [baslangic_aci=14]
"""
import csv
import math
import os
import sys
import threading
import time

import cv2

import algi
import nisan
import protokol as P
import tilt_takip_testi as tt
from kontrol import Kontrol

# arayuz_qt.py sabitlerinin aynasi
NISAN_MESGUL_ORANI = 0.4
NISAN_MIN_ARALIK = 0.04


def main(sure=10.0, baslangic=14.0, kayit_dizin=None, kp=None, gecikme=0.0, kd=None):
    kaynak = tt.kayitli_ayarlari_yukle()
    if kp is not None:
        algi.ayar_guncelle(kp=kp)          # bu calistirma icin; ayarlar.json DEGISMEZ
    if kd is not None:
        algi.ayar_guncelle(kd=kd)
    from ultralytics import YOLO
    model = YOLO(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "models", "best.pt"), task="detect")
    cap = algi.open_camera()
    if cap is None:
        print("[HATA] kamera acilamadi"); return 2
    algi.analiz_et(model, cap.read()[1])            # isinma: ilk cagri yavas

    k = Kontrol("off", tilt_kaynak="auto")
    if not k.tilt_ayri:
        print("[HATA] tilt karti yok:", k.tilt.hata); return 2
    kilit = threading.Lock()
    calis = [True]

    def nabiz():
        while calis[0]:
            with kilit:
                k.oku()
            time.sleep(0.05)
    threading.Thread(target=nabiz, daemon=True).start()
    time.sleep(1.0)

    with kilit:
        k.hiz_ayarla(P.H_NORMAL)
        k.aci(0.0, baslangic)
    time.sleep(2.5)
    # Kol baslangic acisina giderken kamera tamponunda HAREKET ONCESI kareler kalir.
    # Ilk canli testte bunlardan biri "hedef ustte" dedi ve kol 0.2 sn ters yone
    # kipirdadi. Takip baslamadan once atilir.
    for _ in range(10):
        cap.read()
    algi.takip_sifirla()
    nisanci = nisan.PDNisanci()
    hiz_seviye = P.H_NORMAL
    son_t, mesgul_ta = None, 0.0

    if kayit_dizin:
        os.makedirs(kayit_dizin, exist_ok=True)
    satirlar = []
    t0 = time.time()
    son_foto = -1.0
    print(f"gecikme telafisi {gecikme*1000:.0f} ms | ayar: {kaynak} | kp={algi.AYAR['kp']} kd={algi.AYAR['kd']} "
          f"nisan_govde={algi.AYAR.get('nisan_govde')} fov={algi.AYAR['fov']}")
    print(f"baslangic kol {k.tilt_olculen:.1f} derece — takip basliyor ({sure:.0f} sn)")

    while time.time() - t0 < sure:
        ok, kare = cap.read()
        t_okuma = time.time()
        if not ok:
            continue
        h, w = kare.shape[:2]
        dets, balonlar, ai = algi.analiz_et(model, kare)
        simdi = time.time()
        t = simdi - t0
        with kilit:
            kol = k.tilt_olculen
            hareket = k.tilt.hareket
            # GECIKME TELAFISI: hata, karenin CEKILDIGI andaki kol acisina eklenir
            # (bkz. TiltSurucu.aci_zamaninda). gecikme=0 -> eski davranis (simdiki aci).
            kol_kare = k.tilt.aci_zamaninda(t_okuma - gecikme) if gecikme > 0 else kol
        hata_px, komut = None, None
        if 0 <= ai < len(dets) and not dets[ai].get("hayalet"):
            kutu = dets[ai]["box"]
            hx, hy = algi.nisan_noktasi(kutu, balonlar)
            hata_px = hy - h * 0.5
            _, d_pitch = nisanci.adim((hx, hy), (w, h), simdi=simdi,
                                      hedef_yukseklik=abs(kutu[3] - kutu[1]))
            # ---- arayuz_qt._nisan_geldi aynasi (dikey) ----
            if d_pitch and simdi >= mesgul_ta and kol is not None:   # 0.0 = eksen olu bolgede
                tavan_hiz, tavan_ivme = P.HIZ_TABLO[hiz_seviye]
                if son_t is not None:
                    tavan = tavan_hiz * min(0.2, simdi - son_t)
                    d_pitch = max(-tavan, min(tavan, d_pitch))
                son_t = simdi
                komut = max(0.0, min(k.tilt_tavan, kol_kare + d_pitch))
                with kilit:
                    k.aci(0.0, komut)
                sure_m = 2.0 * math.sqrt(abs(d_pitch) / max(1.0, tavan_ivme)) * NISAN_MESGUL_ORANI
                mesgul_ta = simdi + max(NISAN_MIN_ARALIK, sure_m)
        else:
            nisanci.sifirla()
        satirlar.append((round(t, 3), len(dets), ai,
                         None if hata_px is None else round(hata_px, 1),
                         None if kol is None else round(kol, 2),
                         None if komut is None else round(komut, 2), int(hareket)))
        if kayit_dizin and t - son_foto >= 1.0:
            son_foto = t
            g = algi.draw_overlay(kare.copy(), dets, ai, balonlar)
            cv2.line(g, (0, h // 2), (w, h // 2), (0, 255, 255), 1)
            cv2.putText(g, f"t={t:4.1f}s kol={kol:.1f} hata={hata_px}", (10, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
            cv2.imwrite(os.path.join(kayit_dizin, f"takip_{int(t):02d}.jpg"),
                        cv2.resize(g, (640, 360)))

    calis[0] = False
    time.sleep(0.1)
    with kilit:
        yol = k.tilt.kara_kutu_yolu
        k.kapat()
    cap.release()

    dosya = os.path.join(os.path.dirname(yol), os.path.basename(yol).replace(".log", "_takip.csv"))
    with open(dosya, "w", newline="", encoding="utf-8") as f:
        yz = csv.writer(f)
        yz.writerow(["t", "tespit", "aktif", "hata_px", "kol", "komut", "hareket"])
        yz.writerows(satirlar)

    # ---- ozet ----
    fps = len(satirlar) / max(1e-6, satirlar[-1][0])
    gorulen = [r for r in satirlar if r[3] is not None]
    print(f"\n{len(satirlar)} kare, {fps:.1f} FPS, hedef {len(gorulen)} karede kilitli")
    for s in range(0, int(sure) + 1):
        dilim = [r for r in gorulen if s <= r[0] < s + 1]
        if dilim:
            r = dilim[-1]
            print(f"  t={s:2d}s  hata {r[3]:+7.1f} px   kol {r[4]:5.1f}")
    # TITREME OLCUTU: kol kac kez DURUP yeniden KALKTI. Surekli bir takipte kol
    # akmali; her dur-kalk bir hizlan-yavasla-dur dongusudur ve namluyu sarsar.
    dur_kalk = sum(1 for a, b in zip(satirlar, satirlar[1:]) if a[6] == 1 and b[6] == 0)
    hareketli = sum(r[6] for r in satirlar) / max(1, len(satirlar))
    for esik in (20, 10):
        y = next((gorulen[i][0] for i in range(len(gorulen))
                  if all(abs(r[3]) <= esik for r in gorulen[i:])), None)
        print(f"|hata| <= {esik} px kalici yerlesme: " + (f"{y:.2f} s" if y is not None else "YOK"))
    if gorulen:
        print(f"en buyuk sapma {max(abs(r[3]) for r in gorulen):.0f} px, son hata {gorulen[-1][3]:+.1f} px")
    print(f"DUR-KALK: {dur_kalk} kez ({dur_kalk / max(1e-6, satirlar[-1][0]):.1f}/sn), "
          f"kol zamanin %{100 * hareketli:.0f}'inde hareket halinde | kayit: {dosya}")
    return 0


if __name__ == "__main__":
    sure = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0
    bas = float(sys.argv[2]) if len(sys.argv) > 2 else 14.0
    dizin = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] != '-' else None
    kp = float(sys.argv[4]) if len(sys.argv) > 4 else None
    gec = float(sys.argv[5]) if len(sys.argv) > 5 else 0.0
    kd = float(sys.argv[6]) if len(sys.argv) > 6 else None
    raise SystemExit(main(sure, bas, dizin, kp, gec, kd))
