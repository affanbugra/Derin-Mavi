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
  * Dikey (tilt): operatör çalışma açısı, −30..+30 (kol 0..60; 0 = kol 30).
    Kartın fiziksel 0..60 ham açısına dönüşüm yalnız tilt_surucu.py içinde yapılır.

Bu modül Qt'ye bağlı değildir: `python app/bolge.py` kendi testlerini koşar.
"""
from dataclasses import dataclass, field

# [KESİN — kullanıcı bilgisi 21.09.2026] dikey mekanik aralık toplam 60°:
TILT_FIZIKSEL_ALT = -30.0      # operatör alt sınırı
TILT_ARALIK = 60.0             # toplam mekanik hareket

# [KESİN — kullanıcı kararı 23.09.2026] GİZLİ SINIR YOK. Gimbali kısıtlayan her şey
# ARAYÜZDEKİ hareket/atış pencerelerinden gelir; kodun içinde operatörün görmediği
# açı yasağı, tavan ya da pay bulunmaz. Kodda kalan tek sınırlar FİZİKSEL olanlardır
# (dikey: kalibre edilmiş kol 0…60; yatay: işaretli azimutun tanım aralığı ±180).
# (22.09'daki "yatay ±60 yapısal sınır" pencere kapalıyken bile uygulanıyordu; artık
# yalnız pencerenin VARSAYILAN değeridir, arayüzde görünür ve değiştirilebilir.)
PAN_MAX = 180.0                # işaretli azimut aralığı: ön = 0°, sağa +, sola −
PAN_VARSAYILAN = 60.0          # hareket penceresinin açılış değeri (arayüzde görünür)
# DİKEY: kalibre edilmiş fiziksel aralığın TAMAMI (kol 0…60 = operatör −30…+30).
# 23.09 saha: ±25 sınırı + otonomda gizli tavan/pay yüzünden kol 10 m'deki hedefe
# çıkamadı (tilt tüm test boyunca +19.8'de, tavanda kaldı).
TILT_CALISMA_MIN = -30.0
TILT_CALISMA_MAX = 30.0


def tilt_fiziksel(operator_acisi):
    """Geriye uyumlu ad: arayüz ve fiziksel açı artık aynı çerçevededir."""
    return float(operator_acisi)


def tilt_sistem(fiziksel):
    return float(fiziksel)


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
    """Hazır ayarlar (takım kararı 22.09): pencereler KAPALI gelir ama kutular
    makul değerlerle dolu olur — operatör anahtarı açınca hemen kullanılabilir bir
    aralık bulur, sıfırdan sayı girmesi gerekmez.

    * hareket: yatay ±60 · dikey ±30 (arayüzde görünür, operatör değiştirebilir)
    * atış   : yatay ±30 · dikey ±15 — ateş alanı hareket alanından DAR başlar;
      güvenli taraf budur (gidilebilen her yere ateş izni vermek değil)."""
    hareket_pan: Pencere = field(default_factory=lambda: Pencere(True, -PAN_VARSAYILAN, PAN_VARSAYILAN))
    hareket_tilt: Pencere = field(default_factory=lambda: Pencere(True, TILT_CALISMA_MIN, TILT_CALISMA_MAX))
    atis_pan: Pencere = field(default_factory=lambda: Pencere(False, -30.0, 30.0))
    atis_tilt: Pencere = field(default_factory=lambda: Pencere(False, -15.0, 15.0))


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


def pan_hareket(pan_ham, d_pan, pencere, pan_max=PAN_MAX):
    """Sarmasız azimut (karta giden) + delta -> (yeni_pan_ham, durum).

    Önce YAPISAL sınır (±pan_max, sessiz kırpma — tilt'teki 0..60 ile aynı kural),
    sonra varsa operatörün hareket penceresi. Hareket işaretli açıda SÜREKLİ
    hesaplanır (sarmaz): gimbal arkadan dolanarak yasak bölgeye geçemez."""
    cur = pan_isaretli(pan_ham)
    # Kart açılışta pencere dışı bir açı bildirebilir. İlk küçük komutun hedefi
    # doğrudan ±60'a sıçramamalı; yalnız güvenli tarafa adım adım dönülebilir.
    if cur > pan_max:
        if d_pan >= 0:
            return pan_ham, ENGELLENDI
        hedef = max(pan_max, cur + d_pan)
        return pan_ham + (hedef - cur), KIRPILDI if hedef == pan_max else SERBEST
    if cur < -pan_max:
        if d_pan <= 0:
            return pan_ham, ENGELLENDI
        hedef = min(-pan_max, cur + d_pan)
        return pan_ham + (hedef - cur), KIRPILDI if hedef == -pan_max else SERBEST
    hedef = max(-pan_max, min(pan_max, cur + d_pan))
    if not pencere.aktif:
        return pan_ham + (hedef - cur), SERBEST
    yeni, durum = pencere_kirp(cur, hedef, pencere.alt, pencere.ust)
    return pan_ham + (yeni - cur), durum


def tilt_hareket(tilt_sistem_aci, d_tilt, pencere,
                 sistem_max=TILT_CALISMA_MAX, sistem_min=TILT_CALISMA_MIN):
    """Operatör tilt açısını mekanik ve izinli pencereye kırpar."""
    # Açılışta kol fiziksel -30'da olabilir. Kullanıcı bu konumdan daha aşağı
    # istemişse kırpma onu ters yönde -25'e yürütmesin; yalnız içeri dönüş serbest.
    if (tilt_sistem_aci < sistem_min and d_tilt <= 0) or (tilt_sistem_aci > sistem_max and d_tilt >= 0):
        return tilt_sistem_aci, ENGELLENDI
    hedef = max(float(sistem_min), min(float(sistem_max), tilt_sistem_aci + d_tilt))
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
    assert tilt_fiziksel(0) == 0 and tilt_fiziksel(-30) == -30 and tilt_sistem(30) == 30
    assert pan_isaretli(350) == -10 and pan_isaretli(10) == 10 and pan_isaretli(-190) == 170

    # pencere içinde kırpma
    assert pencere_kirp(17, 22, -20, 20) == (20, KIRPILDI)
    assert pencere_kirp(0, 5, -20, 20) == (5, SERBEST)
    # dışarıdayken: uzaklaşma engellenir, yaklaşma serbest
    assert pencere_kirp(25, 30, -20, 20) == (25, ENGELLENDI)
    assert pencere_kirp(25, 18, -20, 20) == (18, SERBEST)

    # dikey: pencere ve komut ayni operator acisinda
    t = Pencere(True, -20.0, 20.0)
    assert tilt_hareket(10.0, 20.0, t) == (20.0, KIRPILDI)
    assert tilt_hareket(-15.0, -10.0, t) == (-20.0, KIRPILDI)
    assert tilt_hareket(0.0, 5.0, t) == (5.0, SERBEST)
    # pencere kapalıyken yalnız FİZİKSEL aralık (−30..+30, kol 0..60) geçerli — gizli sınır yok
    assert tilt_hareket(20.0, 20.0, Pencere()) == (30.0, SERBEST)
    assert tilt_hareket(-20.0, -20.0, Pencere()) == (-30.0, SERBEST)
    assert tilt_hareket(-30.0, -1.0, Pencere()) == (-30.0, SERBEST)       # fiziksel uçta durur
    assert tilt_hareket(-30.0, 30.0, Pencere(True, -25.0, 25.0)) == (0.0, SERBEST)

    # yatay: pencere KAPALIYKEN gizli ±60 yok (23.09 kullanıcı kararı) — yalnız işaretli
    # azimutun tanım aralığı (±180): arkadan dolanıp tur atılmaz
    assert pan_hareket(50.0, 20.0, Pencere()) == (70.0, SERBEST)
    assert pan_hareket(-50.0, -20.0, Pencere()) == (-70.0, SERBEST)
    assert pan_hareket(170.0, 20.0, Pencere()) == (180.0, SERBEST)
    assert pan_hareket(-170.0, -30.0, Pencere()) == (-180.0, SERBEST)

    # yatay pencere: operatörün arayüzde yazdığı aralık uygulanır
    p = Pencere(True, -45.0, 45.0)
    assert pan_hareket(40.0, 20.0, p) == (45.0, KIRPILDI)
    assert pan_hareket(-40.0, -20.0, p) == (-45.0, KIRPILDI)
    ham, d = pan_hareket(360.0 + 40.0, 20.0, p)                # tam tur sonrası da aynı
    assert (ham, d) == (405.0, KIRPILDI), (ham, d)

    # hazır ayarlar: hareket sınırları açılışta etkin
    v = Bolgeler()
    assert v.hareket_pan.aktif and v.hareket_tilt.aktif
    assert not v.atis_pan.aktif and not v.atis_tilt.aktif
    assert (v.hareket_pan.alt, v.hareket_pan.ust) == (-PAN_VARSAYILAN, PAN_VARSAYILAN)
    assert (v.hareket_tilt.alt, v.hareket_tilt.ust) == (TILT_CALISMA_MIN, TILT_CALISMA_MAX)
    assert (v.atis_pan.alt, v.atis_pan.ust) == (-30.0, 30.0)
    assert (v.atis_tilt.alt, v.atis_tilt.ust) == (-15.0, 15.0)
    # atis alani hareket alanindan DAR baslamali (harmanlama sonrasi da bozulmamali)
    atis_uyumla(v)
    assert (v.atis_pan.alt, v.atis_pan.ust) == (-30.0, 30.0)

    # atış: iki eksen birlikte
    b = Bolgeler()
    b.atis_pan = Pencere(True, -30.0, 30.0)
    b.atis_tilt = Pencere(True, -10.0, 10.0)
    assert atis_izinli(10.0, 0.0, b)            # pan +10, tilt yatay
    assert atis_izinli(350.0, 0.0, b)           # pan −10 (sarmalı gösterim)
    assert not atis_izinli(45.0, 0.0, b)        # pan dışarıda
    assert not atis_izinli(0.0, 20.0, b)        # tilt +20 dışarıda

    # harmanlama: atış penceresi hareket penceresine kırpılır
    b = Bolgeler(hareket_tilt=Pencere(True, -20.0, 20.0), atis_tilt=Pencere(True, -30.0, 10.0))
    atis_uyumla(b)
    assert (b.atis_tilt.alt, b.atis_tilt.ust) == (-20.0, 10.0)
    b = Bolgeler(hareket_pan=Pencere(True, -10.0, 10.0), atis_pan=Pencere(True, 40.0, 60.0))
    atis_uyumla(b)
    assert b.atis_pan.alt == b.atis_pan.ust == 40.0             # kesişim yok -> tek nokta
    assert not atis_izinli(0.0, 0.0, b)

    print("bolge testleri OK — birimler, pencere kırpma, dikey/yatay hareket, "
          "sarma koruması, atış penceresi, harmanlama")
