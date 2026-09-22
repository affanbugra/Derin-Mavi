# -*- coding: utf-8 -*-
"""Kamera + hedef tespiti için güvenli, hareketsiz kısa saha ölçümü.

ESP/seri portu açmaz, motor veya lazer komutu göndermez, kare kaydetmez.
Kullanım: python app/canli_pasif_gozlem.py --sure 12
"""
import argparse
from collections import Counter
from pathlib import Path
import statistics
import time

import algi


def yuzde(pay, toplam):
    return 100.0 * pay / toplam if toplam else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sure", type=float, default=12.0, help="ölçüm süresi, saniye")
    ap.add_argument("--uzak-tarama", type=int, choices=(0, 1), default=None,
                    help="yalnız bu süreçte uzak taramayı kapat/aç; ayar dosyasını değiştirmez")
    ap.add_argument("--arama-cozunurluk", type=int, default=None,
                    help="yalnız bu süreçte kilit öncesi model giriş boyutu")
    ap.add_argument("--kare", type=Path, default=None,
                    help="isteğe bağlı tek ham kamera karesi; hedef tespiti görüntü QA için")
    args = ap.parse_args()

    # Ayrı süreçte, yalnız RAM'de: zor örnek toplama bu gözlemde dosya yazmasın.
    algi.ayar_guncelle(zor_ornek=0)
    if args.uzak_tarama is not None:
        algi.ayar_guncelle(uzak_tarama=args.uzak_tarama)
    if args.arama_cozunurluk is not None:
        algi.ayar_guncelle(arama_cozunurluk=args.arama_cozunurluk)
    from ultralytics import YOLO

    model = YOLO(str(Path(__file__).resolve().parents[1] / "models" / "best.pt"), task="detect")
    cap = algi.open_camera()
    if cap is None:
        raise SystemExit("Kamera açılamadı; başka bir uygulama kullanıyor olabilir.")
    bilgi = algi.kamera_bilgi(cap)
    # İlk model/tracker kurulumu saniyeler sürebilir; bunu sürekli-kare ölçümüne katma.
    ok, isinma_kare = cap.read()
    if ok and isinma_kare is not None:
        algi.analiz_et(model, isinma_kare)
    okuyucu = algi.KameraOkuyucu(cap)
    algi.takip_sifirla()
    sayac = Counter()
    siniflar = Counter()
    tum_siniflar = Counter()
    gecikmeler = []
    guvenler = []
    tum_guvenler = []
    ornek_kutular = []
    son_sira = None
    ilk_sira = None
    t0 = time.perf_counter()
    try:
        while time.perf_counter() - t0 < max(1.0, args.sure):
            kare, sira = okuyucu.oku(son_sira)
            if kare is None:
                time.sleep(0.002)
                continue
            if ilk_sira is None:
                ilk_sira = sira
                if args.kare is not None:
                    import cv2
                    args.kare.parent.mkdir(parents=True, exist_ok=True)
                    cv2.imwrite(str(args.kare), kare)
            son_sira = sira
            bas = time.perf_counter()
            dets, _balonlar, aktif = algi.analiz_et(model, kare)
            gecikmeler.append((time.perf_counter() - bas) * 1000.0)
            sayac["islenen"] += 1
            gercek = [d for d in dets if not d.get("hayalet")]
            tum_siniflar.update(d["cls"] for d in gercek)
            tum_guvenler.extend(d["conf"] for d in gercek)
            if gercek and len(ornek_kutular) < 5:
                ornek_kutular.append([(d["cls"], d["conf"], d["box"], d.get("id"))
                                      for d in gercek[:3]])
            sayac["idsiz"] += sum(d.get("id") is None for d in gercek)
            if gercek:
                sayac["tespitli"] += 1
            if 0 <= aktif < len(dets):
                d = dets[aktif]
                if d.get("hayalet"):
                    sayac["hayalet"] += 1
                else:
                    sayac["kilitli"] += 1
                    siniflar[d["cls"]] += 1
                    guvenler.append(d["conf"])
    finally:
        okuyucu.kapat()
    sure = time.perf_counter() - t0
    uretilen = 0 if ilk_sira is None else son_sira - ilk_sira + 1
    atlanan = max(0, uretilen - sayac["islenen"])
    print(f"Kamera: {bilgi} | model: {algi.model_sinif_ozeti(model)}")
    print(f"Süre {sure:.1f} s | kamera kare ~{uretilen/sure:.1f}/s "
          f"| işlenen {sayac['islenen']/sure:.1f}/s | atlanan {atlanan}")
    print(f"Tespitli %{yuzde(sayac['tespitli'], sayac['islenen']):.1f} | "
          f"gerçek kilit %{yuzde(sayac['kilitli'], sayac['islenen']):.1f} | "
          f"hayalet {sayac['hayalet']} kare | sınıflar {dict(siniflar)}")
    print(f"Tüm gerçek kutular: {dict(tum_siniflar)} | ID'siz {sayac['idsiz']}")
    if tum_guvenler:
        print(f"Tüm kutu güveni medyan %{statistics.median(tum_guvenler):.0f}, "
              f"maks %{max(tum_guvenler)} | ilk örnekler {ornek_kutular}")
    if gecikmeler:
        sirali = sorted(gecikmeler)
        print(f"Analiz medyan {statistics.median(gecikmeler):.1f} ms, "
              f"P95 {sirali[int(0.95 * (len(sirali) - 1))]:.1f} ms, "
              f"maks {max(gecikmeler):.1f} ms, >500ms {sum(x > 500 for x in gecikmeler)}")
    if guvenler:
        print(f"Kilit güveni medyan %{statistics.median(guvenler):.0f}")


if __name__ == "__main__":
    main()
