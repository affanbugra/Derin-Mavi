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
                 yor_q_min=60.0):
        self.isaret = 1.0 if isaret >= 0 else -1.0
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
        self.sifirla()

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
        self._kayip_durdu = False                   # kayipta tek hiz-sifir komutu

    @property
    def hazir(self):
        return self.kestirici.hazir

    def _kip_ayari(self, yorunge):
        k = self.kestirici
        if yorunge:
            if k.q_min is None or k.r != self._yor_qr[1]:      # kipe ilk giris
                k.q, k.r = self._yor_qr
                k.q_min = self._yor_q_min
                k.q_max = self._yor_qr[0] if self._yor_q_min is not None else None
                if k.q_min is None:
                    k.q_max = None
        else:
            k.q, k.r = self._konum_qr
            k.q_min = k.q_max = None

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

    def olcum(self, t_kare, aci_kare, hata_px, ppd):
        """Kare `t_kare`de cekildi; eksen o an `aci_kare`deydi; hedef merkezden
        `hata_px` uzakta. Doner: olcum kabul edildi mi."""
        if aci_kare is None or hata_px is None or not ppd:
            return False
        z = float(aci_kare) - self._ofset(t_kare) + self.isaret * float(hata_px) / float(ppd)
        self._son_kare = (float(t_kare), float(hata_px), float(ppd))
        kabul = self.kestirici.guncelle(t_kare, z)
        if kabul:
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
        if self.kestirici.kayip_sure(simdi) > self.kayip_kovalamasi:
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
                and abs(hiz) <= self.durus_hizi):
            return None
        # YERLESME DUZELTMESI: hedef duruyor, motor durduktan SONRA cekilmis bir kare
        # hala olu bolge disini gosteriyor. Bu kare bayat degil (hareket bitmisti), yani
        # hata dogrudan uygulanabilir — ters yonde olsa bile (histerezis bosluk
        # salinimi icindir; yerlesmis namluda salinim yok). Model hatalarinin (bosluk,
        # ppd) biraktigi kalici sapmayi bu kapatir.
        kare = self._son_kare
        if (kare is not None and olu_px is not None and abs(hiz) <= self.durus_hizi
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
        if abs(hiz) > self.durus_hizi:
            tahmin += hiz * self.ileri
        self.son_tahmin = tahmin
        namlu = aci - self._ofset()
        hedef = max(namlu - self.azami_sicrama, min(namlu + self.azami_sicrama, tahmin))
        referans = namlu if self.son_komut is None else self.son_komut
        fark = hedef - referans
        olu = self.olu if olu is None else max(self.olu, float(olu))
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
        if hata_px is None and kayip_sure >= 0.10 and not self._kayip_durdu:
            # Son hizli komut firmware'de 150 ms daha akar. Hedef uc kare kadar
            # gorunmediyse eski hizi sifirla; belirsiz bolgeye tahminle kosma.
            self._kayip_durdu = True
            self._tut = max(float(alt), min(float(ust), aci))
            self.son_komut_t = simdi
            return self._yorunge_sinirla(self._tut, 0.0, alt, ust, pay)
        if self._kayip_durdu:
            return None
        if kayip_sure > self.kayip_kovalamasi:
            if self.kestirici.baslatildi:
                self.sifirla()
            return None
        if not self.hazir:
            return None
        if self.son_komut_t is not None and simdi - self.son_komut_t < self.komut_periyodu:
            return None
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
        if abs(v_uzun) >= 1.0:
            self._yavas_t = None
        elif self._yavas_t is None:
            self._yavas_t = simdi
        if self._duragan and abs(v_kisa) > 2.0:
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
                and abs(hiz) <= self.durus_hizi):
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
        if abs(hiz) >= 1.0:
            self._yor_yon = 1 if hiz > 0 else -1
        elif abs(hedef - namlu) > max(0.2, self.bosluk_kest) or not self._yor_yon:
            self._yor_yon = 1 if hedef > namlu else -1
        motor = hedef + self._yor_yon * self.bosluk_kest * 0.5
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

    print("hedef_kestirici testleri OK — hiz kestirimi, kesintide tahmin, gurultu, "
          "aykiri/geri-zaman korumasi, hiz-sinirli yumusak komut, sentetik takip")
