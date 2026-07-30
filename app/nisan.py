# -*- coding: utf-8 -*-
"""DERIN MAVI — Nisan matematigi: piksel hatasi -> gimbal aci komutu.

Otonom modda (Asama 2-3) hedefi TAKIP etme katmani. Zincir:

    algi.analiz_et -> aktif hedef kutusu
      -> nisan_noktasi()  : nisan noktasi (balon varsa balon, yoksa kutu merkezi)
      -> PDNisanci.adim() : piksel hatasi -> derece -> PD -> (d_yaw, d_pitch)
      -> kontrol.nisan()  : ESP32'ye delta aci komutu

Ayarlar (fov, kp, kd, olu_bolge, ayna) algi.AYAR'dan CANLI okunur — tek ayar kaynagi.
"""
import time

import algi

# Kp (birimsiz): hatanin ne kadari tek adimda kapatilsin. 1.0 = tamami (asma riski).
# Kd (SANIYE): "hedef Kd saniye sonra nerede olacak" — ileri gorus suresi.
#   Klasik "Kd * dHata/dt" yazimi tuzaktir: turev derece/SANIYE, Kp'li terim DERECE
#   cinsindendir; toplayinca kazanc kare hizina baglanir (dt=0.07 s'te D terimi P'yi
#   ezip sistemi geri geri surer — olculdu). Bunun yerine once hata ONGORULUR
#   (tahmin = e + Kd*de/dt), sonra tek Kp uygulanir: birimler tutarli, davranis
#   kare hizindan bagimsiz.
#
# Degerler algi.VARSAYILAN_AYAR'dan gelir — ayarin TEK KAYNAGI orasidir (ayar paneli de
# oradan okur). Burada ikinci bir kopya tutulsaydi biri degisince digeri sessizce yanlis kalirdi.
VARSAYILAN_KP = algi.VARSAYILAN_AYAR["kp"]
VARSAYILAN_KD = algi.VARSAYILAN_AYAR["kd"]      # saniye (~1 kare @ 15 FPS)

# Tespit kutusu kare kare birkac piksel oynar; ham turev bunu buyutur (0-1, 1=yok).
TUREV_YUMUSATMA = 0.5

# Olu bolge: merkeze bu kadar yakinsa komut YOK. Aksi halde sistem her karede titrer
# ve lazer balonun uzerinde sabit duramaz (dwell — CLAUDE.md §7).
OLU_BOLGE_ORAN = algi.VARSAYILAN_AYAR["olu_bolge"]   # %2 — 1280 px'te ±26 px

# Tek komutta gonderilebilecek en buyuk delta (guvenlik: kacak komut olmasin).
MAKS_ADIM_DER = 8.0


def nisan_noktasi(box, balonlar=()):
    """Nisan alinacak (x, y) pikseli.

    Nisan noktasi maketin govdesi DEGIL, ona ait balondur (imha kaniti balonun
    patlamasi, balon maketin altinda — CLAUDE.md §7). Hedefe ait balon: merkezi
    kutunun yatay araliginda ve hedefin ustunde degil; birden fazlaysa en yakini.
    Balon yoksa (or. model balon sinifi icermiyor) kutu merkezine duseriz."""
    x1, y1, x2, y2 = box
    hx = (x1 + x2) * 0.5
    hy = (y1 + y2) * 0.5
    en_iyi, en_iyi_mesafe = None, None
    for bx1, by1, bx2, by2 in balonlar:
        bcx = (bx1 + bx2) * 0.5
        bcy = (by1 + by2) * 0.5
        if not (x1 <= bcx <= x2) or bcy < y1:   # baska hedefin balonu
            continue
        mesafe = abs(bcy - y2) + abs(bcx - hx)
        if en_iyi_mesafe is None or mesafe < en_iyi_mesafe:
            en_iyi, en_iyi_mesafe = (bcx, bcy), mesafe
    return en_iyi if en_iyi is not None else (hx, hy)


def derece_per_piksel(kare_genislik, fov_yatay=None):
    """Yatay FOV'dan derece/piksel. Dikeyde de ayni deger gecerli (ortak odak
    uzunlugu); dikey icin ayri bir FOV sabiti tanimlamak yaygin bir hatadir."""
    if fov_yatay is None:
        fov_yatay = float(algi.AYAR.get("fov", 60.0))
    if kare_genislik <= 0:
        return 0.0
    return float(fov_yatay) / float(kare_genislik)


class PDNisanci:
    """Piksel hatasindan gimbal delta aci komutu ureten PD kontrolcu.

    Integral terimi YOK: komutlar delta oldugu icin integral kalici hatayi
    kapatmak yerine birikip asma ve salinim yaratir (KTR de PD diyor).

        n = PDNisanci()
        d_yaw, d_pitch = n.adim(hedef_xy, kare_boyut)   # (None, None) -> komut yok
        n.sifirla()                                     # hedef/mod degisince
    """

    def __init__(self, kp=None, kd=None, olu_bolge=None, maks_adim=MAKS_ADIM_DER):
        # None birakilan kazanc ayar panelinden CANLI okunur; verilen deger sabitlenir
        # (testlerde kullanilir).
        self._kp, self._kd, self._olu = kp, kd, olu_bolge
        self.maks_adim = maks_adim
        self._son_hata = None      # (ex_der, ey_der)
        self._son_t = None
        self._hiz = (0.0, 0.0)     # yumusatilmis hata degisim hizi (derece/sn)

    def sifirla(self):
        """Turev gecmisini temizler. Hedef kaybolunca/degisince cagrilmali; yoksa yeni
        hedefin ilk karesinde sahte bir 'ani buyuk hiz' hesaplanip gimbal sicrar."""
        self._son_hata = None
        self._son_t = None
        self._hiz = (0.0, 0.0)

    # Kazanclar panelden degisince aninda etki etsin diye property.
    @property
    def kp(self):
        return float(algi.AYAR.get("kp", VARSAYILAN_KP)) if self._kp is None else self._kp

    @property
    def kd(self):
        return float(algi.AYAR.get("kd", VARSAYILAN_KD)) if self._kd is None else self._kd

    @property
    def olu_bolge(self):
        return (float(algi.AYAR.get("olu_bolge", OLU_BOLGE_ORAN))
                if self._olu is None else self._olu)

    def adim(self, hedef_xy, kare_boyut, simdi=None):
        """Bir kontrol adimi.

        hedef_xy   : nisan noktasi (x, y) piksel
        kare_boyut : (genislik, yukseklik) piksel
        Doner (d_yaw, d_pitch) derece; (None, None) = komut gonderme.
        """
        if hedef_xy is None or kare_boyut is None:
            self.sifirla()
            return None, None
        w, h = kare_boyut
        if w <= 0 or h <= 0:
            return None, None

        simdi = time.time() if simdi is None else simdi
        hx, hy = hedef_xy
        px = hx - w * 0.5              # +x = hedef sagda
        py = hy - h * 0.5              # +y = hedef asagida

        if abs(px) <= w * self.olu_bolge and abs(py) <= h * self.olu_bolge:
            self._son_hata = None      # yerlestik; sonraki kacista turev sifirdan
            self._son_t = simdi
            return None, None

        dpp = derece_per_piksel(w)
        ex = px * dpp                  # yaw hatasi (derece)
        ey = py * dpp                  # pitch hatasi (derece)

        # Goruntu aynalanmissa pikseldeki "saga kacis" gercekte soladir; telafi
        # edilmezse gimbal hedeften KACAR (pozitif geri besleme).
        if int(algi.AYAR.get("ayna", 0)):
            ex = -ex

        # protokol.py'de +dy = YUKARI; hedef altta ise (py>0) gimbal asagi donmeli.
        ey = -ey

        # Hata degisim hizi (yumusatilmis) -> ileri gorus icin.
        if self._son_hata is not None and self._son_t is not None:
            dt = simdi - self._son_t
            if dt > 1e-3:
                ham = ((ex - self._son_hata[0]) / dt, (ey - self._son_hata[1]) / dt)
                y = TUREV_YUMUSATMA
                self._hiz = (self._hiz[0] * (1 - y) + ham[0] * y,
                             self._hiz[1] * (1 - y) + ham[1] * y)
        self._son_hata = (ex, ey)
        self._son_t = simdi

        # Ongorulen hataya tek kazanc uygula (tum terimler DERECE cinsinden).
        d_yaw = self.kp * (ex + self.kd * self._hiz[0])
        d_pitch = self.kp * (ey + self.kd * self._hiz[1])

        # Guvenlik: tek komutta kacak aci gonderme.
        d_yaw = max(-self.maks_adim, min(self.maks_adim, d_yaw))
        d_pitch = max(-self.maks_adim, min(self.maks_adim, d_pitch))
        return d_yaw, d_pitch


if __name__ == "__main__":
    # --- nisan_noktasi: balon varsa balona nisan al ---
    hedef = (100, 100, 200, 180)                 # maket kutusu
    balon_alt = (140, 190, 160, 215)             # maketin ALTINDA (bizim balonumuz)
    balon_baska = (400, 190, 420, 215)           # baska hedefin balonu (yatayda uzak)
    assert nisan_noktasi(hedef, []) == (150.0, 140.0)                 # balon yok -> merkez
    assert nisan_noktasi(hedef, [balon_alt]) == (150.0, 202.5)        # balona nisan
    assert nisan_noktasi(hedef, [balon_baska]) == (150.0, 140.0)      # baskasininki sayilmaz
    assert nisan_noktasi(hedef, [balon_baska, balon_alt]) == (150.0, 202.5)

    # --- derece/piksel ---
    algi.ayar_guncelle(fov=60.0)
    assert abs(derece_per_piksel(1280) - 60.0 / 1280) < 1e-9

    kare = (1280, 720)
    n = PDNisanci()

    # 1. Merkezdeki hedef -> komut YOK (olu bolge).
    assert n.adim((640, 360), kare) == (None, None)

    # 2. Hedef SAGDA -> yaw POZITIF (saga don). Hedef ASAGIDA -> pitch NEGATIF (asagi).
    dy, dp = n.adim((1000, 600), kare, simdi=1.0)
    assert dy is not None and dy > 0, dy
    assert dp is not None and dp < 0, dp
    assert abs(dy) <= MAKS_ADIM_DER and abs(dp) <= MAKS_ADIM_DER

    # 3. Hedef SOLDA/YUKARIDA -> isaretler ters.
    n.sifirla()
    dy2, dp2 = n.adim((280, 120), kare, simdi=1.0)
    assert dy2 < 0 and dp2 > 0, (dy2, dp2)

    # 4. AYNA acikken yaw isareti TERS cevrilmeli (yoksa gimbal hedeften kacar).
    n.sifirla()
    dy_normal, _ = n.adim((1000, 360), kare, simdi=1.0)
    algi.ayar_guncelle(ayna=1)
    n.sifirla()
    dy_ayna, _ = n.adim((1000, 360), kare, simdi=1.0)
    assert dy_normal > 0 and dy_ayna < 0, (dy_normal, dy_ayna)
    algi.ayar_guncelle(ayna=0)

    # 5. Maks adim kirpmasi: kadrajin en kenarindaki hedef bile siniri asmamali.
    n.sifirla()
    dy3, dp3 = n.adim((1279, 719), kare, simdi=1.0)
    assert abs(dy3) <= MAKS_ADIM_DER and abs(dp3) <= MAKS_ADIM_DER

    # 6. sifirla() turev gecmisini temizlemeli (yeni hedefte sicrama olmasin).
    n.sifirla()
    assert n._son_hata is None and n._son_t is None

    # --- Kapali cevrim benzetimi: gimbal dondukce hedef kadrajda merkeze kayar ---
    KARE_SURESI = 0.07

    def benzet(adim_sayisi, hedef_px, hedef_hizi=0.0):
        """Doner: her adimdaki merkez hatasi (piksel) listesi."""
        n.sifirla()
        yaw, t, iz = 0.0, 0.0, []
        for _ in range(adim_sayisi):
            t += KARE_SURESI
            hedef_px += hedef_hizi * KARE_SURESI
            gorunen = hedef_px - yaw / derece_per_piksel(1280)
            iz.append(gorunen - 640)
            d_yaw, _dp = n.adim((gorunen, 360), kare, simdi=t)
            if d_yaw is not None:
                yaw += d_yaw
        return iz

    # 7. SABIT hedef: olu bolgeye kadar yakinsamali, hem de SALINMADAN/ASMADAN.
    iz = benzet(60, 1100.0)
    assert abs(iz[-1]) <= 1280 * OLU_BOLGE_ORAN, f"yakinsamadi: {iz[-1]:.1f} px"
    inisli = [v for v in iz if v > 1280 * OLU_BOLGE_ORAN]
    assert all(inisli[i + 1] < inisli[i] for i in range(len(inisli) - 1)), f"salinim: {iz}"
    assert min(iz) >= -1280 * OLU_BOLGE_ORAN, f"asma (overshoot): {iz}"

    # 8. HAREKETLI hedef (Yetenek 5). Sabit hizda kalici bir gecikme OTURUR:
    #    kalici_hata ~ (hedef_hizi * kare_suresi) / Kp = (250*0.07)/0.5 = 35 px
    #    D terimi bunu kapatmaz (sabit hizda hatanin turevi sifirdir); azaltmak icin
    #    Kp yukseltilir veya FPS artirilir. Donanim gelince Kp panelden ayarlanmali.
    iz = benzet(80, 640.0, hedef_hizi=250.0)
    kararli_hal = [abs(v) for v in iz[25:]]
    assert max(kararli_hal) < 60, f"hareketli hedef takibi zayif: {max(kararli_hal):.0f} px"

    print("nisan testleri OK — balon nisani, isaretler, ayna telafisi, kirpma, "
          "yakinsama, salinimsizlik, hareketli hedef")
