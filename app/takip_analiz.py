# -*- coding: utf-8 -*-
"""DERIN MAVI — TAKIP ANALIZI: kara kutu kaydindan ppd ve gecikmeyi OLCER.

    python app/takip_analiz.py loglar/takip_20260923_201500.csv

NE ISE YARAR. Sahada "takip titriyor / geriden geliyor" belirtisinin dort ayri
sebebi ayni gorunur:
  1. ppd (piksel/derece) yanlis  -> her karede hata YANLIS aciya cevrilir; buyukse
     namlu hedefi asar (salinim), kucukse hep geride kalir.
  2. Gecikme telafisi yanlis     -> kare "ne zaman cekildi" yanlis bilinir; eksen
     hareket halindeyken bu, hedefin kendi hareketi gibi gorunur -> kendini
     besleyen salinim.
  3. Kilit atlamasi              -> olcum bir anda baska bir nesneye kayar.
  4. Kutu gurultusu              -> olcumun kendisi titrer.
Bu arac dordunu de AYRI AYRI raporlar; ilk ikisini SAYIYLA olcup onerilen ayar
degerini yazar.

OLCUM YONTEMI (ppd + gecikme birlikte). Hedefin dunya acisi
    z(t) = eksen_acisi(t - δ) + isaret * hata_px(t) / ppd
gercek δ ve ppd ile HEDEFIN kendi yolunu verir: hedef fiziksel bir nesnedir,
yolu PURUZSUZDUR. Yanlis δ/ppd ise EKSENIN kendi hareketini z'ye sizdirir ve yol
zikzaklasir. Bu yuzden (δ, ppd) ikilisi, z'nin puruzsuzlugunu (ikinci farklarin
karesi) EN KUCUK yapan degerdir. Eksen hic hareket etmediyse bilgi yoktur —
arac bunu soyler, uydurmaz.

Kendi kendini test:  python app/takip_analiz.py   (sentetik kayitla dogrular)
"""
import csv
import math
import os
import sys

SAYISAL = ("t", "t_kare", "gecikme_ms", "conf", "x1", "y1", "x2", "y2", "nisan_x",
           "nisan_y", "ex_px", "ey_px", "olu_x_px", "olu_y_px", "kare_w", "kare_h",
           "pan_kare", "tilt_kare", "pan_simdi", "tilt_simdi", "ppd", "kest_pan",
           "kest_pan_hiz", "kest_tilt", "kest_tilt_hiz", "kom_pan", "kom_pan_hiz",
           "kom_tilt", "kom_tilt_hiz", "fps")


def oku(yol):
    """CSV -> satir sozlukleri listesi (sayisal alanlar float, bos alan None)."""
    satirlar = []
    with open(yol, encoding="utf-8") as f:
        for ham in csv.DictReader(l for l in f if not l.startswith("#")):
            s = dict(ham)
            for ad in SAYISAL:
                v = s.get(ad)
                if v in (None, ""):
                    s[ad] = None
                else:
                    try:
                        s[ad] = float(v)
                    except ValueError:
                        s[ad] = None
            satirlar.append(s)
    return satirlar


class Egri:
    """Zaman-deger ornekleri; aradaki degeri dogrusal verir (eksen acisi icin)."""

    def __init__(self, ornekler):
        self.t = [t for t, _ in ornekler]
        self.v = [v for _, v in ornekler]

    def __bool__(self):
        return len(self.t) >= 2

    def deger(self, t):
        if not self.t:
            return None
        if t <= self.t[0]:
            return self.v[0]
        if t >= self.t[-1]:
            return self.v[-1]
        lo, hi = 0, len(self.t) - 1
        while hi - lo > 1:
            orta = (lo + hi) // 2
            if self.t[orta] <= t:
                lo = orta
            else:
                hi = orta
        t0, t1 = self.t[lo], self.t[hi]
        if t1 - t0 <= 1e-9:
            return self.v[lo]
        k = (t - t0) / (t1 - t0)
        return self.v[lo] * (1 - k) + self.v[hi] * k


def _puruzsuzluk(z, t):
    """Yolun ZIKZAK olcusu: ikinci farkin zamana gore normalize karesi (medyan).

    Medyan, ortalamadan iyidir: kilit atladiginda tek bir dev sicrama tum
    ortalamayi ele gecirir ve olcum anlamsizlasir."""
    d = []
    for i in range(1, len(z) - 1):
        dt1, dt2 = t[i] - t[i - 1], t[i + 1] - t[i]
        if dt1 <= 1e-4 or dt2 <= 1e-4:
            continue
        h1 = (z[i] - z[i - 1]) / dt1
        h2 = (z[i + 1] - z[i]) / dt2
        d.append(((h2 - h1) / (0.5 * (dt1 + dt2))) ** 2)
    if not d:
        return None
    d.sort()
    return d[len(d) // 2]


def gecikme_olc(satirlar, eksen="pan", gecikme_araligi=(-0.05, 0.30)):
    """(ek_gecikme_sn, sebep) doner. ek_gecikme: kayitta KULLANILAN `kamera_gecikme`
    degerinin USTUNE eklenmesi gereken sure.

    ⚠ YALNIZ GECIKME olculur, ppd DEGIL. Ikisi birlikte aranirsa cozum tek degildir:
    ppd buyudukce piksel teriminin katkisi sifira gider ve "puruzsuzluk" olcutu
    ppd'yi sonsuza iter (denendi, 40'a dayandi). ppd, kayitta kullanilan degerden
    alinir; o yanlissa ayri olculur (⚙ TAKIP > Takip olcegi aciklamasi).
    """
    aci_ad = "pan_simdi" if eksen == "pan" else "tilt_simdi"
    kare_ad = "pan_kare" if eksen == "pan" else "tilt_kare"
    isaret = 1.0 if eksen == "pan" else -1.0
    hata_ad = "ex_px" if eksen == "pan" else "ey_px"

    ornek = [(s["t"], s[aci_ad]) for s in satirlar if s["t"] is not None and s[aci_ad] is not None]
    ornek.sort()
    egri = Egri(ornek)
    olcum = [s for s in satirlar
             if s.get("kaynak") == "model" and s[hata_ad] is not None
             and s["t_kare"] is not None and s[kare_ad] is not None and s["ppd"]]
    if len(olcum) < 30:
        return None, "yeterli model olcumu yok (en az 30 kare gerekir)"
    if not egri:
        return None, "eksen acisi kaydi yok"
    hareket = max(egri.v) - min(egri.v)
    if hareket < 2.0:
        return None, f"eksen neredeyse hic donmemis ({hareket:.1f}°) — olcum icin bilgi yok"

    t_kare = [s["t_kare"] for s in olcum]
    hata = [s[hata_ad] for s in olcum]
    ppd = [s["ppd"] for s in olcum]
    en_iyi = None
    for gi in range(61):
        gec = gecikme_araligi[0] + (gecikme_araligi[1] - gecikme_araligi[0]) * gi / 60.0
        aci = [egri.deger(tk - gec) for tk in t_kare]
        if any(a is None for a in aci):
            continue
        z = [a + isaret * h / p for a, h, p in zip(aci, hata, ppd)]
        pz = _puruzsuzluk(z, t_kare)
        if pz is None:
            continue
        if en_iyi is None or pz < en_iyi[0]:
            en_iyi = (pz, gec)
    if en_iyi is None:
        return None, "olcum penceresi hesaplanamadi"
    return en_iyi[1], None


def _yuzdelik(v, y):
    if not v:
        return None
    s = sorted(v)
    return s[min(len(s) - 1, max(0, int(round(y * (len(s) - 1)))))]


def ozet(satirlar):
    """Insan-okur teshis metni (liste of satir)."""
    cikti = []
    n = len(satirlar)
    if not n:
        return ["Kayit bos."]
    sure = (satirlar[-1]["t"] or 0) - (satirlar[0]["t"] or 0)
    kaynaklar = {}
    for s in satirlar:
        kaynaklar[s.get("kaynak") or "?"] = kaynaklar.get(s.get("kaynak") or "?", 0) + 1
    kip = {}
    for s in satirlar:
        kip[s.get("kip") or "?"] = kip.get(s.get("kip") or "?", 0) + 1
    cikti.append(f"Kayit: {n} kare, {sure:.1f} sn "
                 f"({n / sure:.1f} kare/sn)" if sure > 0 else f"Kayit: {n} kare")
    cikti.append("Kip: " + ", ".join(f"{a}={b}" for a, b in sorted(kip.items())))
    cikti.append("Olcum kaynagi: " + ", ".join(
        f"{a}={b} (%{100.0 * b / n:.0f})" for a, b in sorted(kaynaklar.items(), key=lambda x: -x[1])))

    gec = [s["gecikme_ms"] for s in satirlar if s["gecikme_ms"] is not None]
    if gec:
        cikti.append(f"Kare yakalandi -> komut: medyan {_yuzdelik(gec, 0.5):.0f} ms, "
                     f"%95 {_yuzdelik(gec, 0.95):.0f} ms  "
                     "(bu sure OLCULEN gecikmenin ALT SINIRIDIR: kameranin kendi "
                     "gecikmesi bunun ustune biner)")

    for ad, e_ad in (("Yatay", "ex_px"), ("Dikey", "ey_px")):
        h = [abs(s[e_ad]) for s in satirlar if s[e_ad] is not None]
        if h:
            cikti.append(f"{ad} hata: medyan {_yuzdelik(h, 0.5):.0f} px, "
                         f"%95 {_yuzdelik(h, 0.95):.0f} px")

    # Salinim: komut yonunun isaret degistirme sikligi
    for ad, k_ad in (("Yatay", "kom_pan"), ("Dikey", "kom_tilt")):
        komut = [(s["t"], s[k_ad]) for s in satirlar if s[k_ad] is not None and s["t"] is not None]
        if len(komut) < 5:
            continue
        yon, degisim = 0, 0
        for i in range(1, len(komut)):
            fark = komut[i][1] - komut[i - 1][1]
            if abs(fark) < 0.05:
                continue
            y = 1 if fark > 0 else -1
            if yon and y != yon:
                degisim += 1
            yon = y
        if sure > 0:
            cikti.append(f"{ad} komut yon degisimi: {degisim} kez ({degisim / sure * 60:.0f}/dk) "
                         f"- {len(komut)} komut")

    # Kilit atlamasi
    idler = [s.get("id") for s in satirlar if s.get("id") not in (None, "")]
    atlama = sum(1 for a, b in zip(idler, idler[1:]) if a != b)
    if idler:
        cikti.append(f"Kilit ID: {len(set(idler))} farkli, {atlama} kez degisti")

    # Kutu gurultusu: ardisik model karelerinde nisan noktasinin oynamasi
    onceki, oynama = None, []
    for s in satirlar:
        if s.get("kaynak") != "model" or s["nisan_x"] is None:
            onceki = None
            continue
        if onceki is not None and s["id"] == onceki[2]:
            oynama.append(math.hypot(s["nisan_x"] - onceki[0], s["nisan_y"] - onceki[1]))
        onceki = (s["nisan_x"], s["nisan_y"], s.get("id"))
    if oynama:
        cikti.append(f"Nisan noktasi kare-kare oynamasi: medyan {_yuzdelik(oynama, 0.5):.1f} px, "
                     f"%95 {_yuzdelik(oynama, 0.95):.1f} px")

    engeller = {}
    for s in satirlar:
        e = s.get("engel")
        if e:
            engeller[e] = engeller.get(e, 0) + 1
    if engeller:
        cikti.append("Komut gitmeme sebepleri: " + ", ".join(
            f"{a} x{b}" for a, b in sorted(engeller.items(), key=lambda x: -x[1])[:5]))
    return cikti


def rapor(yol):
    satirlar = oku(yol)
    cikti = [f"=== {os.path.basename(yol)} ==="] + ozet(satirlar) + [""]
    kullanilan = next((s["ppd"] for s in satirlar if s["ppd"]), None)
    for eksen, ad in (("pan", "YATAY"), ("tilt", "DIKEY")):
        gec, sebep = gecikme_olc(satirlar, eksen)
        if gec is None:
            cikti.append(f"{ad} gecikme olcumu: YAPILAMADI — {sebep}")
            continue
        cikti.append(f"{ad} gecikme: ayardaki 'Kamera gecikmesi' degerine "
                     f"{gec * 1000:+.0f} ms EKLENMELI")
        if abs(gec) > 0.02:
            cikti.append("    ⚠ Telafi eksik/fazla: eksen hareket ederken hedefin kendi "
                         "hareketi gibi gorunur, salinimi buyutur. ⚙ > TAKIP > Kamera "
                         "gecikmesi ayarini bu kadar degistirin.")
    if kullanilan:
        cikti.append(f"\n(Kayitta kullanilan takip olcegi: {kullanilan:.1f} px/derece)")
    return "\n".join(cikti)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        for yol in sys.argv[1:]:
            print(rapor(yol))
        sys.exit(0)

    # ---- Kendi kendini test: bilinen ppd/gecikme geri bulunabilmeli ----
    import random
    rng = random.Random(4)
    GERCEK_PPD, GERCEK_GEC = 21.2, 0.08
    satirlar = []
    t0 = 1000.0
    # Hedef duzgun salinim yapiyor; eksen hedefi GERIDEN takip ediyor (gercek durum).
    for i in range(400):
        t = t0 + i * 0.05
        hedef = 10.0 * math.sin(0.8 * (t - t0))
        eksen = 10.0 * math.sin(0.8 * (t - t0 - 0.25))          # gerideki eksen
        eksen_kare = 10.0 * math.sin(0.8 * (t - t0 - GERCEK_GEC - 0.25))
        hata_px = (hedef - eksen_kare) * GERCEK_PPD + rng.gauss(0, 0.8)
        satirlar.append({"t": t, "t_kare": t, "kaynak": "model", "kip": "yorunge",
                         "ex_px": hata_px, "ey_px": None, "pan_simdi": eksen,
                         "pan_kare": eksen, "tilt_simdi": None, "tilt_kare": None,
                         "kare_w": 1280.0, "ppd": GERCEK_PPD, "id": "7",
                         "nisan_x": 640.0 + hata_px, "nisan_y": 360.0,
                         "gecikme_ms": 60.0, "kom_pan": eksen, "kom_tilt": None,
                         "olu_x_px": 6.0, "olu_y_px": 6.0, "conf": 90.0,
                         "x1": None, "y1": None, "x2": None, "y2": None, "engel": None,
                         "fps": 20.0, "kest_pan": None, "kest_pan_hiz": None,
                         "kest_tilt": None, "kest_tilt_hiz": None, "kom_pan_hiz": None,
                         "kom_tilt_hiz": None, "kare_h": 720.0})
    gec, sebep = gecikme_olc(satirlar, "pan")
    assert sebep is None, sebep
    assert abs(gec - GERCEK_GEC) < 0.03, (gec, GERCEK_GEC)

    # Eksen hic donmediyse UYDURMAZ
    duran = [dict(s, pan_simdi=0.0, pan_kare=0.0) for s in satirlar]
    g2, s2 = gecikme_olc(duran, "pan")
    assert g2 is None and "donmemis" in s2, (g2, s2)

    # Ozet: kaynak dagilimi ve kilit atlamasi gorunur
    karisik = satirlar[:50] + [dict(s, kaynak="renk", id="9") for s in satirlar[50:60]]
    metin = "\n".join(ozet(karisik))
    assert "renk=10" in metin and "1 kez degisti" in metin, metin
    print("takip_analiz testleri OK — gecikme geri bulundu (80 ms), "
          "bilgisiz kayit reddedildi, ozet dogru")
