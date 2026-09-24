# -*- coding: utf-8 -*-
"""DERIN MAVI — Nisan matematigi: piksel hatasi -> gimbal aci komutu.

Otonom modda (Asama 2-3) hedefi TAKIP etme katmani. Zincir:

    algi.analiz_et -> aktif hedef kutusu
      -> nisan_noktasi()  : nisan noktasi (balon varsa balon, yoksa kutu merkezi)
      -> PDNisanci.adim() : piksel hatasi -> derece -> PD -> (d_yaw, d_pitch)
      -> kontrol.nisan()  : ESP32'ye delta aci komutu

Ayarlar (fov, kp, kd, olu_bolge, lazer_ofset_x/y) algi.AYAR'dan CANLI okunur — tek ayar kaynagi.
"""
import math
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

# Tespit kutusu kare kare birkac piksel oynar; ham turev bunu buyutur. ZAMAN-SABITI
# (saniye) tabanli yumusatma kullanilir — sabit-orneklem alfa DEGIL. Sabit alfa (eski:
# 0.5 her karede) FPS yukseldikce gercek-zamanda DAHA AZ filtreler: 4 FPS'te 0.5 alfa
# ~0.25 sn'lik bir pencereyi yumusatirken, 15 FPS'te AYNI 0.5 alfa ~0.07 sn'lik pencereyi
# yumusatir — gurultu ~3-4x daha az bastirilir. OpenVINO ile FPS ~4 -> ~15'e cikinca
# (13.08) namlunun "asiri/sacma" titremesinin bas sebeplerinden biri buydu. Alfa =
# 1 - exp(-dt/TUREV_ZAMAN_SABITI) ile FPS'ten BAGIMSIZ, sabit gercek-zaman filtrelemesi
# saglanir (bkz. adim()).
TUREV_ZAMAN_SABITI = 0.12   # saniye

# Olu bolge: merkeze bu kadar yakinsa komut YOK. Aksi halde sistem her karede titrer
# ve lazer balonun uzerinde sabit duramaz (dwell — CLAUDE.md §7).
OLU_BOLGE_ORAN = algi.VARSAYILAN_AYAR["olu_bolge"]   # %2 — 1280 px'te ±26 px

# Olu bolgenin PIKSEL taban degeri. Kutuya oranli olu bolge cok kucuk hedefte
# sifira yaklasir; tespit kutusu zaten kare kare birkac piksel titrestigi icin
# bunun altini kovalamak sonsuz arayisa (hunting) yol acar, dwell hic tamamlanmaz.
TABAN_OLU_BOLGE_PX = 4.0

# Tek adimda gonderilebilecek en buyuk delta — YALNIZCA ilk cagrida (dt bilinmiyor,
# hedef yeni kilitlendi) kullanilan SABIT guvenlik tavani. Sonraki cagrilarda gercek
# tavan MainWindow._nisan_geldi()'de secili motor hizina (P.HIZ_TABLO) gore, gecen
# sureyle olceklenerek ayrica kirpilir — PD burada yalnizca "makul" bir ilk-adim
# sinirini garanti eder, motorun gercekten yetisebileceginden BAGIMSIZDIR.
MAKS_ADIM_DER = 8.0


# Nisan noktasi geometrisi algi.py'de yasar ve BURADAN YENIDEN YAYINLANIR.
#
# Neden orada: ayni hesabi UC yer kullaniyor — bu PD kontrolcusu, Qt canli
# gorunumdeki nisangah ve algi.draw_overlay. Uc ayri kopya olsaydi ekrandaki
# arti, lazerin gercekte gittigi yerden baska bir noktayi gosterebilirdi.
# Neden burada DEGIL: algi.py bu modulu import EDEMEZ (nisan -> algi bagimliligi
# zaten var, tersi dongusel olurdu), o yuzden ortak sahip algi.py.
#
# Ozet: nisan noktasi BALONDUR (maketin ALTINDA), govde merkezi degil. Balon
# tespit edilebiliyorsa gercek balon, edilemiyorsa kutu yuksekliginin
# `balon_ofset` kati kadar altindaki nokta. Ayrinti icin algi.nisan_noktasi.
nisan_noktasi = algi.nisan_noktasi


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
        # Teshis (arayuz okur, kontrol matematigine KATILMAZ): son karedeki piksel
        # hatasi ve o karede gecerli olu bolge yaricapi. Ates kapisi "hata < olu
        # bolge" olunca aciliyor; ikisi gorunmezse operator neden ates edilmedigini
        # anlayamiyor — sahada tam bu yasandi (16.08).
        self.son_hata_px = None    # (px, py) — nisan noktasinin lazer referansina uzakligi
        self.son_olu_px = None     # (olu_x, olu_y) — o karedeki olu bolge yaricapi

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

    @property
    def olu_bolge_kutu(self):
        return float(algi.AYAR.get("olu_bolge_kutu",
                                   algi.VARSAYILAN_AYAR["olu_bolge_kutu"]))

    def _olu_bolge_px(self, hedef_yukseklik, w, h, olu_orani=None):
        """Olu bolgeyi PIKSEL olarak verir: (yatay_yaricap, dikey_yaricap).

        Hedef kutusunun yuksekligi biliniyorsa olcut KUTUYA oranlidir — sartname
        (s.19) balonu "kesit alanina gore belli bir buyuklukte" tanimladigi icin
        balon ekranda hedefle birlikte kucuur; sabit bir kare yuzdesi uzak hedefte
        balondan genis kalir ve sistem lazer balonun yanindayken "hedefteyim" der.
        Kutu bilinmiyorsa (eski cagri bicimi, testler) kareye oranli davranisa doner.

        TABAN_PX: cok kucuk kutuda olu bolge sifira yaklasip sistemi sonsuz
        arayisa (hunting) sokmasin diye alt sinir — tespit kutusu zaten kare kare
        birkac piksel oynuyor, onun altini kovalamak anlamsiz.
        """
        if hedef_yukseklik and hedef_yukseklik > 0:
            oran = self.olu_bolge_kutu if olu_orani is None else float(olu_orani)
            r = max(TABAN_OLU_BOLGE_PX, hedef_yukseklik * oran)
            return r, r
        return w * self.olu_bolge, h * self.olu_bolge

    @property
    def ofset_x(self):
        """Kamera-lazer boresight ofseti (kare genisliginin orani). Kalibrasyon
        aci.VARSAYILAN_AYAR["lazer_ofset_x"] = 0.0 (canli okunur, ayar panelinden)."""
        return float(algi.AYAR.get("lazer_ofset_x", 0.0))

    @property
    def ofset_y(self):
        return float(algi.AYAR.get("lazer_ofset_y", 0.0))

    def adim(self, hedef_xy, kare_boyut, simdi=None, hedef_yukseklik=None, olu_orani=None):
        """Bir kontrol adimi.

        hedef_xy        : nisan noktasi (x, y) piksel
        kare_boyut      : (genislik, yukseklik) piksel
        hedef_yukseklik : hedef kutusunun yuksekligi (piksel). Verilirse olu bolge
                          KUTUYA oranli olur (bkz. _olu_bolge_px); verilmezse
                          kareye oranli eski davranis surer.
        olu_orani       : kutu BALONUN kendisiyse (balon_takip) olu bolge = yukseklik x
                          bu oran; arac kutusuna gore ayarli olu_bolge_kutu kullanilmaz.
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
        # Denge noktasi kare MERKEZI degil, kalibre edilmis lazer referansidir:
        # kamera ekseni hedefte iken lazer ofset_x/y kadar kaymis vuruyorsa, gimbal
        # o kaymayi ONCEDEN telafi edecek sekilde durmali (bkz. algi.py boresight notu).
        px = hx - w * 0.5 - self.ofset_x * w   # +x = hedef sagda
        py = hy - h * 0.5 - self.ofset_y * h   # +y = hedef asagida

        olu_x, olu_y = self._olu_bolge_px(hedef_yukseklik, w, h, olu_orani)
        self.son_hata_px = (px, py)      # teshis (bkz. __init__)
        self.son_olu_px = (olu_x, olu_y)
        if abs(px) <= olu_x and abs(py) <= olu_y:
            self._son_hata = None      # yerlestik; sonraki kacista turev sifirdan
            self._son_t = simdi
            return None, None

        dpp = derece_per_piksel(w)
        ex = px * dpp                  # yaw hatasi (derece): +x = hedef sagda -> +ex
        ey = py * dpp                  # pitch hatasi (derece)

        # D-pad "Sag" tusu pan'i +1 yonunde hareket ettirir (donanimda dogrulandi,
        # YON_TABLO["right"]=+1.0) -> hedef sagdayken +ex, negatif ETME. Eskiden burada
        # "goruntu aynalanmissa ex=-ex" koşulu vardi (yazilimsal flip acikken gerekliydi);
        # flip ozelligi kaldirildigindan (cv2.flip kalici KAPALI, arayuz_qt.py) hicbir
        # negatiflemeye gerek yok. Koşulsuz negatifleme BURADA BIR SURE durdu ve yaw
        # yonunu tersine cevirip gimbali hedeften kacirdi — CLAUDE.md'ye not dusuldu.

        # protokol.py'de +dy = YUKARI; hedef altta ise (py>0) gimbal asagi donmeli.
        ey = -ey

        # NOT: Balon (hedef alti) ofseti BURADA DEGIL, nisan_noktasi()'nda uygulanir.
        # Burada bir sure sabit "ey -= 3.0" duruyordu; iki sebeple yanlisti:
        #   1. Sabit aci mesafeye gore olceklenmez (5 m'de dogru, 15 m'de uc kati).
        #   2. Yukaridaki olu bolge kontrolu bu satirdan ONCE calisiyor ve kare
        #      MERKEZINE olan uzakliga bakiyordu -> govde ortalanir ortalanmaz
        #      (None, None) donuyor, ofset dinlenme noktasina HIC yansimiyordu.
        #      Yani lazer balona degil govdeye nisan aliyordu ve ustelik ates
        #      kapisi (`merkezde`) "govde ortalandi" anlamina geliyordu.
        # Ofset nisan noktasina tasininca olu bolge dogrudan NISAN NOKTASINA olan
        # uzakligi olcer: `merkezde` artik "lazer balonun uzerinde" demektir.

        # Hata degisim hizi (yumusatilmis) -> ileri gorus icin. Alfa dt'den turer
        # (sabit-orneklem DEGIL) — bkz. TUREV_ZAMAN_SABITI yorumu: FPS degisince
        # (dt kuculunce/buyuyunce) filtrenin GERCEK-ZAMANDAKI gucu SABIT kalir.
        if self._son_hata is not None and self._son_t is not None:
            dt = simdi - self._son_t
            if dt > 1e-3:
                ham = ((ex - self._son_hata[0]) / dt, (ey - self._son_hata[1]) / dt)
                y = 1.0 - math.exp(-dt / TUREV_ZAMAN_SABITI)
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

        # EKSEN BAZLI OLU BOLGE. Yukaridaki "merkezde" karari IKI ekseni birlikte
        # ister (ates kapisi bunu kullanir, o yuzden boyle kalir). Ama komut ekseni
        # tek tek kesilmeli: bir eksen yerlesmisken digeri yerlesmemisse, yerlesmis
        # eksen her karede tespit kutusunun birkac piksellik oynamasini (ve elde
        # tutulan hedefin titremesini) komut olarak surerdi. Sahada tam bu goruldu:
        # pan motoru yokken yatay hata hic sifirlanmiyor, dolayisiyla olu bolge hic
        # devreye girmiyordu; dikey hata 0-10 px iken 40 sn'de 141 komut gitti ve
        # namlu 7.6-7.9 derece arasinda gidip geldi (26 dur-kalk). 0.0 = o eksene
        # KOMUT YOK (arayuz o ekseni oldugu gibi birakir).
        if abs(px) <= olu_x:
            d_yaw = 0.0
        if abs(py) <= olu_y:
            d_pitch = 0.0
        return d_yaw, d_pitch


if __name__ == "__main__":
    # --- nisan_noktasi: nisan noktasi BALONDUR, govde merkezi DEGIL ---
    hedef = (100, 100, 200, 180)                 # maket kutusu (yukseklik 80)
    balon_alt = (140, 190, 160, 215)             # maketin ALTINDA (bizim balonumuz)
    balon_baska = (400, 190, 420, 215)           # baska hedefin balonu (yatayda uzak)
    algi.ayar_guncelle(balon_ofset=0.40)

    # 1. Gercek balon tespiti varsa o kazanir.
    assert nisan_noktasi(hedef, [balon_alt]) == (150.0, 202.5)
    assert nisan_noktasi(hedef, [balon_baska, balon_alt]) == (150.0, 202.5)

    # 2. Balon gorunmuyorsa yeri kutudan kestirilir: alt kenar + 0.40 * yukseklik.
    assert nisan_noktasi(hedef, []) == (150.0, 180 + 80 * 0.40)       # = 212.0
    assert nisan_noktasi(hedef, [balon_baska]) == (150.0, 212.0)      # baskasininki sayilmaz

    # 3. Nisan noktasi HER ZAMAN govde merkezinin ALTINDA olmali (balon asagida).
    assert nisan_noktasi(hedef, [])[1] > (100 + 180) * 0.5

    # 4. Ofset MESAFEDEN BAGIMSIZ: ayni maket yarim boyutta gorununce (2x uzak)
    #    nisan noktasinin kutuya gore BAGIL yeri degismemeli.
    uzak = (100, 100, 150, 140)                  # ayni maket, yukseklik 40 (yarisi)
    yakin_bagil = (nisan_noktasi(hedef, [])[1] - 180) / 80.0
    uzak_bagil = (nisan_noktasi(uzak, [])[1] - 140) / 40.0
    assert abs(yakin_bagil - uzak_bagil) < 1e-9, (yakin_bagil, uzak_bagil)

    # 5. Ayar 0 ise nisan noktasi kutunun tam alt kenari olur.
    algi.ayar_guncelle(balon_ofset=0.0)
    assert nisan_noktasi(hedef, []) == (150.0, 180.0)
    algi.ayar_guncelle(balon_ofset=0.40)

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

    # 4. Boresight ofseti (kamera-lazer kalibrasyonu): merkezdeki hedef, ofset sifirsa
    #    komut YOK ama pozitif X ofsetiyle "hedef solda kalmis" gibi davranmali (denge
    #    noktasi saga kaymis) -> yaw NEGATIF (sola don, lazeri hedefe getirmek icin).
    algi.ayar_guncelle(lazer_ofset_x=0.05)
    n.sifirla()
    dy_ofset, _ = n.adim((640, 360), kare, simdi=1.0)
    assert dy_ofset is not None and dy_ofset < 0, dy_ofset
    algi.ayar_guncelle(lazer_ofset_x=0.0)

    # 5. Maks adim kirpmasi: kadrajin en kenarindaki hedef bile siniri asmamali.
    n.sifirla()
    dy3, dp3 = n.adim((1279, 719), kare, simdi=1.0)
    assert abs(dy3) <= MAKS_ADIM_DER and abs(dp3) <= MAKS_ADIM_DER

    # 6. sifirla() turev gecmisini temizlemeli (yeni hedefte sicrama olmasin).
    n.sifirla()
    assert n._son_hata is None and n._son_t is None

    # --- Olu bolge KUTUYA oranli (isabet payi) ---
    algi.ayar_guncelle(olu_bolge_kutu=0.12)
    n2 = PDNisanci()

    # 6a. Kutu verilmezse kareye oranli ESKI davranis surer (geriye donuk uyum).
    assert n2._olu_bolge_px(None, 1920, 1080) == (1920 * n2.olu_bolge, 1080 * n2.olu_bolge)

    # 6b. Kutu verilirse olcut kutuya oranli ve IKI EKSENDE AYNI olur (balon yuvarlak).
    ox, oy = n2._olu_bolge_px(200.0, 1920, 1080)
    assert ox == oy == 200.0 * 0.12, (ox, oy)

    # 6c. ⭐ ASIL KAZANC: uzak hedefte olu bolge KUCULUR. Eski sabit-kare olcutu
    #     15 m'de balondan genis kaliyordu (lazer yaninda dururken "hedefteyim").
    yakin, _ = n2._olu_bolge_px(200.0, 1920, 1080)
    uzak, _ = n2._olu_bolge_px(70.0, 1920, 1080)
    assert uzak < yakin, (uzak, yakin)
    assert uzak < 1920 * n2.olu_bolge, "uzak hedefte olu bolge eski sabit olcutten dar olmali"

    # 6d. Cok kucuk kutuda taban devreye girer (sonsuz arayis olmasin).
    kucucuk, _ = n2._olu_bolge_px(5.0, 1920, 1080)
    assert kucucuk == TABAN_OLU_BOLGE_PX

    # 6d'. Kutu BALONUN KENDISIYSE (balon_takip) olu bolge kendi oraniyla: 40 px balonda
    #      0.25 -> 10 px (yaricapin yarisi); arac orani (0.12) 4.8 px'e daraltirdi.
    balon_r, _ = n2._olu_bolge_px(40.0, 1920, 1080, olu_orani=0.25)
    assert balon_r == 10.0, balon_r
    n2.sifirla()
    assert n2.adim((1920 * 0.5 + 8.0, 1080 * 0.5), (1920, 1080), simdi=1.0,
                   hedef_yukseklik=40.0, olu_orani=0.25) == (None, None)
    n2.sifirla()
    assert n2.adim((1920 * 0.5 + 8.0, 1080 * 0.5), (1920, 1080), simdi=1.0,
                   hedef_yukseklik=40.0)[0] is not None, "kurulum: arac oraninda 8 px disarida"

    # 6e. Uctan uca: ayni piksel hatasi, YAKIN hedefte "yerlesti" sayilirken
    #     UZAK hedefte sayilmamali (daha hassas nisan istenir).
    kare_orta = (1920 * 0.5 + 15.0, 1080 * 0.5)     # merkeze 15 px yatay hata
    n2.sifirla()
    assert n2.adim(kare_orta, (1920, 1080), simdi=1.0, hedef_yukseklik=200.0) == (None, None)
    n2.sifirla()
    dy_uzak, _ = n2.adim(kare_orta, (1920, 1080), simdi=1.0, hedef_yukseklik=70.0)
    assert dy_uzak is not None, "uzak hedefte 15 px hata icin komut URETILMELIYDI"

    # 6f. ⭐ EKSEN BAZLI OLU BOLGE: yatay hata buyukken (pan henuz yerlesmemis ya da
    #     pan motoru hic yok) dikeyde olu bolge icindeki kucuk hata KOMUT URETMEMELI.
    #     Sahada tam tersi oluyordu ve namlu tespit gurultusunu surup titriyordu.
    n3 = PDNisanci()
    for t_, dy_px in ((1.0, 3.0), (1.07, -4.0), (1.13, 5.0), (1.2, -2.0)):
        d_y, d_p = n3.adim((1920 * 0.5 + 400, 1080 * 0.5 + dy_px), (1920, 1080),
                           simdi=t_, hedef_yukseklik=200.0)
        assert d_y is not None and d_y > 0, "yatay hata icin komut uretilmeliydi"
        assert d_p == 0.0, f"dikey olu bolge icinde komut uretildi: {d_p}"
    #     ...ve tersi: dikey hata buyukse dikey komut normal uretilir
    d_y, d_p = n3.adim((1920 * 0.5 + 400, 1080 * 0.5 + 200), (1920, 1080),
                       simdi=1.3, hedef_yukseklik=200.0)
    assert d_p is not None and d_p < 0, d_p

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

    print("nisan testleri OK — balon nisani, isaretler, boresight ofseti, kirpma, "
          "yakinsama, salinimsizlik, hareketli hedef")
