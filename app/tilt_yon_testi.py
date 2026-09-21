# -*- coding: utf-8 -*-
"""DERIN MAVI — DIKEY YON VE KAZANC OLCUMU (kamera + gercek tilt karti).

Sahada otonom takipte hedef kamera merkezinin USTUNDEYKEN namlu ASAGI indi ve kol
bir uca kadar gitti. Bu, yon isaretinin ters oldugunu dusunduruyor: isaret tersse
sistem hedeften kacar, kactikca hata buyur, kol uca dayanir.

Benzetim bunu yakalayamazdi: orada "aci artinca kamera yukari bakar" VARSAYILIYOR.
Bu arac varsayimi OLCER:
  1. kameradan kare al
  2. kolu +ADIM derece kaldir
  3. tekrar kare al, iki kare arasindaki dikey kaymayi faz korelasyonuyla olc

Dik (ters takilmamis) bir kamera YUKARI donerse sahne goruntude ASAGI kayar (dy > 0).
  dy > 0  -> "aci artinca kamera yukari"  -> tilt_ters = 0 (varsayim dogru)
  dy < 0  -> kamera ters takili ya da mekanizma ters -> tilt_ters = 1

Ek olarak ORANI da olcer: goruntudeki derece / komut edilen derece. 1'den cok farkliysa
PD kazanci fiilen o oranda buyur/kuculur (kol-biyel mekanizmasi kol acisini ve
namlu acisini ayni olcude dondurmeyebilir).

Kullanim:  python app/tilt_yon_testi.py [adim_derece=8]
"""
import sys
import time

import cv2
import numpy as np

import algi
import nisan
import tilt_surucu as T


def ortalama_kare(cap, n=6):
    for _ in range(4):
        cap.read()
    kareler = []
    for _ in range(n):
        ok, k = cap.read()
        if ok:
            kareler.append(cv2.cvtColor(k, cv2.COLOR_BGR2GRAY).astype(np.float32))
    return np.mean(kareler, axis=0) if kareler else None


def git_bekle(s, hedef, azami=15.0):
    s.git(hedef)
    t0 = time.time()
    while time.time() - t0 < azami:
        s.yokla(); time.sleep(0.01)
        if not s.hareket and s._bekleyen_hedef is None and abs(s.aci - hedef) < 0.3:
            break
    t1 = time.time()
    while time.time() - t1 < 0.6:          # titresim sonmesi + nabiz
        s.yokla(); time.sleep(0.01)
    return s.aci


def aralik_olc(s, cap, dpp, a_bas, a_son, tekrar=2):
    """a_bas -> a_son arasinda goruntu kaymasini olcer. (oran, dy_ort, guven) doner."""
    oranlar, dyler, guven = [], [], 1.0
    for _ in range(tekrar):
        a0 = git_bekle(s, a_bas); k0 = ortalama_kare(cap)
        a1 = git_bekle(s, a_son); k1 = ortalama_kare(cap)
        (dx, dy), g = cv2.phaseCorrelate(k0, k1)
        oranlar.append(dy * dpp / (a1 - a0)); dyler.append(dy); guven = min(guven, g)
    return float(np.mean(oranlar)), float(np.mean(dyler)), guven


def tarama(araliklar=((5, 13), (25, 33), (45, 53))):
    """Orani kol boyunca birkac bolgede olcer: kol-biyel mekanizmasi DOGRUSAL
    olmayabilir, tek noktadaki olcum butun araliga genellenemez."""
    import tilt_takip_testi as tt
    kaynak = tt.kayitli_ayarlari_yukle()      # uygulamanin kullandigi FOV ile olc
    algi.ayar_guncelle(kamera_fps=60)
    cap = algi.open_camera()
    s = T.TiltSurucu("auto")
    t0 = time.time()
    while time.time() - t0 < 1.0:
        s.yokla(); time.sleep(0.01)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    dpp = nisan.derece_per_piksel(w)
    print(f"FOV {algi.AYAR['fov']} (kaynak: {kaynak}) -> {dpp:.4f} derece/px")
    sonuc = []
    for a, b in araliklar:
        oran, dy, g = aralik_olc(s, cap, dpp, a, b)
        sonuc.append(oran)
        print(f"  kol {a:>2}->{b:<2} derece: dy {dy:+6.1f} px, oran {oran:.3f} (guven {g:.2f})")
    git_bekle(s, 20.0)
    s.kapat(kalici=True); cap.release()
    print(f"ortalama oran {np.mean(sonuc):.3f}, en kucuk {min(sonuc):.3f}, en buyuk {max(sonuc):.3f}")
    return sonuc


def egri(bas=0.0, son=60.0, adim=4.0, tekrar=2, foto_dizin=None, foto_her=12.0):
    """Komut acisi -> KAMERA acisi egrisini kucuk adimlarla cikarir.

    Kucuk adim: faz korelasyonu ancak iki kare yeterince ORTUSURSE guvenilir.
    8 derecelik adim ust bolgede goruntuyu fazla kaydirdi (guven 0.04).
    Her adimin kaymasi toplanarak kamera acisi bas'tan itibaren biriktirilir.
    Doner: [(komut_acisi, kamera_acisi, adimin_guveni), ...]"""
    import tilt_takip_testi as tt
    tt.kayitli_ayarlari_yukle()
    algi.ayar_guncelle(kamera_fps=60)
    cap = algi.open_camera()
    s = T.TiltSurucu("auto")
    t0 = time.time()
    while time.time() - t0 < 1.0:
        s.yokla(); time.sleep(0.01)
    dpp = nisan.derece_per_piksel(int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)))
    noktalar = []
    a = bas
    onceki_a = git_bekle(s, a)
    onceki_k = ortalama_kare(cap)
    kamera = 0.0
    noktalar.append((onceki_a, 0.0, 1.0))

    def foto(aci):
        """Gozle dogrulama icin: sayilarin soyledigi donus goruntude de var mi?"""
        if foto_dizin is None:
            return
        import os
        os.makedirs(foto_dizin, exist_ok=True)
        for _ in range(3):
            cap.read()
        ok, k = cap.read()
        if ok:
            k = cv2.resize(k, (640, 360))
            cv2.putText(k, f"komut {aci:.0f} derece", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
            cv2.imwrite(os.path.join(foto_dizin, f"tilt_{aci:04.1f}.jpg"), k)
    foto(onceki_a)
    son_foto = onceki_a
    while a + adim <= son + 1e-9:
        a += adim
        kaymalar, guvenler = [], []
        for _ in range(tekrar):
            b = git_bekle(s, a); k = ortalama_kare(cap)
            (dx, dy), g = cv2.phaseCorrelate(onceki_k, k)
            kaymalar.append(dy); guvenler.append(g)
            if _ + 1 < tekrar:                      # tekrar icin geri don
                git_bekle(s, onceki_a); onceki_k = ortalama_kare(cap)
        dy = float(np.median(kaymalar))
        kamera += dy * dpp
        noktalar.append((b, kamera, min(guvenler)))
        print(f"  komut {onceki_a:5.1f} -> {b:5.1f}: dy {dy:+6.1f} px -> kamera {kamera:6.2f} "
              f"derece  (yerel oran {dy*dpp/(b-onceki_a):+.2f}, guven {min(guvenler):.2f})")
        onceki_a, onceki_k = b, k
        if b - son_foto >= foto_her - 1e-6:
            foto(b); son_foto = b
    git_bekle(s, 20.0)
    s.kapat(kalici=True); cap.release()
    return noktalar


def main(adim=8.0):
    algi.ayar_guncelle(kamera_fps=60)
    cap = algi.open_camera()
    if cap is None:
        print("[HATA] Kamera acilamadi (uygulama acik olabilir — kapat)."); return 2
    s = T.TiltSurucu("auto")
    if not s.bagli:
        print("[HATA] Tilt karti yok:", s.hata); return 2
    t0 = time.time()
    while time.time() - t0 < 1.0:
        s.yokla(); time.sleep(0.01)
    if not s.hazir:
        print("[HATA] Kart hazir degil:", s.ozet()); return 2

    bas = s.aci
    ust = min(T.ACI_MAX - 2.0, bas + adim)
    if ust - bas < 3.0:                     # yukarida yer yoksa asagidan olc
        bas = git_bekle(s, max(2.0, bas - adim))
        ust = min(T.ACI_MAX - 2.0, bas + adim)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    dpp = nisan.derece_per_piksel(w, algi.AYAR.get("fov", 60.0))

    sonuclar = []
    for tekrar in range(2):
        a0 = git_bekle(s, bas)
        k0 = ortalama_kare(cap)
        a1 = git_bekle(s, ust)
        k1 = ortalama_kare(cap)
        (dx, dy), guven = cv2.phaseCorrelate(k0, k1)
        komut = a1 - a0
        goruntu = dy * dpp
        sonuclar.append((komut, dx, dy, goruntu, guven))
        print(f"deneme {tekrar+1}: kol {a0:.2f} -> {a1:.2f} (+{komut:.2f} derece) | "
              f"goruntu kaymasi dx={dx:+.1f} dy={dy:+.1f} px (guven {guven:.2f}) "
              f"= {goruntu:+.2f} derece")
    git_bekle(s, bas)
    s.kapat(kalici=True)
    cap.release()

    dy_ort = float(np.mean([r[2] for r in sonuclar]))
    oran = float(np.mean([r[3] / r[0] for r in sonuclar if abs(r[0]) > 0.5]))
    guven = min(r[4] for r in sonuclar)
    print(f"\nkare genisligi {w} px, FOV {algi.AYAR.get('fov', 60.0)} derece -> {dpp:.4f} derece/px")
    if guven < 0.05:
        print("[?] Olcum guveni cok dusuk — sahne dokusuz ya da hareketli. Kameraya "
              "desenli, sabit bir sahne goster ve tekrar dene.")
        return 3
    if dy_ort > 0:
        print(f"[ OK ] Aci artinca kamera YUKARI bakiyor (sahne asagi kaydi). "
              f"Isaret DOGRU -> tilt_ters = 0")
    else:
        print(f"[!!] Aci artinca sahne YUKARI kaydi -> kamera ASAGI bakiyor. "
              f"Isaret TERS -> tilt_ters = 1")
    print(f"     goruntu/komut orani: {abs(oran):.2f}  "
          f"(1'den uzaksa PD kazanci fiilen bu oranla carpilir)")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "tarama":
        tarama()
        raise SystemExit(0)
    if len(sys.argv) > 1 and sys.argv[1] == "egri":
        # Olcer ve app/tilt_egri.json'a KAYDEDER; otonom takip bu dosyayi kullanir.
        # Mekanizma, kamera montaji ya da kalibrasyon degisirse YENIDEN calistirilmali.
        import tilt_egri
        noktalar = egri()
        e = tilt_egri.KameraEgrisi(noktalar)
        e.kaydet(not_=f"tilt_yon_testi.py egri, {time.strftime('%Y-%m-%d %H:%M')}, "
                      f"FOV {algi.AYAR.get('fov')}")
        lo, hi = e.gecerli_aralik
        print(f"\nKAYDEDILDI: {tilt_egri.VARSAYILAN_DOSYA}")
        print(f"gecerli aralik {lo:.0f}-{hi:.0f} derece komut "
              f"(kamera {e.kamera(lo):+.1f} .. {e.kamera(hi):+.1f} derece)")
        raise SystemExit(0)
    raise SystemExit(main(float(sys.argv[1]) if len(sys.argv) > 1 else 8.0))
