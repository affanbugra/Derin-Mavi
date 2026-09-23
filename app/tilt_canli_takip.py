# -*- coding: utf-8 -*-
"""DERIN MAVI — CANLI DIKEY TAKIP TESTI (gercek kamera + gercek model + gercek kart).

Arayuzu (PySide6) acmadan otonom dikey takibi gercek donanimda dener ve OLCER.

Iki kontrolcu karsilastirilir:
  pd     : arayuzdeki mevcut zincir — nisan.PDNisanci + _nisan_geldi aynasi
           (hiz kirpma + mesgul kapisi), taban = olculen aci.
  kalman : hedef_kestirici.KalmanTakipKontrolu — hedefin DUNYA acisi + hizi
           kestirilir; hiz-sinirli ve yon-histerezisli komutla hedefin GIDECEGI
           yere yonelir, kisa tespit kesintisinde tahminle kovalamaya devam eder.

TEKRARLANABILIR HAREKETLI HEDEF (--sanal A,T). Masadaki (sabit) drone'un kadraj
konumuna A*sin(2*pi*t/T) piksel eklenir. Kamera donunce drone da kadrajda kayar,
ekleme ise piksel olarak sabit kalir; yani sanal hedef DUNYADA gercekten hareket
eden bir hedefle esdegerdir. Boylece iki kontrolcu el hareketine bagli kalmadan,
BIREBIR ayni hareketle karsilastirilir.

YAPAY KESINTI (--kesinti S). Her 2 sn'de bir S saniye tespit "kor" sayilir —
hedefin kadrajdan cikmasi / bulanik karede kaybolmasi gibi.

⚠ AYNA UYARISI: pd modu arayuz_qt._nisan_geldi'nin dikey kismini yeniden yazar.

Kullanim ornekleri:
    python app/tilt_canli_takip.py --olc_ppd                       # piksel/derece olc
    python app/tilt_canli_takip.py --mod pd     --sanal 120,4 --sure 20
    python app/tilt_canli_takip.py --mod kalman --sanal 120,4 --kesinti 0.4
"""
import argparse
import csv
import math
import os
import statistics as st
import threading
import time

import algi
import hedef_kestirici as HK
import nisan
import protokol as P
import tilt_surucu as TS
import tilt_takip_testi as tt
from kontrol import Kontrol

NISAN_MESGUL_ORANI = 0.4        # arayuz_qt.py aynasi
NISAN_MIN_ARALIK = 0.04


def kur(args):
    kaynak = tt.kayitli_ayarlari_yukle()
    if args.kp is not None:
        algi.ayar_guncelle(kp=args.kp)
    from ultralytics import YOLO
    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    model = YOLO(os.path.join(kok, "models", "best.pt"), task="detect")
    cap = algi.open_camera()
    if cap is None:
        raise SystemExit("[HATA] kamera acilamadi")
    algi.analiz_et(model, cap.read()[1])            # isinma
    k = Kontrol("off", tilt_kaynak="auto")
    if not k.tilt_ayri:
        raise SystemExit(f"[HATA] tilt karti yok: {k.tilt.hata}")
    kilit = threading.Lock()
    calis = [True]

    def nabiz():
        while calis[0]:
            with kilit:
                k.oku()
            time.sleep(0.01)
    threading.Thread(target=nabiz, daemon=True).start()
    time.sleep(1.0)
    with kilit:
        k.hiz_ayarla(P.H_NORMAL)
    return kaynak, model, cap, k, kilit, calis


def guvenli_kapat(cap, k, kilit, calis):
    """Hata/Ctrl-C dahil her cikista nabzi kes, karti kilitle ve kamerayi birak."""
    calis[0] = False
    time.sleep(0.05)
    try:
        with kilit:
            k.kapat()
    finally:
        cap.release()


def git_bekle(k, kilit, aci, cap, sure=2.5):
    with kilit:
        k.aci(0.0, aci)
    t0 = time.time()
    while time.time() - t0 < sure:
        cap.read()                                  # tamponu taze tut
    for _ in range(10):
        cap.read()


def drone_y(model, cap, n=12):
    ys = []
    for _ in range(n):
        ok, kare = cap.read()
        dets, _b, ai = algi.analiz_et(model, kare)
        if 0 <= ai < len(dets):
            x1, y1, x2, y2 = dets[ai]["box"]
            ys.append((y1 + y2) * 0.5)
    return st.median(ys) if len(ys) >= n // 2 else None


def olc_ppd(args):
    """Kol-komut derecesi basina hedefin goruntude kac piksel kaydigi (Kalman icin)."""
    _k, model, cap, k, kilit, calis = kur(args)
    sonuc = []
    try:
        for a0, a1 in ((args.bas - 4, args.bas), (args.bas, args.bas + 4),
                       (args.bas - 4, args.bas + 4)):
            a0 = max(TS.ACI_MIN, a0)
            git_bekle(k, kilit, a0, cap); algi.takip_sifirla(); y0 = drone_y(model, cap)
            git_bekle(k, kilit, a1, cap); algi.takip_sifirla(); y1 = drone_y(model, cap)
            if y0 is None or y1 is None:
                print(f"  {a0:.0f}->{a1:.0f}: hedef gorulmedi"); continue
            ppd = (y1 - y0) / (a1 - a0)
            sonuc.append(ppd)
            print(f"  kol {a0:4.1f} -> {a1:4.1f}: hedef {y0:6.1f} -> {y1:6.1f} px  =>  {ppd:5.2f} px/derece")
    finally:
        guvenli_kapat(cap, k, kilit, calis)
    if sonuc:
        print(f"piksel/derece (medyan): {st.median(sonuc):.2f}")


def calistir(args):
    kaynak, model, cap, k, kilit, calis = kur(args)
    git_bekle(k, kilit, args.bas, cap)
    tilt_alt = max(TS.ACI_MIN, args.bas - args.tilt_sinir)
    tilt_ust = min(k.tilt_tavan, args.bas + args.tilt_sinir)   # yalniz --tilt_sinir (gizli tavan yok)
    if tilt_alt >= tilt_ust:
        guvenli_kapat(cap, k, kilit, calis)
        raise ValueError(f"Gecersiz tilt test penceresi: {tilt_alt:.1f}..{tilt_ust:.1f}")
    print(f"Tilt test penceresi: {tilt_alt:.1f}..{tilt_ust:.1f}°", flush=True)
    algi.takip_sifirla()
    nisanci = nisan.PDNisanci()
    _pan_profili, tilt_profili = k.hiz_profilleri(P.H_NORMAL)
    takipci = HK.KalmanTakipKontrolu(
        q=args.q, r=args.r, ileri=args.ileri, kazanc=args.g,
        kayip_kovalamasi=args.kostur, komut_hz=args.komut_hz,
        azami_hiz=tilt_profili[0], min_komut=args.min_komut,
        yon_histerezis=args.yon_histerezis, durus_hizi=args.v_esik)
    son_t, mesgul_ta = None, 0.0
    onceki_aci = None
    # arayuz_qt._takip_olcum_geldi aynasi (ayni sinif, ayni ayarlar)
    pan_tk = HK.EksenTakip(isaret=+1.0, bosluk=algi.AYAR["takip_bosluk"])
    tilt_tk = HK.EksenTakip(isaret=-1.0, bosluk=algi.AYAR["takip_bosluk"])
    pan_acik = args.pan and k.pan_ayri
    print(f"PAN takibi: {'ACIK (sinir +-%.0f derece)' % args.pan_sinir if pan_acik else 'KAPALI'}")
    A, T = (args.sanal if args.sanal else (0.0, 1.0))
    AX, TX = (args.sanal_x if args.sanal_x else (0.0, 1.0))
    satirlar = []
    print(f"MOD={args.mod} | sanal Y={A:.0f}px/{T:.1f}s X={AX:.0f}px/{TX:.1f}s | "
          f"kesinti={args.kesinti}s/2s | "
          f"kp={algi.AYAR['kp']} ppd={args.ppd} gecikme={args.gecikme} ileri={args.ileri} "
          f"g={args.g} q={args.q} r={args.r}")
    t0 = time.time()
    # --kilit_bekle: sure hedef ILK KEZ gercekten gorulunce baslar (operator hazir
    # olmadan gecen saniyeler olcume girmesin). Beklerken motor komutu YOK.
    basladi = args.kilit_bekle <= 0
    if not basladi:
        print(f"Hedef bekleniyor (en fazla {args.kilit_bekle:.0f} sn)...", flush=True)
    try:
      while (time.time() - t0 < args.sure) if basladi else (time.time() - t0 < args.kilit_bekle):
        ok, kare = cap.read()
        t_okuma = time.time()
        if not ok:
            continue
        h, w = kare.shape[:2]
        # kamera hareketi telafisi (arayuz_qt.InferenceThread._kamera_kaymasi aynasi)
        if args.gmc:
            with kilit:
                t_k = t_okuma - float(algi.AYAR["kamera_gecikme"])
                p_a, t_a = k.pan_zamaninda(t_k), k.tilt_zamaninda(t_k)
            if p_a is not None and t_a is not None:
                aci_simdi = (p_a, TS.kamera_acisi(t_a))
                if onceki_aci is not None:
                    ppd_g = float(algi.AYAR["takip_ppd_pan"]) * kare.shape[1] / 1280.0
                    algi.kamera_kaymasi_bildir(-(aci_simdi[0] - onceki_aci[0]) * ppd_g,
                                               (aci_simdi[1] - onceki_aci[1]) * ppd_g)
                onceki_aci = aci_simdi
        dets, balonlar, ai = algi.analiz_et(model, kare, asama=2)
        simdi = time.time()
        t = simdi - t0
        with kilit:
            kol = k.tilt_olculen
            hareket = k.tilt.hareket
            t_kare = t_okuma - (float(algi.AYAR["kamera_gecikme"])
                                if args.mod in ("surekli", "yorunge") else args.gecikme)
            kol_kare = k.tilt.aci_zamaninda(t_kare)
            pan_olc = k.pan_olculen
        kesik = args.kesinti > 0 and (t % 2.0) > (2.0 - args.kesinti) and t > 1.0
        aktif_det = dets[ai] if 0 <= ai < len(dets) else None
        hedef_var = (aktif_det is not None and not aktif_det.get("hayalet")
                     and algi.anlik_kirmizi_kaniti(kare, aktif_det["box"]) and not kesik)
        if not basladi:
            if not hedef_var:
                continue
            basladi = True
            t0 = time.time()
            t = 0.0
            print("Hedef kilitlendi, sure basladi.", flush=True)
        hata_px = hata_x = komut = None
        if hedef_var:
            kutu = dets[ai]["box"]
            hx, hy = algi.nisan_noktasi(kutu, balonlar)
            hx += AX * math.sin(2 * math.pi * t / TX)        # pan icin tekrarlanabilir hedef
            hy += A * math.sin(2 * math.pi * t / T)          # sanal hareket (A=0: gercek)
            hata_px = hy - h * 0.5
            hata_x = hx - w * 0.5
            kutu_h = abs(kutu[3] - kutu[1])
        # ---------------- PD ----------------
        if args.mod == "pd":
            if hedef_var:
                d_yaw, d_pitch = nisanci.adim((hx, hy), (w, h), simdi=simdi, hedef_yukseklik=kutu_h)
                if not pan_acik:
                    d_yaw = 0.0
                if (d_pitch or d_yaw) and simdi >= mesgul_ta and kol is not None:
                    (pan_hiz, pan_ivme), (tavan_hiz, tavan_ivme) = k.hiz_profilleri(P.H_NORMAL)
                    dt = min(0.2, simdi - son_t) if son_t is not None else None
                    sure_m = 0.0
                    # arayuz_qt._aci_hareket aynasi: yalniz DEGISEN eksenin tabani olculen aci
                    komut = k.tilt_hedef
                    if d_pitch:
                        sure_m = 2.0 * math.sqrt(abs(d_pitch) / max(1.0, tavan_ivme))
                        if dt is not None:
                            d_pitch = max(-tavan_hiz * dt, min(tavan_hiz * dt, d_pitch))
                        komut = max(tilt_alt, min(tilt_ust, kol + d_pitch))
                    pan_komut = k.pan_hedef
                    if d_yaw and pan_olc is not None:
                        sure_m = max(sure_m, 2.0 * math.sqrt(abs(d_yaw) / max(1.0, pan_ivme)))
                        if dt is not None:
                            d_yaw = max(-pan_hiz * dt, min(pan_hiz * dt, d_yaw))
                        pan_komut = max(-args.pan_sinir, min(args.pan_sinir, pan_olc + d_yaw))
                    son_t = simdi
                    with kilit:
                        k.aci(pan_komut, komut)
                    mesgul_ta = simdi + max(NISAN_MIN_ARALIK, sure_m * NISAN_MESGUL_ORANI)
            else:
                nisanci.sifirla()
        # ---------------- YORUNGE (arayuzun Y/PY destekli karttaki yolu) ----------------
        elif args.mod == "yorunge":
            ex = ey = olu_x = olu_y = None
            if hedef_var:
                nisanci.adim((hx, hy), (w, h), simdi=simdi, hedef_yukseklik=kutu_h)
                (ex, ey), (olu_x, olu_y) = nisanci.son_hata_px, nisanci.son_olu_px
                ppd_k = float(algi.AYAR["takip_ppd_pan"]) * w / 1280.0
                with kilit:
                    p_kare = k.pan_zamaninda(t_kare) if pan_acik else None
                pan_tk.olcum(t_kare, p_kare, ex, ppd_k)
                tilt_tk.olcum(t_kare, TS.kamera_acisi(kol_kare), ey, ppd_k)
            ust = tilt_ust
            pr = pan_tk.yorunge_komut(simdi, pan_olc, -args.pan_sinir, args.pan_sinir,
                                      hata_px=ex, olu_px=olu_x, pay=0.0) if pan_acik else None
            tr = tilt_tk.yorunge_komut(simdi, TS.kamera_acisi(kol), TS.kamera_acisi(tilt_alt),
                                       TS.kamera_acisi(ust), hata_px=ey, olu_px=olu_y,
                                       pay=0.0)   # arayuzle ayni: gizli pay yok
            tilt_kol = tilt_v = None
            if tr is not None:
                tilt_kol = max(tilt_alt, min(ust, TS.kol_acisi(tr[0])))
                egim = (TS.kamera_acisi(tilt_kol + 0.05) - TS.kamera_acisi(tilt_kol - 0.05)) / 0.1
                tilt_v = tr[1] / max(1e-3, egim)
                komut = tilt_kol
            if pr is not None or tr is not None:
                with kilit:
                    k.yorunge(pr[0] if pr else None, pr[1] if pr else None, tilt_kol, tilt_v)
        # ---------------- SUREKLI (arayuz yolu) ----------------
        elif args.mod == "surekli":
            ex = ey = olu_x = olu_y = None
            if hedef_var:
                nisanci.adim((hx, hy), (w, h), simdi=simdi, hedef_yukseklik=kutu_h)
                (ex, ey), (olu_x, olu_y) = nisanci.son_hata_px, nisanci.son_olu_px
                olcek = w / 1280.0
                with kilit:
                    p_kare = k.pan_zamaninda(t_kare) if pan_acik else None
                pan_tk.olcum(t_kare, p_kare, ex, float(algi.AYAR["takip_ppd_pan"]) * olcek)
                tilt_tk.olcum(t_kare, TS.kamera_acisi(kol_kare), ey,
                              float(algi.AYAR["takip_ppd_pan"]) * olcek)
            pan_k = pan_tk.komut(simdi, pan_olc, -args.pan_sinir, args.pan_sinir,
                                 hata_px=ex, olu_px=olu_x) if pan_acik else None
            ust = tilt_ust
            komut = TS.kol_acisi(tilt_tk.komut(simdi, TS.kamera_acisi(kol), TS.kamera_acisi(tilt_alt),
                                              TS.kamera_acisi(ust), hata_px=ey, olu_px=olu_y))
            if komut is not None:
                komut = max(tilt_alt, min(ust, komut))
            if pan_k is not None or komut is not None:
                with kilit:
                    k.aci(k.pan_hedef if pan_k is None else pan_k,
                          k.tilt_hedef if komut is None else komut)
        # ---------------- KALMAN ----------------
        else:
            if hedef_var and kol_kare is not None:
                takipci.olcum(t_okuma - args.gecikme, kol_kare, hata_px, args.ppd)
            if kol is not None:
                olu = max(nisan.TABAN_OLU_BOLGE_PX,
                          algi.AYAR["olu_bolge_kutu"] * kutu_h) if hedef_var else None
                komut = takipci.komut(simdi, kol, hedef_var, hata_px, olu,
                                      alt=tilt_alt, ust=tilt_ust)
                if komut is not None:
                    with kilit:
                        k.aci(0.0, komut)
        satirlar.append((t, int(hedef_var), hata_px, kol, komut, int(hareket), int(kesik),
                         len(dets), None if aktif_det is None else aktif_det.get("id"),
                         None if aktif_det is None else aktif_det.get("cls"),
                         None if aktif_det is None else aktif_det.get("conf"),
                         int(bool(aktif_det and aktif_det.get("hayalet"))), hata_x, pan_olc))
    finally:
        yol = k.tilt.kara_kutu_yolu
        guvenli_kapat(cap, k, kilit, calis)
    dosya = yol.replace(".log", f"_{args.mod}.csv")
    with open(dosya, "w", newline="", encoding="utf-8") as f:
        yz = csv.writer(f)
        yz.writerow(["t", "hedef", "hata_px", "kol", "komut", "hareket", "kesik",
                     "tespit_sayisi", "aktif_id", "aktif_sinif", "aktif_guven", "hayalet",
                     "hata_x", "pan"])
        yz.writerows(satirlar)
    ozet(satirlar, dosya)


def ozet(satirlar, dosya):
    if not satirlar:
        print(f"\nKamera karesi okunamadi; bos kayit: {dosya}")
        return
    fps = len(satirlar) / max(1e-6, satirlar[-1][0])
    son = [r for r in satirlar if r[0] > 2.0]                 # ilk yakalamadan sonrasi
    goren = [r for r in son if r[2] is not None]
    e = [abs(r[2]) for r in goren]
    dur_kalk = sum(1 for a, b in zip(son, son[1:]) if a[5] == 1 and b[5] == 0)
    kol = [r[3] for r in son if r[3] is not None]
    yon, onceki = 0, 0
    for a, b in zip(kol, kol[1:]):
        d = 1 if b - a > 0.02 else (-1 if b - a < -0.02 else 0)
        if d and onceki and d != onceki:
            yon += 1
        if d:
            onceki = d
    # kesinti sonrasi: kor aralik biter bitmez gorulen ilk hata (kacirdi mi?)
    donus = [abs(b[2]) for a, b in zip(son, son[1:]) if a[6] == 1 and b[6] == 0 and b[2] is not None]
    hayalet = sum(r[11] for r in son if len(r) > 11)
    idler = [r[8] for r in son if len(r) > 8 and r[8] is not None and not r[11]]
    id_degisim = sum(a != b for a, b in zip(idler, idler[1:]))
    print(f"\n{len(satirlar)} kare, {fps:.0f} FPS | 2. saniyeden sonra:")
    if e:
        e_s = sorted(e)
        print(f"  |hata| ORT {st.mean(e):5.1f} px | medyan {st.median(e):5.1f} | "
              f"%95 {e_s[int(0.95 * (len(e_s) - 1))]:5.1f} | en buyuk {max(e):5.1f}")
    if kol:
        print(f"  tilt araligi {min(kol):+.2f} .. {max(kol):+.2f} derece")
    # HIZ DALGALANMASI (titresimin dogrudan gostergesi): 0.1 sn'lik pencerelerde eksen
    # hizi, ardisik pencereler arasi ortalama |hiz degisimi| / 0.1 sn = der/sn^2.
    # Kartin "hareket" bayragi yorunge kipinde surekli acik oldugu icin dur-kalk
    # sayaci orada anlamsizdir; bu olcu iki kipte de ayni sekilde hesaplanir.
    def _dalga(sutun):
        orn, sinir = [], 2.0
        for r_ in son:
            if len(r_) > sutun and r_[sutun] is not None and r_[0] >= sinir:
                orn.append((r_[0], r_[sutun]))
                sinir = r_[0] + 0.1
        hz = [(b[1] - a[1]) / max(1e-6, b[0] - a[0]) for a, b in zip(orn, orn[1:])]
        return st.mean(abs(b - a) / 0.1 for a, b in zip(hz, hz[1:])) if len(hz) > 2 else 0.0
    print(f"  HIZ DALGALANMASI (ort |ivme|): tilt {_dalga(3):6.0f} der/sn^2 | pan {_dalga(13):6.0f} der/sn^2")
    print(f"  hedef gorulen kare %{100 * len(goren) / max(1, len(son)):.0f} | "
          f"hayalet {hayalet} | ID degisimi {id_degisim} | "
          f"dur-kalk {dur_kalk} | kol yon degisimi {yon}")
    ex = [abs(r[12]) for r in goren if len(r) > 12 and r[12] is not None]
    pan = [r[13] for r in son if len(r) > 13 and r[13] is not None]
    if ex and pan:
        ex_s = sorted(ex)
        print(f"  YATAY |hata| medyan {st.median(ex):5.1f} px | %95 {ex_s[int(0.95 * (len(ex_s) - 1))]:5.1f} | "
              f"pan araligi {min(pan):+.1f} .. {max(pan):+.1f} derece")
    if donus:
        print(f"  kesinti SONRASI ilk hata: ort {st.mean(donus):.0f} px, en buyuk {max(donus):.0f} px "
              f"({len(donus)} kesinti)")
    print(f"  kayit: {dosya}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mod", choices=("pd", "kalman", "surekli", "yorunge"), default="yorunge",
                    help="surekli = arayuzun konum bildiren karttaki yolu (EksenTakip)")
    ap.add_argument("--sure", type=float, default=20.0)
    ap.add_argument("--bas", type=float, default=0.0,
                    help="baslangic operator acisi (-30..+30; 0 = fiziksel kol 30)")
    ap.add_argument("--tilt_sinir", type=float, default=45.0,
                    help="baslangic acisi etrafindaki test penceresi (+/- derece)")
    ap.add_argument("--sanal", type=lambda s: tuple(map(float, s.split(","))), default=None,
                    help="A,T: sanal hedef genligi (px) ve periyodu (sn)")
    ap.add_argument("--sanal-x", type=lambda s: tuple(map(float, s.split(","))), default=None,
                    help="A,T: yatay sanal hedef genligi (px) ve periyodu (sn)")
    ap.add_argument("--kesinti", type=float, default=0.0, help="her 2 sn'de kor sure (sn)")
    ap.add_argument("--kp", type=float, default=None)
    # 21.09 olculdu (--olc_ppd, drone ~40 cm): 2-6 derece 9.6, 6-10 derece 17.4, medyan 13.4.
    # 8.0 kucuk kaliyordu: z = kol - hata/ppd duzeltmeyi ~1.6 kat buyutur -> asma/salinim.
    # Belirsizlikte BUYUK taraf guvenlidir (az duzeltir, yavas ama kararli yaklasir).
    ap.add_argument("--ppd", type=float, default=13.0, help="piksel / kol derecesi")
    ap.add_argument("--gecikme", type=float, default=0.06, help="kamera gecikmesi (sn)")
    ap.add_argument("--ileri", type=float, default=0.08, help="kalman ongoru suresi (sn)")
    ap.add_argument("--g", type=float, default=0.9, help="kalman duzeltme kazanci")
    ap.add_argument("--q", type=float, default=120.0)
    ap.add_argument("--r", type=float, default=0.4)
    ap.add_argument("--kostur", type=float, default=0.45, help="kayipta tahminle kovalama (sn)")
    ap.add_argument("--komut_hz", type=float, default=25.0, help="azami motor komutu / sn")
    ap.add_argument("--min_komut", type=float, default=0.08, help="derece: daha kucuk komutu yut")
    ap.add_argument("--yon_histerezis", type=float, default=0.30,
                    help="derece: kucuk ters-yon komutunu yut")
    ap.add_argument("--v_esik", type=float, default=1.5, help="derece/sn: olu bolgede durma esigi")
    ap.add_argument("--olc_ppd", action="store_true")
    ap.add_argument("--pan", type=int, default=1, help="1: pan (sag-sol) de takip etsin (yalniz pd)")
    ap.add_argument("--gmc", type=int, default=1, help="1: kamera hareketi telafisi")
    ap.add_argument("--kilit_bekle", type=float, default=0.0,
                    help="sn: sure hedef ilk gorulunce baslasin (0 = hemen)")
    ap.add_argument("--pan_sinir", type=float, default=45.0, help="pan guvenlik siniri (derece, baslangica gore)")
    a = ap.parse_args()
    olc_ppd(a) if a.olc_ppd else calistir(a)
