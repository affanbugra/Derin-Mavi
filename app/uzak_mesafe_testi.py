# -*- coding: utf-8 -*-
"""DERIN MAVI — UZAK MESAFE TESPIT TESTI (motor YOK, yalniz kamera + model).

Hedefi bilinen bir mesafeye koy, kamerayi ona dogrult, bu betigi calistir.
Olculen: hedef karelerin yuzde kacinda goruldugu, guven, goruntudeki BOY (px) ve
kilidin ne kadar surdugu. Modelin GOREMEDIGI kareler egitim icin kaydedilir.

    python app/uzak_mesafe_testi.py --mesafe 15 --sure 30

⚠ Hareket komutu GONDERMEZ: kart bagli olmasa da calisir. Amaci takip degil,
"bu mesafede hedefi goruyor muyuz" sorusunu net cevaplamak.

Kaydedilenler (app/veri_toplama/<oturum>/):
  kacirma_*  : model hicbir sey bulamadi, ama hedef renginde leke var (ETIKETSIZ)
  dusuk_*    : bulundu ama guven onay esiginin altinda (etiketli)
  roi_*      : ana tarama kacirdi, kilit penceresi/uzak tarama buldu (etiketli)
Etiketler modelden gelir, yani SAHTEDIR — egitime girmeden once gozden gecir.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import algi


# Sartname maket boylari (CLAUDE.md §3). Drone EN KUCUK hedeftir: digerleri ayni
# mesafede goruntude daha BUYUK gorunur, yani uzak tespit onlarda daha kolaydir.
TIP_BOY_CM = {"drone": 30.0, "fuze": 40.0, "f16": 50.0, "helikopter": 50.0}


# px = boy / (2*d*tan(FOV/2)) * genislik_px
def beklenen_px(mesafe_m, boy_cm=30.0, genislik_px=1280, fov_der=48.0):
    import math
    return boy_cm / 100.0 / (2 * mesafe_m * math.tan(math.radians(fov_der) / 2)) * genislik_px


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mesafe", type=float, default=0.0, help="hedefin mesafesi (m) — yalniz rapor icin")
    ap.add_argument("--sure", type=float, default=30.0)
    ap.add_argument("--asama", type=int, default=2, choices=(1, 2, 3))
    ap.add_argument("--tip", default="drone", choices=sorted(TIP_BOY_CM),
                   help="hangi maket test ediliyor (beklenen boy ve suzgec icin)")
    ap.add_argument("--boy", type=float, default=None, help="gercek boy (cm) — tipin varsayilanini ezer")
    ap.add_argument("--suz", type=int, default=0,
                   help="1: otonom kilit YALNIZ --tip hedefine kurulsun")
    ap.add_argument("--kirmizi", type=int, default=None, help="1/0: kirmizi oneriyle uzak tarama")
    args = ap.parse_args()

    if args.kirmizi is not None:
        algi.ayar_guncelle(uzak_kirmizi=int(args.kirmizi))
    algi.ayar_guncelle(zor_ornek=1)
    boy_cm = args.boy if args.boy else TIP_BOY_CM[args.tip]
    if args.suz:
        algi.hedef_tipleri_ayarla([args.tip])

    from ultralytics import YOLO
    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    model = YOLO(os.path.join(kok, "models", "best.pt"), task="detect")
    cap = algi.open_camera()
    if cap is None:
        raise SystemExit("[HATA] kamera acilamadi")
    okuyucu = algi.KameraOkuyucu(cap)
    time.sleep(0.5)
    kare = okuyucu.oku()[0]
    if kare is None:
        raise SystemExit("[HATA] kameradan kare gelmedi")
    algi.analiz_et(model, kare, asama=args.asama)          # isinma

    if args.mesafe:
        print(f"{args.mesafe:.0f} m'de {args.tip} ({boy_cm:.0f} cm) goruntude yaklasik "
              f"{beklenen_px(args.mesafe, boy_cm):.0f} px olmali.")
    print(f"Basliyor: {args.sure:.0f} sn. Hedefi kadrajda TUT, kameraya dokunma.\n")

    t0 = time.time()
    kare_sayisi = gorulen = kilitli = 0
    confler, boylar, roi_kare, siniflar = [], [], 0, {}
    son_sira = -1
    while time.time() - t0 < args.sure:
        kare, sira = okuyucu.oku(son_sira)
        if kare is None:
            time.sleep(0.002)
            continue
        son_sira = sira
        kare_sayisi += 1
        dets, _, aktif = algi.analiz_et(model, kare, asama=args.asama)
        # Rapor yalniz test edilen SINIFI sayar. Kadrajdaki baska bir maket/yanlis
        # pozitif "hedef goruldu" oranini yapay olarak yukseltemez.
        gercek = [d for d in dets if not d.get("hayalet") and d.get("cls") == args.tip]
        if gercek:
            gorulen += 1
            en_iyi = max(gercek, key=lambda d: d.get("conf", 0))
            confler.append(en_iyi.get("conf", 0))
            x1, y1, x2, y2 = en_iyi["box"]
            boylar.append(max(x2 - x1, y2 - y1))
            roi_kare += bool(en_iyi.get("roi"))
            siniflar[en_iyi.get("cls", "?")] = siniflar.get(en_iyi.get("cls", "?"), 0) + 1
        if aktif >= 0:
            kilitli += 1
        if kare_sayisi % 40 == 0:
            print(f"  {time.time()-t0:4.0f} sn | gorulen %{100*gorulen/kare_sayisi:3.0f} "
                  f"| kilitli %{100*kilitli/kare_sayisi:3.0f}", flush=True)

    okuyucu.kapat()
    try:
        cap.release()
    except Exception:
        pass

    n = max(1, kare_sayisi)
    print(f"\n===== SONUC ({args.mesafe:.0f} m) =====")
    print(f"  kare {kare_sayisi} ({kare_sayisi/max(0.1, time.time()-t0):.0f} FPS)")
    print(f"  HEDEF GORULEN KARE   %{100*gorulen/n:.0f}")
    print(f"  KILITLI KARE         %{100*kilitli/n:.0f}")
    if confler:
        confler.sort(); boylar.sort()
        print(f"  guven  medyan %{confler[len(confler)//2]:.0f} | en dusuk %{confler[0]:.0f}")
        print(f"  kutu boyu medyan {boylar[len(boylar)//2]:.0f} px | en kucuk {boylar[0]:.0f} px")
        print(f"  yalniz kilit penceresi/uzak tarama ile bulunan kare: {roi_kare}")
        dag = ", ".join(f"{k} %{100*v/sum(siniflar.values()):.0f}"
                        for k, v in sorted(siniflar.items(), key=lambda t: -t[1]))
        print(f"  siniflandirma: {dag}")
    else:
        print("  HIC TESPIT YOK")
    if _zor_oturum():
        print(f"  kaydedilen zor kare: {algi._zor['sayi']} -> veri_toplama/{algi._zor['oturum']}/")


def _zor_oturum():
    return algi._zor.get("oturum")


if __name__ == "__main__":
    main()
