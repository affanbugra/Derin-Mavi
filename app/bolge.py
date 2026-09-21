"""Harekete / atışa İZİNLİ PENCERELER — şartname §4.2 güvenlik hususu.

[KESİN] Şartname: "Sistemin sadece hedeflerin yer alacağı tarafa bakmasına izin
verilecektir. Kesinlikle tanımlanan yasak bölgeye dönmesine izin verilmeyecek...
Bu atışa yasak alan ile karıştırılmamalıdır. Sistemlerin hem harekete yasak alan
hem de atışa yasak alan tanımlama fonksiyonlarının olması beklenmektedir."

MODEL (takım kararı 21.09.2026): operatör YASAK aralığı değil, İZİN VERİLEN
pencereyi yazar; pencerenin dışı yasaktır. Her eksende iki pencere vardır:
  * hareket penceresi — gimbal bu aralığın DIŞINA çıkamaz (sınırda KIRPILIR,
    komut reddedilmez: sınıra 3° kalmışken 5°'lik adım 3° gider),
  * atış penceresi   — lazer yalnız bu aralığın İÇİNDE açılabilir; dışına
    çıkılırsa ateş KESİLİR.
İkisi "harmanlıdır": atış penceresi hareket penceresinin dışına taşamaz
(`atis_uyumla`) — gidilemeyen yerde ateş izni anlamsızdır.

BİRİMLER (operatörün düşündüğü gibi):
  * Yatay (pan): ÖN = 0°, sağa +, sola − (−180..+180). Fiziksel sınır YOK, 360°
    döner; pencere ön taraf etrafında tanımlanır ki arkadan dolanıp yasak
    bölgeye girilemesin.
  * Dikey (tilt): FİZİKSEL açı, yere paralel = 0°, −30..+30. Ekranda/protokolde
    bu aralık 0..60 "sistem açısı" olarak görünür (sistem 0 = fiziksel −30).

Bu modül Qt'ye bağlı değildir: `python app/bolge.py` kendi testlerini koşar.
"""
from dataclasses import dataclass, field

# [KESİN — kullanıcı bilgisi 21.09.2026] dikey mekanik aralık toplam 60°:
TILT_FIZIKSEL_ALT = -30.0      # sistem 0° = namlu 30° AŞAĞI
TILT_ARALIK = 60.0             # sistem 0..60 = fiziksel −30..+30


def tilt_fiziksel(sistem):
    return float(sistem) + TILT_FIZIKSEL_ALT


def tilt_sistem(fiziksel):
    return float(fiziksel) - TILT_FIZIKSEL_ALT


def pan_isaretli(pan):
    """Herhangi bir azimut -> ön taraf etrafında işaretli açı (−180..+180)."""
    return ((float(pan) + 180.0) % 360.0) - 180.0


@dataclass
class Pencere:
    aktif: bool = False
    alt: float = -30.0
    ust: float = 30.0

    def icinde(self, x):
        return (not self.aktif) or (self.alt <= x <= self.ust)


@dataclass
class Bolgeler:
    hareket_pan: Pencere = field(default_factory=lambda: Pencere(False, -90.0, 90.0))
    hareket_tilt: Pencere = field(default_factory=lambda: Pencere(False, -30.0, 30.0))
    atis_pan: Pencere = field(default_factory=lambda: Pencere(False, -90.0, 90.0))
    atis_tilt: Pencere = field(default_factory=lambda: Pencere(False, -30.0, 30.0))


# durum kodları (arayüz şeridi bunlara göre renk/metin seçer)
SERBEST, KIRPILDI, ENGELLENDI = "serbest", "kirpildi", "engellendi"


def pencere_kirp(cur, hedef, alt, ust):
    """1 boyutlu hareketi [alt, ust] penceresine uydurur. Doner: (yeni, durum).

    İçerideyken: hedef sınırda kırpılır (asla dışarı çıkılmaz).
    Dışarıdayken (pencere yeni açıldıysa): yalnız pencereye DOĞRU harekete izin
    verilir — uzaklaşan komut engellenir, yaklaşan komut pencere içinde durur."""
    if alt <= cur <= ust:
        yeni = min(max(hedef, alt), ust)
        return yeni, (SERBEST if yeni == hedef else KIRPILDI)
    if cur < alt:
        if hedef <= cur:
            return cur, ENGELLENDI
        yeni = min(hedef, ust)
        return yeni, (SERBEST if yeni == hedef else KIRPILDI)
    if hedef >= cur:                                    # cur > ust
        return cur, ENGELLENDI
    yeni = max(hedef, alt)
    return yeni, (SERBEST if yeni == hedef else KIRPILDI)


def pan_hareket(pan_ham, d_pan, pencere):
    """Sarmasız azimut (karta giden) + delta -> (yeni_pan_ham, durum).

    Pencere ön taraf etrafında (−180..+180) tanımlıdır. Hareket işaretli açıda
    SÜREKLİ hesaplanır (sarmaz): pencere içinde kalan bir gimbal arkadan
    dolanarak yasak bölgeye geçemez."""
    if not pencere.aktif:
        return pan_ham + d_pan, SERBEST
    cur = pan_isaretli(pan_ham)
    yeni, durum = pencere_kirp(cur, cur + d_pan, pencere.alt, pencere.ust)
    return pan_ham + (yeni - cur), durum


def tilt_hareket(tilt_sistem_aci, d_tilt, pencere, sistem_max=TILT_ARALIK):
    """Sistem tilt'i (0..max) + delta -> (yeni_sistem_tilt, durum).
    Önce MEKANİK sınır (0..max, sessiz kırpma), sonra hareket penceresi
    (fiziksel açıyla)."""
    hedef = max(0.0, min(float(sistem_max), tilt_sistem_aci + d_tilt))
    if not pencere.aktif:
        return hedef, SERBEST
    cur_f = tilt_fiziksel(tilt_sistem_aci)
    yeni_f, durum = pencere_kirp(cur_f, tilt_fiziksel(hedef), pencere.alt, pencere.ust)
    return tilt_sistem(yeni_f), durum


def atis_izinli(pan, tilt_sistem_aci, b):
    """Şu anki yönde lazer açılabilir mi? (iki eksenin atış penceresi birlikte)"""
    return (b.atis_pan.icinde(pan_isaretli(pan))
            and b.atis_tilt.icinde(tilt_fiziksel(tilt_sistem_aci)))


def atis_uyumla(b):
    """"Harmanlama": atış penceresi hareket penceresinin dışına taşamaz.
    Hareket penceresi aktifken atış penceresi onun içine kırpılır. Kesişim boşsa
    atış penceresi tek noktaya iner (pratikte hiç ateş edilemez) — sessizce
    'her yer serbest'e dönmesinden güvenlidir."""
    for hareket, atis in ((b.hareket_pan, b.atis_pan), (b.hareket_tilt, b.atis_tilt)):
        if hareket.aktif and atis.aktif:
            atis.alt = max(atis.alt, hareket.alt)
            atis.ust = min(atis.ust, hareket.ust)
            if atis.alt > atis.ust:
                atis.ust = atis.alt
    return b


# =====================================================================
#  Kendi kendini test
# =====================================================================
if __name__ == "__main__":
    # birim dönüşümleri
    assert tilt_fiziksel(0) == -30 and tilt_fiziksel(60) == 30 and tilt_sistem(0) == 30
    assert pan_isaretli(350) == -10 and pan_isaretli(10) == 10 and pan_isaretli(-190) == 170

    # pencere içinde kırpma
    assert pencere_kirp(17, 22, -20, 20) == (20, KIRPILDI)
    assert pencere_kirp(0, 5, -20, 20) == (5, SERBEST)
    # dışarıdayken: uzaklaşma engellenir, yaklaşma serbest
    assert pencere_kirp(25, 30, -20, 20) == (25, ENGELLENDI)
    assert pencere_kirp(25, 18, -20, 20) == (18, SERBEST)

    # dikey: kullanıcının örneği — pencere −20..+20 (fiziksel) = sistem 10..50
    t = Pencere(True, -20.0, 20.0)
    assert tilt_hareket(40.0, 20.0, t) == (50.0, KIRPILDI)     # +10 → +20'de durur
    assert tilt_hareket(15.0, -10.0, t) == (10.0, KIRPILDI)    # −15 → −20'de durur
    assert tilt_hareket(30.0, 5.0, t) == (35.0, SERBEST)
    # mekanik sınır pencere kapalıyken de geçerli (0..60)
    assert tilt_hareket(55.0, 20.0, Pencere()) == (60.0, SERBEST)
    assert tilt_hareket(5.0, -20.0, Pencere()) == (0.0, SERBEST)

    # yatay: ön ±90 penceresi, sarma YOK (arkadan dolanamaz)
    p = Pencere(True, -90.0, 90.0)
    assert pan_hareket(80.0, 20.0, p) == (90.0, KIRPILDI)
    assert pan_hareket(-80.0, -20.0, p) == (-90.0, KIRPILDI)
    ham, d = pan_hareket(360.0 + 85.0, 10.0, p)                # tam tur sonrası da aynı
    assert (ham, d) == (450.0, KIRPILDI), (ham, d)
    # pencere kapalı: 360° serbest
    assert pan_hareket(350.0, 20.0, Pencere()) == (370.0, SERBEST)

    # atış: iki eksen birlikte
    b = Bolgeler()
    b.atis_pan = Pencere(True, -30.0, 30.0)
    b.atis_tilt = Pencere(True, -10.0, 10.0)
    assert atis_izinli(10.0, 30.0, b)           # pan +10, tilt fiziksel 0
    assert atis_izinli(350.0, 30.0, b)          # pan −10 (sarmalı gösterim)
    assert not atis_izinli(45.0, 30.0, b)       # pan dışarıda
    assert not atis_izinli(0.0, 50.0, b)        # tilt fiziksel +20 dışarıda

    # harmanlama: atış penceresi hareket penceresine kırpılır
    b = Bolgeler(hareket_tilt=Pencere(True, -20.0, 20.0), atis_tilt=Pencere(True, -30.0, 10.0))
    atis_uyumla(b)
    assert (b.atis_tilt.alt, b.atis_tilt.ust) == (-20.0, 10.0)
    b = Bolgeler(hareket_pan=Pencere(True, -10.0, 10.0), atis_pan=Pencere(True, 40.0, 60.0))
    atis_uyumla(b)
    assert b.atis_pan.alt == b.atis_pan.ust == 40.0             # kesişim yok -> tek nokta
    assert not atis_izinli(0.0, 30.0, b)

    print("bolge testleri OK — birimler, pencere kırpma, dikey/yatay hareket, "
          "sarma koruması, atış penceresi, harmanlama")
