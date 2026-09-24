# -*- coding: utf-8 -*-
"""DERIN MAVI — HEDEF KESTIRICI: hedefin DUNYA acisi + acisal hizi (1B Kalman).

NEDEN. Oransal (P/PD) takip yalniz "hedef su an merkezden ne kadar uzak"a bakar:
  1. Hareketli hedefte HEP geride kalir — hedefin HIZINI bilmez, ancak hata olusunca
     tepki verir (kalici gecikme ~ hiz x gecikme / kazanc).
  2. Tespit birkac kare kesilince komut da kesilir, kol durur, hedef kadrajdan kacar.
     Sahada elle hareket ettirilen drone testinde hedef karelerin %46'sinda kayipti.
Kestirici hedefin nerede OLDUGUNU ve nereye GITTIGINI tutar: kol hedefin gidecegi
yere yonelir, kisa kesintide tahminle kovalamaya devam eder.

NEDEN PIKSEL DEGIL DUNYA ACISI. Kamera kolla birlikte doner; hedef sabit dururken
bile pikseli kayar. Pikselde kurulan bir Kalman kolun kendi hareketini hedefin
hareketi sanardi. Olcum, kolun KARE CEKILDIGI andaki acisina eklenir:

        z = kol_acisi(t_kare) - hata_px / piksel_per_derece

(isaret: hata_px > 0 = hedef merkezin ALTINDA -> hedef daha DUSUK acida.)
`piksel_per_derece` kol-komut derecesi basina goruntudeki kayma; kamera montaji ve
mekanizmaya baglidir, OLCULUR (tilt_canli_takip.py --olc_ppd).

Birim: derece (tilt kartinin komut acisi) ve derece/sn.
"""
import math
import statistics as st


class HedefKestirici:
    """Sabit hizli (CV) 1B Kalman. Durum x = [aci, hiz].

        k = HedefKestirici(q=..., r=...)
        k.guncelle(t, z)          # olcum geldi
        k.tahmin(t)               # t anindaki aci tahmini (durumu DEGISTIRMEZ)
        k.kayip_sure(t)           # son olcumden beri gecen sure
    """

    def __init__(self, q=120.0, r=0.4, aykiri_esik=4.0, hiz_siniri=90.0,
                 aykiri_tekrar=2, aykiri_yakinlik=2.0):
        # q: hedef IVMESININ spektral yogunlugu, (derece/sn^2)^2 * sn. Buyuk q = hedefin
        #    ani hiz degistirebilecegi varsayimi (tahmin olcume hizli uyar, gurultuyu
        #    daha az bastirir). Elde tasinan hedef raydakinden cok daha "zipla" oldugu
        #    icin kucuk tutulmaz.
        # r: olcum std sapmasi (derece). Tespit kutusu merkezinin kare-kare oynamasi
        #    (~3 px) + kol acisinin zamanlama hatasi.
        # aykiri_esik: yeniligin (olcum - tahmin) kac std'yi asinca olcumun "baska
        #    bir sey" sayilip kestiricinin SIFIRLANACAGI. Kilit baska nesneye gecerse ya
        #    da kestirici yanlis yone kacarsa eski hizla ilerlemeye devam etmesin.
        self.q = max(1e-6, float(q))
        self.r = max(1e-6, float(r))
        self.aykiri_esik = max(1.0, float(aykiri_esik))
        self.hiz_siniri = None if hiz_siniri is None else max(0.1, float(hiz_siniri))
        self.aykiri_tekrar = max(1, int(aykiri_tekrar))
        self.aykiri_yakinlik = max(self.r, float(aykiri_yakinlik))
        # ADAPTIVE Q (manevra algilama). q_min/q_max verilirse q sabit degildir:
        # normalize yenilik (NIS = y^2 / s) duzgun hareketde ~1 civarindadir; hedef ani
        # yon/hiz degistirince buyur. NIS'in ustel ortalamasina gore q, q_min (guclu
        # yumusatma: el titremesi bastirilir) ile q_max (hizli uyum) arasinda kayar.
        # Tek sabit q ya titremeyi izliyor (buyuk q) ya manevrada geride kaliyordu (kucuk q).
        self.q_min = None
        self.q_max = None
        self.nis = 1.0
        self.nis_yukselis, self.nis_inis = 0.5, 0.1
        self.nis_alt, self.nis_ust = 1.5, 4.0
        self.sifirla()

    def sifirla(self):
        self.x = None          # [aci, hiz]
        self.P = None
        self.t = None          # durumun ait oldugu an
        self.t_olcum = None    # son OLCUMUN ani (kayip suresi buradan)
        self.olcum_sayisi = 0
        self._aykiri_aday = None
        self._aykiri_sayisi = 0
        self.son_yenilik = None
        self.son_aykiri = False

    def _ilk_olcum(self, t, z):
        self.x = [float(z), 0.0]
        # Hiz bilinmiyor: genis belirsizlik (40 derece/sn std).
        self.P = [[self.r ** 2, 0.0], [0.0, 1600.0]]
        self.t = self.t_olcum = float(t)
        self.olcum_sayisi = 1
        self._aykiri_aday = None
        self._aykiri_sayisi = 0

    @property
    def hazir(self):
        # Tek kare konumu verir ama hizi vermez. Ilk karede motoru kosturmak yerine
        # ikinci olcumu beklemek hem sahte tek-kare kutuyu hem ilk hiz sicramesini keser.
        return self.x is not None and self.olcum_sayisi >= 2

    @property
    def baslatildi(self):
        return self.x is not None

    @property
    def hiz(self):
        return 0.0 if self.x is None else self.x[1]

    def _ilerlet(self, t):
        """Durumu t anina tasir (tahmin adimi)."""
        dt = t - self.t
        if dt <= 0:
            return
        p, v = self.x
        (a, b), (c, d) = self.P
        q = self.q
        # F = [[1, dt], [0, 1]];  Q = q * [[dt^3/3, dt^2/2], [dt^2/2, dt]]
        a2 = a + dt * (b + c) + dt * dt * d + q * dt ** 3 / 3.0
        b2 = b + dt * d + q * dt * dt / 2.0
        c2 = c + dt * d + q * dt * dt / 2.0
        d2 = d + q * dt
        self.x = [p + v * dt, v]
        self.P = [[a2, b2], [c2, d2]]
        self.t = t

    def guncelle(self, t, z):
        """Olcum: t aninda hedef z derecede goruldu. Doner: kabul edildi mi."""
        try:
            t, z = float(t), float(z)
        except (TypeError, ValueError):
            return False
        if not (math.isfinite(t) and math.isfinite(z)):
            return False
        # Kamera/decoder bazen eski bir kareyi gec teslim edebilir. Zamani geri
        # sararak guncellemek hiz kestirimini ters cevirir; eski olcum atilir.
        if self.t is not None and t < self.t - 1e-6:
            return False
        self.son_aykiri = False
        if self.x is None:
            self._ilk_olcum(t, z)
            return True
        self._ilerlet(t)
        (a, b), (c, d) = self.P
        s = a + self.r ** 2                    # yenilik varyansi (H = [1, 0])
        y = z - self.x[0]
        self.son_yenilik = y
        if y * y > (self.aykiri_esik ** 2) * s and self.olcum_sayisi >= 3:
            # Tek bir kotu kutu filtreden gecmemeli. Eski kod ilk aykirida filtreyi
            # TAM o kotu olcume sifirliyordu; sonuc tek karede buyuk motor komutuydu.
            # Ancak yeni hedef/ID gercekten baska yerdeyse ardisik olcumler birbirine
            # yakin gelir: aykiri_tekrar adet tutarli aykirida yeni konuma kurulur.
            self.son_aykiri = True
            if self._aykiri_aday is not None and abs(z - self._aykiri_aday) <= self.aykiri_yakinlik:
                self._aykiri_sayisi += 1
                self._aykiri_aday = 0.5 * (self._aykiri_aday + z)
            else:
                self._aykiri_aday = z
                self._aykiri_sayisi = 1
            if self._aykiri_sayisi >= self.aykiri_tekrar:
                yeni = self._aykiri_aday
                self._ilk_olcum(t, yeni)
                self.son_aykiri = True
            return False
        self._aykiri_aday = None
        self._aykiri_sayisi = 0
        if self.q_min is not None and self.q_max is not None:
            x = y * y / s
            # ASIMETRIK: manevra basladiginda HIZLI yukselir (gec uyum = hedefin gerisinde
            # kalmak), bitince YAVAS iner (tek gurultulu karede q sicramasin).
            a_ = self.nis_yukselis if x > self.nis else self.nis_inis
            self.nis = (1 - a_) * self.nis + a_ * x
            oran = min(1.0, max(0.0, (self.nis - self.nis_alt) / (self.nis_ust - self.nis_alt)))
            self.q = self.q_min + (self.q_max - self.q_min) * oran
        k0, k1 = a / s, c / s
        self.x = [self.x[0] + k0 * y, self.x[1] + k1 * y]
        if self.hiz_siniri is not None:
            self.x[1] = max(-self.hiz_siniri, min(self.hiz_siniri, self.x[1]))
        # Skaler olcum guncellemesi. Yuvarlama farkiyla P01/P10 ayrismasin diye
        # capraz terim simetriklenir; uzun canli kosuda kovaryans bozulmaz.
        p00 = max(1e-12, (1 - k0) * a)
        p01 = (1 - k0) * b
        p10 = c - k1 * a
        p11 = max(1e-12, d - k1 * b)
        capraz = 0.5 * (p01 + p10)
        self.P = [[p00, capraz], [capraz, p11]]
        self.t_olcum = t
        self.olcum_sayisi += 1
        return True

    def tahmin(self, t):
        """t anindaki aci tahmini. Durumu degistirmez."""
        if self.x is None:
            return None
        return self.x[0] + self.x[1] * max(0.0, float(t) - self.t)

    def kayip_sure(self, t):
        return float("inf") if self.t_olcum is None else max(0.0, float(t) - self.t_olcum)


class KalmanTakipKontrolu:
    """Kalman kestirimini guvenli ve yumusak MUTLAK tilt hedefine cevirir.

    Filtre tek basina motor kontrolcusu degildir. Ham ``kol + g*(hedef-kol)``
    komutu tek karede onlarca derece sicrabilir ve tespit gurultusunde yon degistirir.
    Bu katman dort kapinin tek sahibidir:

      * komut frekansi (seri hatti/model FPS'ini motor davranisindan ayirir),
      * derece/sn tabanli hedef ilerleme tavani,
      * kucuk komut ve yon-degisimi histerezisi,
      * tespit kaybinda sinirli sure ongoru, sonra kesin durus.

    Donanimdan bagimsizdir; ``olcum`` ve ``komut`` saf sayilarla test edilebilir.
    """

    def __init__(self, q=120.0, r=0.4, ileri=0.08, kazanc=0.85,
                 kayip_kovalamasi=0.45, komut_hz=25.0, azami_hiz=45.0,
                 min_komut=0.08, yon_histerezis=0.30, durus_hizi=1.5,
                 hedef_hiz_siniri=90.0):
        self.kestirici = HedefKestirici(q=q, r=r, hiz_siniri=hedef_hiz_siniri)
        self.ileri = max(0.0, float(ileri))
        self.kazanc = max(0.0, min(1.0, float(kazanc)))
        self.kayip_kovalamasi = max(0.0, float(kayip_kovalamasi))
        self.komut_periyodu = 1.0 / max(1.0, float(komut_hz))
        self.azami_hiz = max(0.1, float(azami_hiz))
        self.min_komut = max(0.0, float(min_komut))
        self.yon_histerezis = max(0.0, float(yon_histerezis))
        self.durus_hizi = max(0.0, float(durus_hizi))
        self.son_komut_t = None
        self.son_komut = None
        self.son_yon = 0
        self.son_tahmin = None

    @property
    def hazir(self):
        return self.kestirici.hazir

    @property
    def hiz(self):
        return self.kestirici.hiz

    def sifirla(self):
        self.kestirici.sifirla()
        self.son_komut_t = None
        self.son_komut = None
        self.son_yon = 0
        self.son_tahmin = None

    def olcum(self, t_kare, kol_kare, hata_px, ppd):
        if ppd is None or not math.isfinite(float(ppd)) or abs(float(ppd)) < 1e-6:
            return False
        z = olcum_acisi(kol_kare, hata_px, ppd)
        return self.kestirici.guncelle(t_kare, z)

    def komut(self, simdi, kol, hedef_var=False, hata_px=None, olu_px=None,
              alt=0.0, ust=60.0):
        """Yeni mutlak kol hedefi veya ``None`` dondurur."""
        simdi, kol = float(simdi), float(kol)
        kayip = self.kestirici.kayip_sure(simdi)
        if kayip > self.kayip_kovalamasi:
            # Eski hizla sonsuza kadar kadraj disina kosma. Yeni gercek olcum iki
            # karede filtreyi tekrar kurar; bu sirada mevcut konum korunur.
            self.sifirla()
            return None
        if not self.hazir:
            return None
        if hedef_var and hata_px is not None and olu_px is not None:
            if abs(float(hata_px)) <= float(olu_px) and abs(self.hiz) <= self.durus_hizi:
                self.son_yon = 0
                return None
        if self.son_komut_t is not None and simdi - self.son_komut_t < self.komut_periyodu:
            return None

        tahmin = self.kestirici.tahmin(simdi + self.ileri)
        self.son_tahmin = tahmin
        fark = self.kazanc * (tahmin - kol)
        if abs(fark) < self.min_komut:
            return None

        yon = 1 if fark > 0 else -1
        if self.son_yon and yon != self.son_yon and abs(fark) < self.yon_histerezis:
            return None

        # Ilk komutta da bir periyotluk hiz payi kullanilir; filtre ilk iki kareden
        # sonra birden 20 derece oteyi gosterse bile karta 20 derecelik hedef sicrama yok.
        dt = self.komut_periyodu if self.son_komut_t is None else min(
            0.20, max(self.komut_periyodu, simdi - self.son_komut_t))
        azami_adim = self.azami_hiz * dt
        fark = max(-azami_adim, min(azami_adim, fark))
        hedef = max(float(alt), min(float(ust), kol + fark))
        if self.son_komut is not None and abs(hedef - self.son_komut) < self.min_komut:
            return None

        self.son_komut_t = simdi
        self.son_komut = hedef
        self.son_yon = yon
        return hedef


BOSLUK_OGRENME_TAVANI = 1.0      # derece — calisirken ogrenilen boslugun ust siniri

# SAHA AYARI (24.09, "uzakta akiskan ama yakinda titriyor; titremeyi cozunce uzak takilir").
# Sahada (19:42 oturumu) yakinda (balon 40+ px) namlu duran balona saniyede 1.5-3.8 kez
# yon degistiriyordu; kayittan hesaplanan hedef dunya acisi 21.0 +- 0.3 derece SABITTI —
# salinimi kontrolcu uretiyordu. Iki kok neden:
#   1. Tek sabit ayar: kutu merkezinin kare-kare gurultusu balon boyunun ~%10'u (kayit,
#      15.5 bin olcum: 20 px'te 2.5 px, 97 px'te 8-11, kuyrukta 31). Uzaga gore ayarli
#      esikler yakinda gurultuyu "manevra" sayiyor, hiz ileri beslemesi onu motora
#      tasiyordu. -> olcek_ref_px: balon 24 px'ten buyukse gurultu, hiz esikleri, olu
#      bantlar ve filtre ivme gurultusu boyla olceklenir; uzakta ayar AYNEN kalir.
#   2. Tek kayip karede DUR: kare -> karar ~0.15 sn (kayit: t_gonder - t_kare 0.11-0.14 +
#      pozlama), esik 0.10 idi -> her kacirilan karede namlu durup yeniden kalkiyordu
#      (yakinda gorulme %56-83). -> kayip_dur_s 0.35 (~0.2 sn gercek bosluk); kisa
#      boslukta duran/tutulan hedefte namlu yerinde bekler, hareketlide tahminle surer.
# Kapali cevrim benzetim (kartin yorunge kopyasi, 0.15 sn gecikme, 17 Hz cikarim, boyla
# buyuyen kuyruklu gurultu, %20 kayip kare; 11 senaryo x 5 tohum), eski -> yeni:
#   yakin 90 px duran: yon degisimi 4.7 -> 1.3/sn, nisan balonun ic yarisinda %53 -> %83
#   cok yakin 130 px: 5.0 -> 1.3/sn, %49 -> %82 | yakin yuruyen 70 px: %39 -> %46
#   uzak yuruyen 20 px: hata 13 -> 5.7 px, %13 -> %43 | uzak duran 18 px: %88 -> %85
# Denenip ELENENLER (benzetimde yakinda az fayda, uzakta zarar): olcum gurultusunu yalniz
# boyla olceklemek (esikler sabit), kip gecisinde filtreyi sabit tutmak, bosluk tarafina
# histerezis, olu bolge kararini filtreli hatayla vermek.
SAHA_AYARI = dict(olcek_ref_px=24.0, kayip_dur_s=0.35, kayipta_tut=True)

# ATES KORLUGU (EksenTakip.korluk): lazer altinda hedefin yolu son KOR_GECMIS_S sn'lik
# olcumlere uydurulan dogrudur. Egim KOR_DURAN_HIZ x s der/sn'nin ya da kendi belirsizliginin
# KOR_GUVEN katinin altindaysa hedef duruyor sayilir. Benzetim taramasi (24 tohum): 1.0 sn'lik
# pencerede duran balonun namlu oturmasindan gelen sahte 0.35 der/sn egim namluyu kosturdu
# (13 px duran %88 -> %82); 1.5 sn'de %87. Esik 0.4'e cikinca 0.3 der/sn kayan balon %83 -> %42.
KOR_GECMIS_S = 1.5
KOR_DURAN_HIZ = 0.2
KOR_GUVEN = 3.0


class EksenTakip:
    """TEK eksenin surekli takip kontrolcusu (pan veya tilt) — arayuzun otonom yolu.

    SAHADA GORULEN (21.09, iki eksenli ilk takip): iki eksende de titreme, yatayda
    yavaslik. Kok neden PD + mesgul kapisi zinciriydi: her kare kucuk bir ADIM
    uretiyor, motor adimi bitirip DURUYOR, bayat kareye bakilip yeni adim atiliyordu
    (40 sn'de 271 ayri tilt hedefi, %25 hareket, 56 dur-kalk). Kutu merkezinin kendi
    gurultusu ise kucuktu (motor dururken kareden kareye medyan 1.5 px).

    Bu sinif hedefin DUNYA acisini izler ve karta DOGRUDAN o aciyi (+ kisa ongoru)
    MUTLAK hedef olarak verir:

        z      = eksen_acisi(t_kare) + isaret * hata_px / ppd      (kare aninin acisi!)
        komut  = z_filtre + hiz * ileri                             (hedef hareketliyse)

    Hareket halindeki hedefte karta 25 Hz'de yeni hedef gider; firmware
    (MotionCore/PanCore retarget) DURMADAN yeni hedefe gecer — motor surekli akar.
    KalmanTakipKontrolu'ndan FARKI: hedef, kolun o anki acisinin bir periyotluk hiz
    payi otesine KIRPILMAZ. O kirpma, hedefi hep 1-2 derece ileride tutup motoru
    tepe hiza hic cikarmiyor, ivme-fren-ivme dongusune sokuyordu. Hiz ve ivme
    sinirini firmware zaten uyguluyor.

    DISLI BOSLUGU (~1 derece): kartin bildirdigi aci DARBE SAYIMIDIR; namlu, motorun
    hareket yonunde bosluk/2 kadar GERIDE durur. Telafi edilmezse (benzetimde olculdu)
      * yon her degistiginde olcum bosluk kadar sicrar, kontrolcu bunu hedef hareketi
        sanip ~3.5 derecelik surekli ileri-geri salinima girer,
      * duran hedefte bosluk/2 kadar (12 px/der'de ~6 px) kalici sapma kalir.
    Bu yuzden: namlu = aci - yon*bosluk/2 (olcumde) ve motor = namlu_hedefi +
    yon*bosluk/2 (komutta). Ek kapilar:
      * olu bant: namlu hedefi son hedefe `olu` dereceden yakinsa yeni komut YOK,
      * yon histerezisi: son hareketin TERSI yonunde `bosluk`tan kucuk duzeltme yutulur.
    """

    def __init__(self, isaret=1.0, q=40.0, r=0.6, ileri=0.05, komut_hz=25.0,
                 olu=0.5, bosluk=1.5, telafi=0.5, durus_hizi=3.0, kayip_kovalamasi=0.45,
                 azami_sicrama=25.0, hedef_hiz_siniri=120.0, yor_q=800.0, yor_r=0.3,
                 yor_q_min=60.0, yor_hiz_tavan=45.0, yor_ff_dusuk=0.5, yor_ff_esik=0.3,
                 yor_ff_pencere=0.6, kayip_dur_s=0.10, olcek_ref_px=None,
                 kayipta_tut=False):
        self.isaret = 1.0 if isaret >= 0 else -1.0
        # YAKIN/UZAK DENGESI (24.09 saha) — arayuz SAHA_AYARI ile kurar; bkz. SAHA_AYARI.
        # kayip_dur_s: son olcumun KARE aninden bu kadar sonra hala tespit yoksa dur.
        #   Kare -> karar ~0.15 sn surer; 0.10 her TEK kayip karede namluyu durduruyordu.
        self.kayip_dur_s = max(0.0, float(kayip_dur_s))
        # olcek_ref_px: BOYA GORE OLCEKLEME. Balon bu boydan (px) buyukse s = boy/ref;
        #   olcum gurultusu x s, hiz esikleri x s, olu bantlar x s, filtre ivme gurultusu
        #   x s^2. Kucuk (uzak) balonda ayar AYNEN kalir; yakindaki davranis uzaktakinin
        #   balon boyuna gore olceklenmis hali olur (acisal boy, hiz ve kutu gurultusu
        #   mesafeyle birlikte olceklenir).
        self.olcek_ref_px = None if not olcek_ref_px else float(olcek_ref_px)
        self._s = 1.0
        # kayipta_tut: kisa tespit boslugunda (kayip_dur_s dolmadan) namlu duran/tutulan
        #   hedefte YERINDE bekler (yeni komut yok); hareketli hedefte tahminle devam eder.
        self.kayipta_tut = bool(kayipta_tut)
        self.yor_hiz_tavan = max(1.0, float(yor_hiz_tavan))
        # UYARLAMALI HIZ ILERI BESLEMESI (bkz. _ileri_besleme_orani). Tespit karenin
        # cekilisinden ~130 ms (kotu durumda ~230 ms) sonra kontrolcuye ulasir, kart da
        # son komutu 150 ms akitir. Hedef durunca/donunce namlu eski hizla gitmeye
        # devam eder: benzetimde 10 der/sn'den duran hedefi 2.0, 20'den 3.5 derece
        # asiyordu (sahada "cok fazla iniyor, sonra cikiyor"). Sabit hizla giden
        # (rayda) hedefte tam besleme gerekir: sabit %50 besleme orada hatayi
        # 1.7 -> 13 px buyuttu. Hedef acilari son `yor_ff_pencere` sn'de bir DOGRUYA
        # oturuyorsa (artik < `yor_ff_esik` derece) tam, oturmuyorsa `yor_ff_dusuk`.
        self.yor_ff_dusuk = max(0.0, min(1.0, float(yor_ff_dusuk)))
        self.yor_ff_esik = max(0.0, float(yor_ff_esik))
        self.yor_ff_pencere = max(0.1, float(yor_ff_pencere))
        self.kestirici = HedefKestirici(q=q, r=r, hiz_siniri=hedef_hiz_siniri)
        # Kip basina filtre ayari. Yorunge kipi hizi DOGRUDAN motora ileri besleme
        # olarak verir: hiz kestirimi hedefin hiz degisimine hizli uymali (benzetim:
        # q=40/r=0.6'da yon degistiren hedefte 7.7 px, q=300/r=0.3'te 4.0 px; hareket
        # yine konum kipinden 5-7 kat yumusak). Konum kipi eski ayariyla kalir.
        self._konum_qr = (float(q), float(r))
        self._yor_qr = (float(yor_q), float(yor_r))
        # yor_q_min verilirse yorunge kipinde q, [yor_q_min, yor_q] arasinda adaptive.
        # 60..800 (benzetim, 5 tohum ort.): el titremeli duran hedefte yon degisimi 23->11,
        # ort ivme 72->24; rayda sabit hizda ivme 30->17; bedeli akici el hareketinde
        # +1.8 px, hizli sinuste +3.5 px. Sabit q=300 ya titremeyi izliyor ya geride kaliyordu.
        # 22.09 aksam: SAHADAKI GERCEK el hareketi (loglardan cikarilan hedef yolu, tepe
        # 30-60 der/sn, keskin donusler) benzetime girdi: 60..800 donuslerde geride
        # kaliyordu (medyan 22.4 px, %95 101 px). Ust sinir 1200-5000 + hizli manevra
        # algilama 19.4-21.6 px verdi AMA kaba geri bildirimli sahte kartta (kapi testi)
        # hedef cevresinde +-1 derece salinima girdi -> kararlilik payi icin 800'de
        # KALDI. Kazanc kucuk; kalan hatanin asil kaynagi ~60-80 ms toplam gecikme
        # (kamera 40 ms + model + seri) ve elin 30-60 der/sn keskin donusleri.
        self._yor_q_min = None if yor_q_min is None else float(yor_q_min)
        self.ileri = max(0.0, float(ileri))
        self.komut_periyodu = 1.0 / max(1.0, float(komut_hz))
        self.olu = max(0.0, float(olu))
        self.bosluk = max(0.0, float(bosluk))
        # Telafi edilen bosluk = telafi x bosluk. Tamami (1.0) degil: gercek bosluk
        # sanilandan KUCUKSE fazla telafi namluyu hedefin otesine iter ve duran hedefte
        # surekli ileri-geri (benzetim: 0.3 derece gercek boslukta 74 yon degisimi).
        # Eksik telafi yalniz kucuk bir kalici sapma birakir; o da olu bantta kalir.
        self.telafi = max(0.0, min(1.0, float(telafi)))
        self.durus_hizi = max(0.0, float(durus_hizi))
        self.kayip_kovalamasi = max(0.0, float(kayip_kovalamasi))
        self.azami_sicrama = max(0.5, float(azami_sicrama))
        self._yor_kipinde = False                   # filtre su an yorunge ayarinda mi
        self.kor_bitis = None                       # bkz. korluk(); hedefe degil lazere ait
        self.sifirla()

    def korluk(self, bitis_t):
        """ATES KORLUGU (24.09 saha): lazer noktasi balona degince model balonu goremez
        (21:27 kaydi: uzak balonda her atistan 3 kare sonra). `bitis_t` anina kadar olcum
        gelmemesi KAYIP sayilmaz; namlu hedefin son KOR_GECMIS_S'lik yoluna uydurulan
        dogruyu izler (bkz. _kor_komut). None: kapali. Arayuz yalniz gercek lazerle ates
        surerken (+ kameranin noktayi gostermeye devam ettigi pay) acar."""
        self.kor_bitis = None if bitis_t is None else float(bitis_t)
        self._kor_dogru = None

    def _korde(self, simdi, hata_px):
        return hata_px is None and self.kor_bitis is not None and simdi < self.kor_bitis

    def _kor_komut(self, simdi, aci, alt, ust, pay):
        """Korlukte (lazer altinda) yorunge: hedefin son olcumlerine en kucuk karelerle
        uydurulan DOGRU. Kalman'in anlik hizi degil: yavas (0.3-1 der/sn) kayan uzak balon
        "duran hedef" kipinde kalir ve namlu bekler, balon ~0.4 sn'de noktanin altindan kayar
        (Kalman tahminiyle devam benzetimde yavasta hic fark etmedi).
        Kapali cevrim benzetim (kart yorunge kopyasi, 2 sn kor ates, 24 tohum; ates boyunca
        namlu balonun UZERINDE, korluk kapali -> acik): 13 px 0.3 der/sn %35 -> %83,
        0.5 der/sn %11 -> %89, 15 px 1 der/sn %19 -> %88, 25 px 2 der/sn %23 -> %92,
        30 px 4 der/sn %21 -> %93, 18 px capraz %13 -> %95; duran 13 px %88 -> %87,
        20 px %85 -> %99; elde hafif sallanan 90 px %92 -> %97. 3 derece savrulan el
        %15 -> %9: kor iken izlenemez. Egim anlamli degilse duran/tutulan hedefte namlu
        bekler, degilse olcumlerin ortalamasina gider."""
        if self._kor_dogru is None:
            self._kor_dogru = self._dogru_uydur()
        t0, z0, v = self._kor_dogru
        if not v and (self._duragan or self._tut is not None):
            return None                             # duran balon: namlu yerinde bekler
        hedef = z0 + v * (simdi - t0)
        namlu = aci - self._ofset()
        hedef = max(namlu - self.azami_sicrama, min(namlu + self.azami_sicrama, hedef))
        if v:
            self._yor_yon = 1 if v > 0 else -1
        elif not self._yor_yon:
            self._yor_yon = 1 if hedef > namlu else -1
        motor = hedef + self._yor_yon * self.bosluk_kest * 0.5
        hiz = max(-self.yor_hiz_tavan, min(self.yor_hiz_tavan, v))
        if motor >= ust:
            motor, hiz = float(ust), min(0.0, hiz)
        elif motor <= alt:
            motor, hiz = float(alt), max(0.0, hiz)
        self.son_komut, self.son_komut_t = hedef, simdi
        return self._yorunge_sinirla(motor, hiz, alt, ust, pay)

    def _dogru_uydur(self):
        """(t0, z0, hiz): son olcumlere uydurulan dogru, t0 = son olcum ani. Egim anlamli
        degilse (KOR_DURAN_HIZ x s ya da egim belirsizliginin KOR_GUVEN kati altinda) hiz 0
        ve konum olcumlerin ortalamasi: kuyruklu kutu gurultusunun sahte egimiyle 2 sn kosmak
        duran balonda namluyu balondan cikariyordu (benzetim, 40 tohum, 20 px duran: anlamlilik
        testiyle %91 -> %97; bedeli 0.3 der/sn kayanda %83 -> %80). Olcum azsa Kalman durumu."""
        z = self._kor_gecmisi
        if len(z) >= 4 and z[-1][0] - z[0][0] >= 0.3:
            n = float(len(z))
            tm = sum(a for a, _ in z) / n
            zm = sum(b for _, b in z) / n
            sxx = sum((a - tm) ** 2 for a, _ in z)
            v = sum((a - tm) * (b - zm) for a, b in z) / sxx
            artik = sum((b - zm - v * (a - tm)) ** 2 for a, b in z) / max(1.0, n - 2)
            if abs(v) < max(KOR_DURAN_HIZ * self._s, KOR_GUVEN * (artik / sxx) ** 0.5):
                return z[-1][0], zm, 0.0
            t0 = z[-1][0]
            return t0, zm + v * (t0 - tm), v
        k = self.kestirici
        return k.t, k.x[0], k.x[1]

    def sifirla(self):
        self.kestirici.sifirla()
        self.son_komut = None
        self.son_komut_t = None
        self.son_yon = 0
        self.son_tahmin = None
        self._son_aci = None
        self._hareket_yon = 0
        self._yon_gecmisi = [(float("-inf"), 0)]    # [(t, yon)] — yon degisim anlari
        self._namlu = None                          # bosluk modelindeki namlu acisi
        self._motor = None                          # son bildirilen motor acisi
        self._ofset_gecmisi = [(float("-inf"), 0.0)]  # [(t, motor - namlu)]
        self._son_hareket_t = float("-inf")         # aci en son ne zaman degisti
        self._son_kare = None                       # (t_kare, hata_px, ppd)
        # CALISIRKEN OGRENILEN BOSLUK (derece). Baslangic bosluk x telafi. Yerlesme
        # duzeltmesi ters yonde yapildiginda sonraki yerlesmis kare sonucu gosterir:
        # namlu hedefi ASTIYSA bosluk sanildigindan kucuk, EKSIK KALDIYSA buyuk.
        # Sabit tahmin gercekten buyukse duran hedefte surekli ping-pong olur
        # (benzetim: gercek bosluk 0 iken 55 yon degisimi).
        self.bosluk_kest = self.bosluk * self.telafi
        self._ters_duzeltme = 0                     # son yerlesme ters yondeyse o yon
        self._tut = None                            # yorunge kipi: durulan motor acisi
        self._yor_yon = 0                           # yorunge kipi: bosluk tarafi (histerezisli)
        self._duragan = True                        # yorunge kipi: hedef duruyor mu (histerezisli)
        self._yavas_t = None                        # hiz esigin altina ne zaman indi
        self._hiz_gecmisi = []                      # [(t_kare, hiz)] — son ~1 sn
        self._z_gecmisi = []                        # [(t_kare, hedef acisi)] — ileri besleme
        self._kor_gecmisi = []                      # [(t_kare, hedef acisi)] — korluk dogrusu
        self._kor_dogru = None                      # (t0, z0, hiz) — bu kor aralikta
        self._kayip_durdu = False                   # kayipta tek hiz-sifir komutu

    def _ileri_besleme_orani(self):
        """Hiz ileri beslemesinin carpani: 1.0 ya da yor_ff_dusuk.

        Son pencerede olculen hedef acilarina dogru uydurulur. Artik kucuk ve egim
        belirginse hedef SABIT HIZLA gidiyor (rayda) -> tam besleme. Artik buyukse
        (durus, donus, el hareketi) ya da olcum azsa -> dusuk besleme: gecikme
        yuzunden eski hizla hedefi asmasin."""
        z = self._z_gecmisi
        if len(z) < 6:
            return self.yor_ff_dusuk
        n = float(len(z))
        tm = sum(a for a, _ in z) / n
        zm = sum(b for _, b in z) / n
        sxx = sum((a - tm) ** 2 for a, _ in z)
        if sxx < 1e-6:
            return self.yor_ff_dusuk
        egim = sum((a - tm) * (b - zm) for a, b in z) / sxx
        artik = (sum((b - zm - egim * (a - tm)) ** 2 for a, b in z) / n) ** 0.5
        return 1.0 if (artik < self.yor_ff_esik * self._s and abs(egim) > 1.0 * self._s) else self.yor_ff_dusuk

    def hedef_degisti(self):
        """Kilit BASKA bir nesneye gecti: hedef kestirimi sifirdan kurulur.

        Iki farkli nesnenin konum farki "hiz" sanilmamali. 23.09 arayuz kaydi: kilit
        dustu, 213 px otedeki kutu ayni filtreye girdi, pan'a 62 der/sn komut gitti.
        Bosluk modeli (namlu/motor gecmisi, ogrenilen bosluk) MEKANIZMAYA aittir,
        hedefe degil — korunur."""
        self.kestirici.sifirla()
        self.son_komut = None
        self.son_komut_t = None
        self.son_yon = 0
        self.son_tahmin = None
        self._son_kare = None
        self._tut = None
        self._yor_yon = 0
        self._duragan = True
        self._yavas_t = None
        self._hiz_gecmisi = []
        self._z_gecmisi = []
        self._kor_gecmisi = []
        self._kor_dogru = None
        self.kor_bitis = None          # lazer eski hedefteydi; arayuz kilit degisince ateşi keser
        self._kayip_durdu = False

    @property
    def hazir(self):
        return self.kestirici.hazir

    def _kip_ayari(self, yorunge):
        k = self.kestirici
        s = self._s
        if yorunge:
            if not self._yor_kipinde:                            # kipe (yeniden) giris
                k.q = self._yor_qr[0] * s * s
                self._yor_kipinde = True
            if self._yor_q_min is not None:
                k.q_min, k.q_max = self._yor_q_min * s * s, self._yor_qr[0] * s * s
                k.q = min(k.q_max, max(k.q_min, k.q))
            else:
                k.q_min = k.q_max = None
            k.r = self._yor_qr[1] * s
        else:
            k.q, k.r = self._konum_qr[0] * s * s, self._konum_qr[1] * s
            k.q_min = k.q_max = None
            self._yor_kipinde = False

    def _ofset(self, t=None):
        """Motor sayimi - namlu (derece) `t` aninda. Olcumde KARE ANININ degeri
        kullanilir (hattaki eski kareler eski konumda cekildi).

        ⚠ BOSLUK = "PLAY" MODELI, basamak DEGIL. Eski model ofseti yon * bosluk/2 diye
        hesapliyordu: motor yon degistirdigi AN ofset bir uctan obur uca SICRIYORDU.
        Gercekte namlu sicramaz — motor once boslugu kapatir, namlu o sure YERINDE
        bekler. Sahte sicrama Kalman'a "hedef bosluk kadar kaydi" diye giriyor, hiz
        kestirimi firliyor, yorunge kipi motoru o hizla surup yonu yine ceviriyordu:
        KENDINI BESLEYEN SALINIM. 23.09 benzetim (1.5 px tespit gurultusu, duran
        hedef): tilt 18 kosunun 9'unda ~2.6 derece tepe-tepe sonmeyen salinim; sahada
        da tilt salinimi goruldu. Play modelinde ofset surekli degisir: namlu motorun
        +-bosluk/2 bandinda kalir, yalniz bandin kenari onu ittiginde hareket eder."""
        if t is None:
            return 0.0 if self._namlu is None else self._motor - self._namlu
        for t_o, o in reversed(self._ofset_gecmisi):
            if t_o <= t:
                return o
        return 0.0

    def _bosluk_guncelle(self, aci, t):
        """Play operatoru: namlu, motorun +-bosluk/2 bandinin icinde kalir."""
        yari = self.bosluk_kest * 0.5
        if self._namlu is None:
            self._namlu = aci            # hangi tarafa dayali oldugu bilinmiyor: ortada
        self._motor = aci
        self._namlu = min(max(self._namlu, aci - yari), aci + yari)
        if t is not None:
            o = aci - self._namlu
            if abs(o - self._ofset_gecmisi[-1][1]) > 1e-6:
                self._ofset_gecmisi.append((float(t), o))
                del self._ofset_gecmisi[:-200]

    def aci_bildir(self, aci, t=None):
        """Eksenin bildirilen acisini izler; son hareket YONUNU ve bosluk modelindeki
        namlu acisini tutar."""
        if aci is None:
            return
        aci = float(aci)
        self._bosluk_guncelle(aci, t)
        if self._son_aci is None:
            self._son_aci = aci
        elif abs(aci - self._son_aci) > 0.02:
            if t is not None:
                self._son_hareket_t = float(t)
            yon = 1 if aci > self._son_aci else -1
            if yon != self._hareket_yon and t is not None:
                self._yon_gecmisi.append((float(t), yon))
                del self._yon_gecmisi[:-20]
            self._hareket_yon = yon
            self._son_aci = aci

    def olcum(self, t_kare, aci_kare, hata_px, ppd, boy_px=None):
        """Kare `t_kare`de cekildi; eksen o an `aci_kare`deydi; hedef merkezden
        `hata_px` uzakta; hedef kutusu `boy_px` buyuklugunde (varsa olcum gurultusu
        boyla olceklenir). Doner: olcum kabul edildi mi."""
        if aci_kare is None or hata_px is None or not ppd:
            return False
        if self.olcek_ref_px and boy_px:
            self._s = max(1.0, float(boy_px) / self.olcek_ref_px)
            self._kip_ayari(self._yor_kipinde)            # r / q sinirlari yeni boya gore
        z = float(aci_kare) - self._ofset(t_kare) + self.isaret * float(hata_px) / float(ppd)
        self._son_kare = (float(t_kare), float(hata_px), float(ppd))
        kabul = self.kestirici.guncelle(t_kare, z)
        if kabul:
            self._z_gecmisi.append((float(t_kare), z))
            while self._z_gecmisi and self._z_gecmisi[0][0] < t_kare - self.yor_ff_pencere:
                self._z_gecmisi.pop(0)
            self._kor_gecmisi.append((float(t_kare), z))
            while self._kor_gecmisi and self._kor_gecmisi[0][0] < t_kare - KOR_GECMIS_S:
                self._kor_gecmisi.pop(0)
            self._kor_dogru = None                  # yeni kor aralik yeni dogru
            self._kayip_durdu = False
            self._hiz_gecmisi.append((float(t_kare), self.kestirici.hiz))
            while self._hiz_gecmisi and self._hiz_gecmisi[0][0] < t_kare - 1.0:
                self._hiz_gecmisi.pop(0)
        return kabul

    def _ort_hiz(self, simdi, pencere):
        """Son `pencere` saniyedeki hiz kestirimlerinin ortalamasi (yoksa anlik hiz)."""
        v = [h for t, h in self._hiz_gecmisi if t >= simdi - pencere]
        return sum(v) / len(v) if v else self.kestirici.hiz

    def komut(self, simdi, aci, alt, ust, olu=None, hata_px=None, olu_px=None):
        """Yeni MUTLAK eksen hedefi ya da None (komut gerekmez).

        `aci`: eksenin su anki (kartin bildirdigi) acisi. `olu`: bu kare icin olu bant
        (derece) — verilmezse sinifin varsayilani (kutuya oranli olu bolgeyi arayuz verir).
        `hata_px`/`olu_px`: son karede GOZLENEN hata ve olu bolge. Duran hedef gorunurde
        zaten olu bolgedeyse hicbir model hesabina bakilmadan komut verilmez: bosluk,
        ppd veya gecikme modeli ne kadar yanlis olursa olsun yerlesmis namlu kipirdamaz."""
        if aci is None:
            return None
        self._kip_ayari(False)
        simdi, aci = float(simdi), float(aci)
        self.aci_bildir(aci, simdi)
        if self.kestirici.kayip_sure(simdi) > self.kayip_kovalamasi and not self._korde(simdi, hata_px):
            # Uzun kayipta eski hizla kadraj disina kosma: filtreyi birak, eksen
            # son hedefinde kalir. Yeni gercek olcum iki karede filtreyi yeniden kurar.
            if self.kestirici.baslatildi:
                self.sifirla()
            return None
        if not self.hazir:
            return None
        if self.son_komut_t is not None and simdi - self.son_komut_t < self.komut_periyodu:
            return None
        hiz = self.kestirici.hiz
        if (hata_px is not None and olu_px is not None and abs(float(hata_px)) <= float(olu_px)
                and abs(hiz) <= self.durus_hizi * self._s):
            return None
        # YERLESME DUZELTMESI: hedef duruyor, motor durduktan SONRA cekilmis bir kare
        # hala olu bolge disini gosteriyor. Bu kare bayat degil (hareket bitmisti), yani
        # hata dogrudan uygulanabilir — ters yonde olsa bile (histerezis bosluk
        # salinimi icindir; yerlesmis namluda salinim yok). Model hatalarinin (bosluk,
        # ppd) biraktigi kalici sapmayi bu kapatir.
        kare = self._son_kare
        if (kare is not None and olu_px is not None and abs(hiz) <= self.durus_hizi * self._s
                and kare[0] > self._son_hareket_t + 0.03 and abs(kare[1]) > float(olu_px)
                and (self.son_komut_t is None or kare[0] > self.son_komut_t)):
            # 0.8: ppd sanilandan buyukse (goruntu dereceye daha cok kayiyorsa) tam
            # duzeltme hedefi asar ve ters duzeltme dogurur; eksik kalan kisim bir
            # sonraki yerlesmis karede tamamlanir.
            e = 0.8 * self.isaret * kare[1] / kare[2]    # namlunun gitmesi gereken (der)
            yon_namlu = 1 if e > 0 else -1
            if self._ters_duzeltme:
                # Onceki ters duzeltmenin sonucu: ayni yone devam gerekiyorsa eksik
                # kalmis (bosluk buyuk), geri donmek gerekiyorsa asmis (bosluk kucuk).
                if yon_namlu == self._ters_duzeltme:
                    # TAVAN 1.0 derece (eskiden 3.0). Sahada olculen bosluk tilt
                    # 0.1-0.9, pan 0.2-0.7. 23.09 benzetim: bosluk kestirimi 0.75'e
                    # cikinca yorunge kipinde duran hedefte salinim basliyor (8 kosunun
                    # 6'si, eski kod); ogrenmenin kendini o bolgeye tasimasi engellenir.
                    self.bosluk_kest = min(BOSLUK_OGRENME_TAVANI, self.bosluk_kest + 0.5 * abs(e))
                else:
                    self.bosluk_kest = max(0.0, self.bosluk_kest - abs(e))
                self._ters_duzeltme = 0
            if self._hareket_yon and yon_namlu != self._hareket_yon:
                self._ters_duzeltme = yon_namlu
            namlu = aci - self._ofset()
            hedef = namlu + e
            motor = max(float(alt), min(float(ust),
                                        hedef + yon_namlu * self.bosluk_kest * 0.5))
            self.son_komut, self.son_komut_t, self.son_yon = hedef, simdi, yon_namlu
            self.son_tahmin = hedef
            return motor
        tahmin = self.kestirici.tahmin(simdi)
        # Duran hedefte hiz kestirimi yalniz gurultudur; onu ileri tasimak namluyu
        # titretir. Ongoru yalniz gercekten hareket eden hedefe uygulanir.
        if abs(hiz) > self.durus_hizi * self._s:
            tahmin += hiz * self.ileri
        self.son_tahmin = tahmin
        namlu = aci - self._ofset()
        hedef = max(namlu - self.azami_sicrama, min(namlu + self.azami_sicrama, tahmin))
        referans = namlu if self.son_komut is None else self.son_komut
        fark = hedef - referans
        olu = self.olu * self._s if olu is None else max(self.olu * self._s, float(olu))
        if abs(fark) < olu:
            return None
        yon = 1 if fark > 0 else -1
        if self.son_yon and yon != self.son_yon and abs(fark) < max(olu, self.bosluk):
            return None
        # Motor, namlunun gidecegi yone bosluk/2 FAZLA gider (bosluk o yonde kapanir).
        yon_namlu = 1 if hedef > namlu else -1
        motor = max(float(alt), min(float(ust),
                                        hedef + yon_namlu * self.bosluk_kest * 0.5))
        self._ters_duzeltme = 0          # model komutu: ogrenme orneklemi degil
        self.son_komut, self.son_komut_t, self.son_yon = hedef, simdi, yon
        return motor


    @staticmethod
    def _yorunge_sinirla(konum, hiz, alt, ust, pay=None):
        """Yorunge ucunun gelecek 250 ms'de yazilim sinirini asmamasini sagla.

        Kart referansi 150 ms hizla akip ardindan ivmeyle durur; yalniz konumu
        kirpmak yeterli degildir. Fiziksel fren mesafesi icin sinirdan 1.5° pay
        birakilir. Bu yumusak sinir, kartin donanimsal sonlandirmasi DEGILDIR.
        """
        alt, ust = float(alt), float(ust)
        # `pay` verilmezse 1.5 birim (eksenin kendi biriminde). ⚠ Tilt KAMERA acisinda
        # izlenir; kolun ust bolgesinde kamera kol derecesi basina ~0.3 derece doner,
        # 1.5 kamera derecesi ~5 KOL derecesi eder (23.09: tavan +25 yerine +19.8'de
        # kaldi). Arayuz payi kol acisinda kendisi hesaplayip burada 0 verir.
        pay = min(1.5, max(0.0, (ust - alt) * 0.15)) if pay is None else max(0.0, float(pay))
        ic_alt, ic_ust = alt + pay, ust - pay
        konum = max(ic_alt, min(ic_ust, float(konum)))
        hiz = max((ic_alt - konum) / 0.25,
                  min((ic_ust - konum) / 0.25, float(hiz)))
        return konum, hiz


    def yorunge_komut(self, simdi, aci, alt, ust, hata_px=None, olu_px=None, pay=None):
        """YORUNGE KIPI cikisi: (motor_konumu, hiz) ya da None.

        Konum kipindeki `komut`tan farki: karta "su aciya git" degil, "hedef SU AN burada
        ve bu HIZLA gidiyor" denir; kart referansi kendisi ilerletir ve motoru o hizda
        AKITIR (firmware yorunge_core.h). Sahadaki dur-kalk/titremenin kaynagi olan uc sey
        burada yok:
          * varis ani yok  -> motor her guncellemede durmuyor,
          * hiz ongorusu YAVAS hedefte de acik (konum kipinde durus_hizi altinda kapaliydi
            ve hedef 0.5 derecelik adimlarla izleniyordu),
          * ortalanmis duran hedefte konum SABITLENIR, hiz 0 (kart yumusakca durur).
        None: bu cagrida gonderilecek bir sey yok. Kart son komutu 150 ms ilerletmeye
        devam eder, sonra yumusakca durur — hedef kaybinda istenen davranis da budur.
        """
        if aci is None:
            return None
        self._kip_ayari(True)
        simdi, aci = float(simdi), float(aci)
        self.aci_bildir(aci, simdi)
        kayip_sure = self.kestirici.kayip_sure(simdi)
        kor = self._korde(simdi, hata_px)            # lazer altinda gorunmemek kayip degil
        if hata_px is None and kayip_sure >= self.kayip_dur_s and not self._kayip_durdu and not kor:
            # Son hizli komut firmware'de 150 ms daha akar. Hedef uc kare kadar
            # gorunmediyse eski hizi sifirla; belirsiz bolgeye tahminle kosma.
            self._kayip_durdu = True
            self._tut = max(float(alt), min(float(ust), aci))
            self.son_komut_t = simdi
            return self._yorunge_sinirla(self._tut, 0.0, alt, ust, pay)
        if self._kayip_durdu:
            return None
        if kayip_sure > self.kayip_kovalamasi and not kor:
            if self.kestirici.baslatildi:
                self.sifirla()
            return None
        if not self.hazir:
            return None
        if self.son_komut_t is not None and simdi - self.son_komut_t < self.komut_periyodu:
            return None
        if kor:
            return self._kor_komut(simdi, aci, alt, ust, pay)
        if self.kayipta_tut and hata_px is None and (self._duragan or self._tut is not None):
            return None                    # kisa bosluk, duran hedef: namlu yerinde bekler
        hiz = self.kestirici.hiz
        # DURAN HEDEF -> konum kipinin mantigi (yon histerezisi, yerlesme duzeltmesi,
        # ogrenilen bosluk), karta hiz 0 ile. Sahada (22.09, yere konmus drone) yalniz
        # yorunge mantigi pan'da +-0.35 derece ileri-geri yapti: gurultu bosluk tarafini
        # surekli degistiriyordu; konum kipi ayni hedefte hic kipirdamadi. Histerezis
        # (1 -> 2 der/sn) ve 0.4 sn bekleme: elde tasinan hedef yon degistirirken hizi
        # bir an sifirdan gecer; beklemesiz gecis orada kip degistirip hareketi
        # sarsiyordu (benzetim: el hareketinde ort ivme 51 -> 174).
        #
        # ⚠ ANLIK hiz degil, kisa pencere ORTALAMASI. 23.09 benzetim (1.5 px tespit
        # gurultusu, duran hedef, operator -15): hiz kestirimi ~0.2 sn periyotla +-5
        # der/sn salliyordu — namlunun kendi salinimi (bosluk modeli ile gercek arasindaki
        # fark hiz ileri beslemesiyle buyuyor). Anlik |hiz| 1'in altina HIC inmedigi icin
        # duran hedef kipine gecilemiyor, salinim sonmuyordu. Salinimin ortalamasi
        # sifirdir; gercekten hareket eden hedefin hizi ayni isarette kalir.
        v_uzun, v_kisa = self._ort_hiz(simdi, 0.5), self._ort_hiz(simdi, 0.2)
        if abs(v_uzun) >= 1.0 * self._s:
            self._yavas_t = None
        elif self._yavas_t is None:
            self._yavas_t = simdi
        if self._duragan and abs(v_kisa) > 2.0 * self._s:
            self._duragan = False
        elif (not self._duragan and self._yavas_t is not None
              and simdi - self._yavas_t >= 0.4):
            self._duragan = True
        if self._duragan:
            self._tut = None
            c = self.komut(simdi, aci, alt, ust, hata_px=hata_px, olu_px=olu_px)
            return None if c is None else self._yorunge_sinirla(c, 0.0, alt, ust, pay)
        self._kip_ayari(True)
        # TUTMA: hedef gorunurde olu bolgede ve duruyor -> namlu oldugu yerde sabit.
        # Tutma konumu GIRISTE bir kez alinir; her cagrida olculen aciya "yeniden
        # oturtmak" motoru kipirdatirdi.
        if (hata_px is not None and olu_px is not None and abs(float(hata_px)) <= float(olu_px)
                and abs(hiz) <= self.durus_hizi * self._s):
            if self._tut is None:
                self._tut = max(float(alt), min(float(ust), aci))
            self.son_komut_t = simdi
            return self._yorunge_sinirla(self._tut, 0.0, alt, ust, pay)
        self._tut = None
        # ONGORU YOK (konum kipindeki `ileri` burada kullanilmaz): kart referansi
        # komut anindan itibaren kendisi ilerletir. Eklenirse namlu hedefin hiz x ileri
        # kadar ONUNDE gider (benzetim: 8 der/sn'de sabit 0.4 derece = 7.5 px).
        hedef = self.kestirici.tahmin(simdi)
        namlu = aci - self._ofset()
        hedef = max(namlu - self.azami_sicrama, min(namlu + self.azami_sicrama, hedef))
        self.son_tahmin = hedef
        # Bosluk tarafi: hedef belirgin hizla hareket ediyorsa hizin yonu; yavasta ancak
        # konum farki boslugu asinca degisir. Histerezissiz her kucuk hiz isaret
        # degisiminde komut bosluk kadar sicrardi.
        if abs(hiz) >= 1.0 * self._s:
            self._yor_yon = 1 if hiz > 0 else -1
        elif abs(hedef - namlu) > max(0.2, self.bosluk_kest) or not self._yor_yon:
            self._yor_yon = 1 if hedef > namlu else -1
        motor = hedef + self._yor_yon * self.bosluk_kest * 0.5
        # HIZ TAVANI: karta giden ileri besleme hizi. 5 m'de 1 m/s hedef ~11 der/sn,
        # sahada elle savrulan drone tepede 30-60. 23.09 kaydinda 62 der/sn komut
        # gercek bir hedefin degil kilit sicramasinin imzasiydi.
        hiz = max(-self.yor_hiz_tavan, min(self.yor_hiz_tavan, hiz * self._ileri_besleme_orani()))
        if motor >= ust:
            motor, hiz = float(ust), min(0.0, hiz)
        elif motor <= alt:
            motor, hiz = float(alt), max(0.0, hiz)
        self.son_komut, self.son_komut_t = hedef, simdi
        return self._yorunge_sinirla(motor, hiz, alt, ust, pay)


def olcum_acisi(kol_kare, hata_px, ppd):
    """Hedefin dunya acisi (komut derecesi): kare cekildigindeki kol acisi eksi
    piksel hatasinin dereceye cevrimi. hata_px > 0 = hedef merkezin ALTINDA."""
    return kol_kare - hata_px / ppd


if __name__ == "__main__":
    import random
    rng = random.Random(7)

    # 1. Sabit hizla giden hedef: hiz dogru kestirilmeli, tahmin one gecmeli
    k = HedefKestirici(q=100.0, r=0.3)
    for i in range(60):                        # 60 Hz, 1 sn, 12 derece/sn
        t = i / 60.0
        k.guncelle(t, 10.0 + 12.0 * t + rng.gauss(0, 0.3))
    assert abs(k.hiz - 12.0) < 2.0, k.hiz
    assert abs(k.tahmin(1.1) - (10.0 + 12.0 * 1.1)) < 0.8, k.tahmin(1.1)

    # 2. KESINTI: olcum gelmezken tahmin hedefi kovalamaya devam etmeli
    #    (sahadaki "kaybedince kol duruyor, hedef kaciyor" sorununun cozumu)
    gercek_05 = 10.0 + 12.0 * (59 / 60.0 + 0.5)
    assert abs(k.tahmin(59 / 60.0 + 0.5) - gercek_05) < 1.5
    assert abs(k.kayip_sure(59 / 60.0 + 0.5) - 0.5) < 1e-9

    # 3. Duran hedef: gurultu bastirilmali (ham olcumden daha az oynamali)
    k2 = HedefKestirici(q=100.0, r=0.3)
    ham, kest = [], []
    for i in range(120):
        z = 20.0 + rng.gauss(0, 0.3)
        k2.guncelle(i / 60.0, z)
        if i > 30:
            ham.append(z); kest.append(k2.tahmin(i / 60.0))
    std = lambda v: (sum((x - sum(v) / len(v)) ** 2 for x in v) / len(v)) ** 0.5
    assert std(kest) < 0.6 * std(ham), (std(kest), std(ham))
    assert abs(k2.hiz) < 1.0, k2.hiz

    # 4. TEK AYKIRI kutu motoru sicratrmamali; ayni yeni yerde iki olcum gelirse
    #    bunun gercek hedef/ID degisimi oldugu kabul edilip filtre yeniden kurulmali.
    k3 = HedefKestirici(q=100.0, r=0.3)
    for i in range(30):
        k3.guncelle(i / 60.0, 5.0 + 20.0 * i / 60.0)
    assert k3.hiz > 10
    once = k3.tahmin(0.52)
    kabul = k3.guncelle(0.52, 40.0)            # tek karelik 25+ derece ziplama
    assert not kabul and abs(k3.tahmin(0.52) - once) < 1e-9 and k3.hiz > 10
    kabul = k3.guncelle(0.54, 40.2)            # ayni yeni yerde ikinci olcum
    assert not kabul and abs(k3.tahmin(0.54) - 40.1) < 0.2 and k3.hiz == 0.0
    assert not k3.hazir                         # yeni hiz icin bir gercek kare daha gerekir

    # 5. ZAMANI GERI GIDEN kare kabul edilmemeli (decoder gec teslim etti).
    k4 = HedefKestirici(q=100.0, r=0.3)
    assert k4.guncelle(1.0, 10.0) and k4.guncelle(1.1, 11.0)
    eski = (list(k4.x), [list(r_) for r_ in k4.P], k4.t, k4.t_olcum)
    assert not k4.guncelle(1.05, 50.0)
    assert (k4.x, k4.P, k4.t, k4.t_olcum) == eski

    # 6. Olcum acisi isareti: hedef merkezin ALTINDA (+px) -> kolun ALTINDA
    assert olcum_acisi(20.0, +60.0, 12.0) == 15.0
    assert olcum_acisi(20.0, -60.0, 12.0) == 25.0

    # 7. KOMUT SEKILLENDIRME: filtre uzagi gosterse bile bir komut 45 deg/sn'nin
    #    25 Hz'deki payini (1.8 derece) asamaz; ters yone kucuk gurultu bastirilir.
    c = KalmanTakipKontrolu(q=100.0, r=0.3, komut_hz=25.0, azami_hiz=45.0)
    assert c.olcum(0.00, 0.0, -160.0, 8.0)      # hedef dunya acisi +20
    assert c.olcum(0.04, 0.0, -160.0, 8.0)
    ilk = c.komut(0.08, 0.0, hedef_var=True, hata_px=-160.0, olu_px=10.0)
    assert ilk is not None and 0.0 < ilk <= 45.0 / 25.0 + 1e-9, ilk
    assert c.komut(0.09, 0.0) is None            # 25 Hz kapisi

    # 8. KISA kayipta tahminle devam, sure asiminda kesin durus + filtre sifirlama.
    devam = c.komut(0.13, 0.5, hedef_var=False)
    assert devam is not None
    assert c.komut(1.0, 1.0, hedef_var=False) is None and not c.hazir

    # 9. UCTAN UCA SENTETIK TAKIP: 4 kare gecikme, gurultu ve periyodik 250 ms
    #    tespit kesintisinde hedef makul hatayla izlenmeli; komutlar hiz tavanini
    #    asmamali. Bu fiziksel mekanik testi DEGIL, algoritmik regresyon testidir.
    rng2 = random.Random(19)
    c2 = KalmanTakipKontrolu(q=120.0, r=0.4, komut_hz=25.0, azami_hiz=45.0,
                             kayip_kovalamasi=0.45)
    dt, ppd, kol, hedef_komut = 1 / 60.0, 8.0, 20.0, 20.0
    gecmis, hatalar, komutlar = [], [], []
    for i in range(720):                         # 12 saniye
        t = i * dt
        hedef = 25.0 + 5.0 * math.sin(2 * math.pi * t / 3.0)
        # Basit hız-sınırlı mekanik: firmware ivmesi burada modellenmez; amac
        # filtrenin gecikme/gurultu/kayip davranisini sinamaktir.
        fark = max(-45.0 * dt, min(45.0 * dt, hedef_komut - kol))
        kol += fark
        gecmis.append((t, kol, hedef))
        if len(gecmis) > 4:
            tk, kk, hk = gecmis[-5]              # ~67 ms kamera+inference gecikmesi
            hata_px = (kk - hk) * ppd + rng2.gauss(0.0, 2.5)
            kayip = (t % 2.0) > 1.75             # her 2 sn'de 250 ms korluk
            if not kayip:
                c2.olcum(tk, kk, hata_px, ppd)
            yeni = c2.komut(t, kol, hedef_var=not kayip, hata_px=hata_px,
                             olu_px=6.0, alt=0.0, ust=60.0)
            if yeni is not None:
                if komutlar:
                    assert abs(yeni - komutlar[-1][1]) <= 45.0 * 0.20 + 1e-6
                hedef_komut = yeni
                komutlar.append((t, yeni))
        if t > 2.0:
            hatalar.append(abs(kol - hedef))
    assert st.median(hatalar) < 1.6, st.median(hatalar)
    assert max(hatalar) < 5.0, max(hatalar)
    assert len(komutlar) < 360, len(komutlar)       # 30 Hz'den belirgin az

    # 10. EksenTakip — FIRMWARE BENZERI mekanik (tepe hiz + ivme + yeniden hedefleme),
    #     DISLI BOSLUGU ve 83 ms kamera gecikmesi. Sahadaki (21.09) titreme/dur-kalk
    #     sikayetinin regresyonu. Esikler benzetimdeki eski PD zincirine gore konuldu
    #     (PD: yavas sinus medyan ~24 px, hizli sinus ~83 px, duran hedefte 2.3 px).
    class _Motor:
        def __init__(s, vmax, ivme, bosluk):
            s.x = s.v = s.hedef = s.namlu = 0.0
            s.vmax, s.ivme, s.b = vmax, ivme, bosluk

        def adim(s, dt):
            e = s.hedef - s.x
            if abs(e) < 1e-4 and abs(s.v) < 1e-3:
                s.v, s.x = 0.0, s.hedef
            else:
                vis = math.copysign(min(s.vmax, math.sqrt(2 * s.ivme * abs(e))), e)
                s.v += max(-s.ivme * dt, min(s.ivme * dt, vis - s.v))
                s.x += s.v * dt
                if (e > 0 and s.x > s.hedef) or (e < 0 and s.x < s.hedef):
                    s.x, s.v = s.hedef, 0.0
            if s.x - s.namlu > s.b / 2:
                s.namlu = s.x - s.b / 2
            if s.namlu - s.x > s.b / 2:
                s.namlu = s.x + s.b / 2

    def _eksen_kos(hedef_f, bosluk, ppd_gercek=12.0, sure=12.0):
        rng3 = random.Random(3)
        m, dt, gec = _Motor(60.0, 500.0, bosluk), 1 / 60.0, []
        eks = EksenTakip(isaret=1.0)
        hatalar, yon, onceki, son_x = [], 0, 0, 0.0
        for i in range(int(sure / dt)):
            t = i * dt
            m.adim(dt)
            gec.append((t, m.x, m.namlu, hedef_f(t)))
            if len(gec) > 5:
                tk, xk, nk, hk = gec[-6]
                hata = (hk - nk) * ppd_gercek + rng3.gauss(0, 1.5)
                if t > 1.0:
                    hatalar.append(abs((hedef_f(t) - m.namlu) * ppd_gercek))
                eks.olcum(tk, xk, hata, 12.0)
                c = eks.komut(t, m.x, -400, 400, hata_px=hata, olu_px=7.2)
                if c is not None:
                    m.hedef = c
            d = 1 if m.x - son_x > 0.02 else (-1 if m.x - son_x < -0.02 else 0)
            if d and onceki and d != onceki:
                yon += 1
            if d:
                onceki = d
            son_x = m.x
        return st.median(hatalar), yon

    for b in (0.0, 0.3, 1.0, 2.0):                  # bosluk bilinmiyor: hepsinde saglam
        e, y = _eksen_kos(lambda t: 8.0, b)
        assert e < 7.2 and y <= 4, ("duran hedef", b, e, y)
        e, y = _eksen_kos(lambda t: 10 * math.sin(2 * math.pi * t / 4), b)
        assert e < 13.0 and y <= 10, ("yavas sinus", b, e, y)
        e, y = _eksen_kos(lambda t: 15 * math.sin(2 * math.pi * t / 2), b)
        assert e < 65.0 and y <= 12, ("hizli sinus", b, e, y)
        e, y = _eksen_kos(lambda t: 20 * t if t < 6 else 120.0, b)
        assert e < 8.0 and y <= 3, ("rampa", b, e, y)
    for p in (8.0, 17.0):                           # ppd %30 yanlis
        e, y = _eksen_kos(lambda t: 8.0, 1.0, ppd_gercek=p)
        assert e < 7.2 and y <= 8, ("ppd yanlis", p, e, y)
    # 11. YORUNGE KIPI (firmware yorunge_core.h'nin kopyasi): rayda sabit hizli hedefte
    #     motor DURMADAN akar ve hedefin ustunde kalir; konum kipi ayni hedefte her
    #     guncellemede hizlanip yavaslar (sahadaki titreme sikayeti).
    def _yor_kos(hedef_f, sure=10.0, bosluk=0.6):
        rng4 = random.Random(5)
        x = v = namlu = 0.0
        p0 = v0 = 0.0
        t0, aktif = -1.0, False
        eks = EksenTakip(isaret=1.0, bosluk=0.8)
        gecmis, hatalar, ivmeler, dur_kalk, durdu = [], [], [], 0, False
        dt, son_kare, onceki_v = 0.001, -1.0, 0.0
        for i in range(int(sure / dt)):
            t = i * dt
            if aktif:
                vh = 0.0 if t - t0 > 0.15 else v0 + 8.0 * ((p0 + v0 * (t - t0)) - x)
                vh = max(-60.0, min(60.0, vh))
                v += max(-500 * dt, min(500 * dt, vh - v))
                x += v * dt
            if x - namlu > bosluk / 2:
                namlu = x - bosluk / 2
            if namlu - x > bosluk / 2:
                namlu = x + bosluk / 2
            gecmis.append((t, x, namlu))
            if t - son_kare >= 1 / 60.0 - 1e-9:
                son_kare = t
                tk, xk, nk = gecmis[max(0, len(gecmis) - 51)]
                hata = (hedef_f(tk) - nk) * 18.7 + rng4.gauss(0, 1.5)
                eks.olcum(tk, xk, hata, 18.7)
                r = eks.yorunge_komut(t, x, -400, 400, hata_px=hata, olu_px=7.0)
                if r is not None:
                    (p0, v0), t0, aktif = r, t, True
                if t > 2:
                    hatalar.append(abs(hedef_f(t) - namlu) * 18.7)
            if t > 2 and i % 10 == 0:
                vh_ = (hedef_f(t + 0.005) - hedef_f(t - 0.005)) / 0.01
                if abs(vh_) > 1.5:
                    if abs(v) < 0.15 * abs(vh_) and not durdu:
                        dur_kalk, durdu = dur_kalk + 1, True
                    elif abs(v) > 0.5 * abs(vh_):
                        durdu = False
                ivmeler.append(abs(v - onceki_v) / 0.01)
                onceki_v = v
        return st.median(hatalar), dur_kalk, st.mean(ivmeler)

    e, dk, iv = _yor_kos(lambda t: -20 + 8 * t)
    assert e < 2.0 and dk == 0 and iv < 60, ("rampa", e, dk, iv)
    e, dk, iv = _yor_kos(lambda t: 6.0)
    assert e < 3.0 and iv < 5, ("duran", e, dk, iv)
    e, dk, iv = _yor_kos(lambda t: 8 * math.sin(2 * math.pi * t / 5))
    assert e < 7.0 and dk <= 8 and iv < 80, ("sinus", e, dk, iv)
    # 12. ADAPTIVE Q: el titremesi (~0.25 derece, 6-9 Hz) olan DURAN hedefi namlu
    #     izlememeli (sabit q=300 iken ort ivme ~70 idi).
    titrek = lambda t: 5.0 + 0.15 * math.sin(2 * math.pi * 6 * t) + 0.1 * math.sin(2 * math.pi * 9.3 * t + 1)
    e, dk, iv = _yor_kos(titrek)
    print(f"  (titreyen duran hedef: medyan {e:.1f} px, ort ivme {iv:.0f})")
    assert e < 4.0 and iv < 45, ("titreme", e, dk, iv)

    # tilt isareti: hata_px > 0 (hedef ALTTA) -> daha dusuk aci
    ti = EksenTakip(isaret=-1.0)
    ti.olcum(0.0, 20.0, 60.0, 12.0); ti.olcum(0.02, 20.0, 60.0, 12.0)
    assert ti.komut(0.05, 20.0, 0.0, 60.0) < 20.0

    # YORUNGEDE KAYIP: son hizli komut 150 ms kartta akarken uc kare hedef
    # yoksa bir kez hiz=0 gonder; ayni bekleme her kare tekrarlanmasin.
    kayip = EksenTakip(isaret=1.0)
    for i in range(8):
        kayip.olcum(i * 0.02, 0.0, 100.0, 18.7)
    assert kayip.yorunge_komut(0.16, 0.0, -20.0, 20.0, hata_px=100.0, olu_px=7.0)
    dur = kayip.yorunge_komut(0.26, 1.0, -20.0, 20.0)
    assert dur == (1.0, 0.0), dur
    assert kayip.yorunge_komut(0.30, 1.0, -20.0, 20.0) is None
    kayip.olcum(0.31, 1.0, 80.0, 18.7)
    assert kayip.yorunge_komut(0.35, 1.0, -20.0, 20.0, hata_px=80.0, olu_px=7.0)

    # Dar test penceresinde hiz, kartin 150 ms ufku + fren payiyla sinirda
    # birikmemeli; eskiden konum 31'e kirpilip hiz +38 kalabiliyordu.
    for konum, hiz in ((30.5, 38.0), (21.5, -38.0), (26.0, 20.0)):
        p, v = EksenTakip._yorunge_sinirla(konum, hiz, 21.0, 31.0)
        assert 22.5 <= p <= 29.5 and 22.5 <= p + 0.25 * v <= 29.5, (p, v)

    # KILIT BASKA NESNEYE GECINCE: eski nesnenin konumu ile yenisininki arasindaki fark
    # hiz sanilmamali (23.09: 213 px sicrama -> 62 der/sn). hedef_degisti() sonrasi ilk
    # yorunge komutunun hizi kucuk; bosluk modeli korunur.
    e = EksenTakip(isaret=1.0)
    for i in range(30):
        e.olcum(i / 30.0, 0.0, 0.0, 18.7)
        e.yorunge_komut(i / 30.0 + 0.001, 0.0, -90.0, 90.0, hata_px=0.0, olu_px=7.0)
    bosluk, namlu = e.bosluk_kest, e._namlu
    assert e.hazir
    e.hedef_degisti()
    assert not e.hazir and e.kestirici.hiz == 0.0, "hedef degisimi kestirimi sifirlamadi"
    assert e.bosluk_kest == bosluk and e._namlu == namlu, "hedef degisimi bosluk modelini sildi"

    # YORUNGE HIZ TAVANI: 60 der/sn kacan hedefte tavansiz komut 80+ der/sn'ye
    # cikiyordu; karta giden hiz yor_hiz_tavan'i (45) asamaz.
    e = EksenTakip(isaret=1.0)
    tepe = 0.0
    for i in range(60):
        t = i / 30.0
        e.olcum(t, 0.0, 60.0 * t * 18.7, 18.7)
        r = e.yorunge_komut(t + 0.001, 0.0, -180.0, 180.0, hata_px=60.0 * t * 18.7, olu_px=7.0)
        if r is not None:
            tepe = max(tepe, abs(r[1]))
    assert 40.0 <= tepe <= 45.0 + 1e-6, f"yorunge hiz tavani: tepe {tepe:.1f} der/sn"

    # UYARLAMALI ILERI BESLEME: sabit hizla giden (rayda) hedefte TAM hiz beslemesi;
    # hedef durunca (acilar artik dogruya oturmaz) YARIM — gecikme yuzunden eski hizla
    # hedefi asmasin. Benzetim: 20 der/sn'den duran hedefte asma 3.45 -> 1.88 derece,
    # raydaki (8 der/sn) hedefte hata degismedi.
    e = EksenTakip(isaret=1.0)
    for i in range(30):                                    # 10 der/sn, 1 sn
        t = i / 30.0
        e.olcum(t, 0.0, 10.0 * t * 18.7, 18.7)
    assert e._ileri_besleme_orani() == 1.0, "sabit hizli hedefte ileri besleme kisildi"
    for i in range(30, 42):                                # hedef DURDU (0.4 sn)
        t = i / 30.0
        e.olcum(t, 0.0, 10.0 * 1.0 * 18.7, 18.7)
    assert e._ileri_besleme_orani() == e.yor_ff_dusuk, "duran hedefte ileri besleme tam kaldi"
    # Yorunge komutu bu carpani KULLANIR: ayni olcumler, uyarlamali ve uyarlamasiz iki
    # takipci; hedef durduktan sonra karta giden hiz uyarlamalida belirgin kucuk.
    def _durus_hizlari(dusuk):
        e = EksenTakip(isaret=1.0, yor_ff_dusuk=dusuk)
        hiz = []
        for i in range(48):
            t = i / 30.0
            h = 10.0 * min(t, 1.0) * 18.7                 # 1 sn 10 der/sn, sonra durur
            e.olcum(t, 0.0, h, 18.7)
            r = e.yorunge_komut(t + 0.001, 0.0, -90.0, 90.0, hata_px=h, olu_px=7.0)
            # durus ~3 olcumde (ornek pencere) anlasilir; ondan sonraki komutlar
            if r is not None and t > 1.12:
                hiz.append(abs(r[1]))
        return hiz
    uyar, sabit = _durus_hizlari(0.5), _durus_hizlari(1.0)
    assert uyar and sum(sabit) > 1.0, "kurulum: durus sonrasi yorunge komutu uretilmedi"
    assert sum(uyar) < 0.75 * sum(sabit), f"durusta hiz kisilmadi: {sum(uyar):.1f} vs {sum(sabit):.1f}"

    # 13. SAHA DENGESI (24.09): yakinda titreme / uzakta akicilik. SAHADAKI kosullar: kare ->
    #     karar 0.15 sn, cikarim 17 Hz, %20 kayip kare, olcum gurultusu balon boyunun %10'u
    #     (%6 olasilikla 3.5 kat), kart yorunge kopyasi (K=8, 250 der/sn^2).
    def _saha_kos(hedef_f, boy, ek, sure=9.0, tohum=1):
        rng5 = random.Random(tohum)
        e = EksenTakip(isaret=1.0, bosluk=0.8, **ek)
        dt, x, v, namlu, p0, v0, t0, aktif = 0.002, 0.8, 0.0, 0.8, 0.0, 0.0, -1.0, False
        gecmis, bekleyen, sonraki, serbest = [], [], 0.0, 0.0
        hata, icerde, hizlar = [], [], []
        for i in range(int(sure / dt)):
            t = i * dt
            if aktif:
                vh = 0.0 if t - t0 > 0.15 else v0 + 8.0 * ((p0 + v0 * (t - t0)) - x)
                vh = max(-60.0, min(60.0, vh))
                v += max(-250 * dt, min(250 * dt, vh - v))
                x += v * dt
            namlu = min(max(namlu, x - 0.3), x + 0.3)
            gecmis.append((t, x))
            if t >= sonraki:
                sonraki += 1 / 30.0
                if t >= serbest:
                    serbest = t + 1 / 17.0
                    s_ = max(1.2, 0.1 * boy) * (3.5 if rng5.random() < 0.06 else 1.0)
                    gor = rng5.random() < 0.8
                    bekleyen.append((t + 0.15, t, (hedef_f(t) - namlu) * 18.7 + rng5.gauss(0, s_), gor))
            while bekleyen and bekleyen[0][0] <= t:
                _, tk, h, gor = bekleyen.pop(0)
                xk = next(g[1] for g in reversed(gecmis) if g[0] <= tk)
                if gor:
                    e.olcum(tk, xk, h, 18.7, boy_px=boy)
                r = e.yorunge_komut(t, x, -400, 400, hata_px=h if gor else None,
                                    olu_px=0.25 * boy if gor else None, pay=0.0)
                if r is not None:
                    (p0, v0), t0, aktif = r, t, True
            if t > 1.5 and i % 5 == 0:
                d = abs(hedef_f(t) - namlu) * 18.7
                hata.append(d); icerde.append(d <= 0.25 * boy); hizlar.append(v)
        yon, son = 0, 0
        for h_ in hizlar:
            if abs(h_) > 1.0:
                s_ = 1 if h_ > 0 else -1
                yon, son = yon + (son != 0 and s_ != son), s_
        return yon / (sure - 1.5), st.median(hata), sum(icerde) / len(icerde)

    def _ort(hedef_f, boy, ek):
        r = [_saha_kos(hedef_f, boy, ek, tohum=k) for k in (1, 2, 3)]
        return tuple(sum(x[j] for x in r) / len(r) for j in range(3))

    yakin = lambda t: 5.0 + 0.3 * math.sin(2 * math.pi * 0.6 * t)       # 90 px, elde duran
    uzak = lambda t: 5.0 + 6.0 * (1.5 - abs((t % 6.0) - 3.0))             # 20 px, yuruyen
    y_eski, y_yeni = _ort(yakin, 90.0, {}), _ort(yakin, 90.0, SAHA_AYARI)
    u_eski, u_yeni = _ort(uzak, 20.0, {}), _ort(uzak, 20.0, SAHA_AYARI)
    print(f"  (saha: yakin 90 px yon/sn {y_eski[0]:.2f} -> {y_yeni[0]:.2f}, balon icinde "
          f"%{100*y_eski[2]:.0f} -> %{100*y_yeni[2]:.0f}; uzak yuruyen hata {u_eski[1]:.1f} -> "
          f"{u_yeni[1]:.1f} px)")
    assert y_yeni[0] < 0.6 * y_eski[0], ("yakinda titreme azalmadi", y_eski, y_yeni)
    assert y_yeni[1] < y_eski[1] and y_yeni[2] >= y_eski[2], ("yakinda nisan kotulesti", y_eski, y_yeni)
    assert u_yeni[1] <= u_eski[1], ("uzakta takip geride kaldi", u_eski, u_yeni)
    # Olcek: kucuk balonda ayar AYNEN (s=1); buyukte r ve q sinirlari boyla
    o = EksenTakip(isaret=1.0, **SAHA_AYARI)
    o.olcum(0.0, 0.0, 0.0, 18.7, boy_px=20.0)
    assert o._s == 1.0
    o.olcum(0.02, 0.0, 0.0, 18.7, boy_px=96.0)
    o._kip_ayari(True)
    assert o._s == 4.0 and abs(o.kestirici.r - 0.3 * 4.0) < 1e-9, (o._s, o.kestirici.r)
    assert abs(o.kestirici.q_max - 800.0 * 16) < 1e-6 and abs(o.kestirici.q_min - 60.0 * 16) < 1e-6
    o._kip_ayari(False)
    assert abs(o.kestirici.r - 0.6 * 4.0) < 1e-9 and abs(o.kestirici.q - 40.0 * 16) < 1e-6
    # Tek kayip kare (kare -> karar 0.15 sn + bir kare) namluyu DURDURMAZ; uzun kayip durdurur
    k1 = EksenTakip(isaret=1.0, **SAHA_AYARI)
    for i in range(12):
        k1.olcum(i / 17.0, 0.0, 10.0 * 18.7 * i / 17.0, 18.7)
        k1.yorunge_komut(i / 17.0 + 0.15, 0.0, -90.0, 90.0, hata_px=10.0 * 18.7 * i / 17.0, olu_px=5.0)
    t_son = 11 / 17.0
    assert not k1._kayip_durdu
    k1.yorunge_komut(t_son + 0.15 + 1 / 17.0, 0.0, -90.0, 90.0)
    assert not k1._kayip_durdu, "tek kayip karede namlu durduruldu"
    r = k1.yorunge_komut(t_son + 0.40, 0.0, -90.0, 90.0)
    assert k1._kayip_durdu and r is not None and r[1] == 0.0, "uzun kayipta durmadi"
    # Hiz esikleri boyla olceklenir: 2.5 der/sn, 96 px balonda (s=4, yakinda elde tutulan
    # hedefin sallanmasi) "duruyor", 20 px balonda (uzakta yuruyen) "hareketli" sayilir.
    def _duragan_orani(boy):
        """Son 0.8 sn'de 'duruyor' sayilan adimlarin orani (kip acilip kapaniyorsa ~0.5)."""
        k3 = EksenTakip(isaret=1.0, **SAHA_AYARI)
        z, sayim = 0.0, []
        for i in range(int(2.6 * 17)):
            t = i / 17.0
            z += (12.0 if t < 0.6 else 2.5) / 17.0       # once hizli (durustan cikar), sonra yavas
            k3.olcum(t, 0.0, z * 18.7, 18.7, boy_px=boy)
            k3.yorunge_komut(t + 0.15, 0.0, -90.0, 90.0, hata_px=z * 18.7, olu_px=0.25 * boy)
            if t >= 1.8:
                sayim.append(k3._duragan)
        return sum(sayim) / len(sayim)
    assert _duragan_orani(96.0) >= 0.9, "buyuk balonda yavas sallanma hareket sayildi (esik olceklenmedi)"
    assert _duragan_orani(20.0) <= 0.1, "kucuk balonda yuruyen hedef duruyor sayildi"
    # Kisa boslukta DURAN hedef: namlu yerinde bekler (yeni komut yok) — tahminle konum
    # komutu uretip bir sonraki karede geri donmek yakindaki dur-kalk titremesiydi.
    for tut_acik in (True, False):
        k2 = EksenTakip(isaret=1.0, **dict(SAHA_AYARI, kayipta_tut=tut_acik))
        for i in range(20):                          # namlu 0'da, hedef 3 derecede, duruyor
            k2.olcum(i / 17.0, 0.0, 3.0 * 18.7, 18.7)
            k2.yorunge_komut(i / 17.0 + 0.15, 0.0, -90.0, 90.0, hata_px=3.0 * 18.7, olu_px=5.0)
        assert k2._duragan
        k2.son_komut, k2.son_komut_t = 0.0, None     # son komut namlunun yeri: fark 3 derece
        r = k2.yorunge_komut(19 / 17.0 + 0.15 + 1 / 17.0, 0.0, -90.0, 90.0)
        if tut_acik:
            assert r is None, f"kisa boslukta duran hedefe komut gitti: {r}"
        else:
            assert r is not None, "kurulum: kayipta_tut kapaliyken komut beklenirdi"

    # 14. ATES KORLUGU (24.09 saha, 21:27 kaydi): lazer noktasi balona degince model onu
    #     goremez. korluk() suresince olcum yoklugu KAYIP DEGIL: kayan balonda namlu son
    #     1.5 sn'ye uydurulan dogruyu izler (durdurulsaydi balon noktanin altindan kayardi),
    #     duran balonda yerinde bekler, sallanan balonda egim anlamsizsa kosmaz.
    import random

    def _kor_kos(hiz, korlu, sallanti=0.0, boy=13.0, gur=0.1, tohum=3):
        rng = random.Random(tohum)
        # bosluk 0: "namlu balonun uzerinde" beslemesi bosluk modelinin oturma gecisiyle
        # celisip olcumlere sahte egim katmasin (dogru uydurmanin kendisi sinaniyor)
        k = EksenTakip(isaret=1.0, bosluk=0.0, **SAHA_AYARI)
        z = lambda t: 5.0 + hiz * t + sallanti * math.sin(2 * math.pi * 0.6 * t)
        t = 0.0
        while t < 1.6:                                  # namlu balonun uzerinde, 17 Hz
            h = rng.gauss(0.0, gur * boy)
            k.olcum(t, z(t), h, 18.7, boy_px=boy)
            k.yorunge_komut(t + 0.12, z(t + 0.12), -90.0, 90.0, hata_px=h, olu_px=0.25 * boy)
            t += 1 / 17.0
        bitis = t + 2.0
        if korlu:
            k.korluk(bitis)
        cikti = []
        while t < bitis - 0.05:                         # ates: model kor
            cikti.append((t, k.yorunge_komut(t, z(t), -90.0, 90.0)))
            t += 0.04
        return k, z, cikti, t

    k, z, c, t = _kor_kos(1.0, korlu=False)
    assert k._kayip_durdu and any(r is not None and r[1] == 0.0 for _, r in c), \
        "kurulum: korluk yokken kayipta namlu durmadi"
    k, z, c, t = _kor_kos(1.0, korlu=True)
    assert not k._kayip_durdu and not any(r is not None and r[1] == 0.0 for _, r in c), \
        "lazer altinda (korluk) kayan balonda namlu DURDURULDU"
    hareket = [r for _, r in c if r is not None]
    assert hareket and abs(hareket[-1][1] - 1.0) < 0.35, f"korlukte hiz kestirilen yolda degil: {hareket[-1]}"
    assert abs(k.son_komut - z(k.son_komut_t)) < 0.3,         f"korlukte namlu balondan kaydi: {k.son_komut} / {z(k.son_komut_t)}"
    assert k.yorunge_komut(t + 0.1, z(t), -90.0, 90.0) is not None and k._kayip_durdu, \
        "korluk bitti, balon gelmedi: namlu durmali"
    k, z, c, t = _kor_kos(0.0, korlu=True)
    assert k._duragan and all(r is None for _, r in c) and not k._kayip_durdu, \
        f"korlukte DURAN balona komut gitti: {[r for _, r in c if r][:3]}"
    k, z, c, t = _kor_kos(0.0, korlu=True, sallanti=0.3, boy=90.0)
    assert all(r is None or r[1] == 0.0 for _, r in c), \
        "elde sallanan yakin balonda salinimin anlik egimiyle kosuldu"
    # Gurultulu kutulu DURAN uzak balon (sahada kuyruklu): egim esigi asiyor (-0.28 der/sn)
    # ama kendi belirsizliginin 3 katinin (0.54) altinda -> anlamsiz, kosulmaz.
    k, z, c, t = _kor_kos(0.0, korlu=True, boy=20.0, gur=0.3, tohum=24)
    assert all(r is None or r[1] == 0.0 for _, r in c),         "duran balonda gurultunun anlamsiz egimiyle kosuldu"
    k.hedef_degisti()
    assert k.kor_bitis is None, "kilit degisti, korluk yeni hedefe tasindi"

    print("hedef_kestirici testleri OK — hiz kestirimi, kesintide tahmin, gurultu, "
          "aykiri/geri-zaman korumasi, hiz-sinirli yumusak komut, sentetik takip, "
          "hedef degisiminde sifirlama, yorunge hiz tavani, uyarlamali ileri besleme, "
          "ates korlugu (kayan / duran / sallanan balon)")
