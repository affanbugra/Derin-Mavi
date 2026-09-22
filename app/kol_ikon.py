# -*- coding: utf-8 -*-
"""Oyun kolu göstergesi — hangi tuşa basıldığı arayüzde yanar.

NEDEN ÇİZİM, NEDEN FOTOĞRAF DEĞİL: kolun ürün fotoğrafı beyaz/parlak, arayüz ise
koyu — yan yana sırıtır; ayrıca fotoğrafta **tek bir tuşu** yakamayız, oysa bu
göstergenin bütün amacı o. Şekil burada QPainter ile çizilir, her tuş ayrı bir
parçadır ve tek tek aydınlatılabilir.

TEK KAYNAK: gösterge KOMUT ÜRETMEZ, yalnız durumu gösterir. Işıklar arayüzün
kendi kapılarından (`_dpad_press`, `_ates_bas`, `_aci_reset`, `_estop_bas`) ve
gerçek gamepad okumasından beslenir — yani ekranda yanan tuş, sistemin gerçekten
aldığı komuttur (klavye, ekrandaki D-pad ve kol aynı ışığı yakar).

Düzen (CLAUDE.md §5.4, 22.09'da güncellendi):
    D-pad          → yön        · L2 + R2 (2 sn) → ateş aç, tekrar bas → kes
    L1 / R1 (2 sn) → merkeze al · Options        → ACİL DURDUR / DEVAM

Kendi kendini test:  python app/kol_ikon.py   (pencere açmaz)
"""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QTransform
from PySide6.QtWidgets import QWidget

import tasarim as T

# Çizim, 200 × 150'lik sabit bir tuvalde tanımlıdır; bileşen bunu kendi boyutuna
# ölçekler. Böyle yazmak ölçüleri okunur tutar (piksel yerine oran hesabı yok).
TUVAL = (200.0, 150.0)

GOVDE_UST = QRectF(24, 26, 152, 60)          # ana gövde
KOL_SOL = QRectF(34, 62, 42, 62)             # sol tutamak (aşağı-dışa eğik)
KOL_SAG = QRectF(124, 62, 42, 62)
KOL_ACI = 12.0                               # tutamakların dışa açılma açısı

# Tuşlar: ad -> (tip, ...). Tip "kutu" = yuvarlatılmış dikdörtgen, "daire" = çember.
# Adlar arayüzde kullanılan adlardır; yeni bir tuş eklenirse yalnız burası değişir.
TUSLAR = {
    # D-pad: kollar ORTADA BIRLESMEZ, aralarinda 1-2 px bosluk vardir — hangi kolun
    # yandigi boylece net okunur (gercek kolda tek parcadir, burada bilgi onceliklidir).
    "up":     ("kutu", QRectF(58.5, 36, 9, 13), 3),
    "down":   ("kutu", QRectF(58.5, 59, 9, 13), 3),
    "left":   ("kutu", QRectF(45, 49.5, 13, 9), 3),
    "right":  ("kutu", QRectF(68, 49.5, 13, 9), 3),
    "l1":     ("kutu", QRectF(36, 18, 32, 10), 5),
    "r1":     ("kutu", QRectF(132, 18, 32, 10), 5),
    "l2":     ("kutu", QRectF(40, 6, 26, 11), 5),
    "r2":     ("kutu", QRectF(134, 6, 26, 11), 5),
    "start":  ("kutu", QRectF(146, 34, 6, 11), 3),
    "ucgen":  ("daire", QPointF(140, 40), 6.0),
    "daire":  ("daire", QPointF(152, 52), 6.0),
    "capraz": ("daire", QPointF(140, 64), 6.0),
    "kare":   ("daire", QPointF(128, 52), 6.0),
    "sol_cubuk":  ("daire", QPointF(76, 86), 13.0),
    "sag_cubuk":  ("daire", QPointF(124, 86), 13.0),
}
DOKUNMATIK = QRectF(82, 38, 36, 28)          # orta dokunmatik yüzey (tuş değil)

# Sistemin gerçekten kullandığı tuşlar; kalanları soluk çizilir ki göz ilgisizleri
# aramasın (video anlatımında "bunlar çalışıyor" demek kolay olsun).
ETKIN = ("up", "down", "left", "right", "l1", "r1", "l2", "r2", "start")

ISIK_RENK = {"l2": T.KIRMIZI, "r2": T.KIRMIZI, "start": T.KIRMIZI}   # geri kalanı AKSAN


def isik_rengi(ad):
    return ISIK_RENK.get(ad, T.AKSAN)


def govde_yolu():
    """Kolun dış hattı: gövde + iki eğik tutamak (tek birleşik yol)."""
    yol = QPainterPath()
    yol.addRoundedRect(GOVDE_UST, 26, 26)
    for kutu, aci in ((KOL_SOL, -KOL_ACI), (KOL_SAG, KOL_ACI)):
        kol = QPainterPath()
        kol.addRoundedRect(kutu, 19, 19)
        merkez = QPointF(kutu.center().x(), kutu.top())
        d = (QTransform().translate(merkez.x(), merkez.y())
                         .rotate(aci).translate(-merkez.x(), -merkez.y()))
        yol = yol.united(d.map(kol))
    return yol.simplified()


class KolGostergesi(QWidget):
    """Oyun kolu resmi; `isik(ad, açık)` ile tuşlar yanar/söner."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._yanan = set()
        self._govde = govde_yolu()
        self.setAttribute(Qt.WA_TransparentForMouseEvents)   # tıklanmaz: gösterge
        self.setToolTip("Oyun kolu — D-pad: yön · L2+R2 (2 sn): ateş · "
                        "L1/R1 (2 sn): merkeze al · Options: ACİL DURDUR")

    def isik(self, ad, acik=True):
        if ad not in TUSLAR:
            return
        yeni = set(self._yanan)
        yeni.add(ad) if acik else yeni.discard(ad)
        if yeni != self._yanan:
            self._yanan = yeni
            self.update()

    def isiklari_ayarla(self, adlar):
        """Yanan tuş kümesini bir kerede kurar (gamepad okumasından)."""
        yeni = {a for a in adlar if a in TUSLAR}
        if yeni != self._yanan:
            self._yanan = yeni
            self.update()

    def hepsini_sondur(self):
        self.isiklari_ayarla(())

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        olcek = min(self.width() / TUVAL[0], self.height() / TUVAL[1])
        p.translate((self.width() - TUVAL[0] * olcek) / 2,
                    (self.height() - TUVAL[1] * olcek) / 2)
        p.scale(olcek, olcek)
        self.ciz(p, self._yanan)
        p.end()

    @staticmethod
    def ciz(p, yanan=()):
        """Saf çizim (bileşen gerektirmez, test edilebilir)."""
        # gövde
        p.setPen(QPen(_renk(T.KENAR_ISIK), 1.2))
        p.setBrush(_renk(T.D2))
        p.drawPath(govde_yolu())

        # dokunmatik yüzey (tuş değil, yalnız kolu tanıdık kılar)
        p.setPen(Qt.NoPen)
        p.setBrush(_renk(T.D3))
        p.drawRoundedRect(DOKUNMATIK, 5, 5)

        for ad, sekil in TUSLAR.items():
            acik = ad in yanan
            if acik:
                renk = QColor(isik_rengi(ad))
                kenar = QColor(renk)
            elif ad in ETKIN:
                renk, kenar = _renk(T.beyaz(0.22)), _renk(T.beyaz(0.30))
            else:
                renk, kenar = _renk(T.beyaz(0.07)), _renk(T.beyaz(0.10))
            if acik:                              # yumuşak hale: yanan tuş öne çıksın
                hale = QColor(renk)
                hale.setAlphaF(0.30)
                p.setPen(Qt.NoPen)
                p.setBrush(hale)
                _ciz_sekil(p, sekil, buyut=3.0)
            p.setPen(QPen(kenar, 1.0))
            p.setBrush(renk)
            _ciz_sekil(p, sekil)
        # çubukların içi (kolun kendi görünümü; komutla ilgisi yok)
        p.setPen(Qt.NoPen)
        p.setBrush(_renk(T.beyaz(0.05)))
        for ad in ("sol_cubuk", "sag_cubuk"):
            _, merkez, r = TUSLAR[ad]
            p.drawEllipse(merkez, r * 0.62, r * 0.62)


def _renk(metin):
    """tasarim.py'nin 'rgba(r, g, b, a)' metnini QColor'a çevirir (tek kaynak korunur)."""
    if metin.startswith("rgba"):
        r, g, b, a = [float(x) for x in metin[metin.index("(") + 1:metin.index(")")].split(",")]
        c = QColor(int(r), int(g), int(b))
        c.setAlphaF(a)
        return c
    return QColor(metin)


def _ciz_sekil(p, sekil, buyut=0.0):
    tip = sekil[0]
    if tip == "kutu":
        _, kutu, yc = sekil
        k = kutu.adjusted(-buyut, -buyut, buyut, buyut)
        p.drawRoundedRect(k, yc + buyut, yc + buyut)
    else:
        _, merkez, r = sekil
        p.drawEllipse(merkez, r + buyut, r + buyut)


# =====================================================================
#  Kendi kendini test (pencere AÇMAZ)
# =====================================================================
if __name__ == "__main__":
    # 1. Sistemin kullandigi her tus cizimde var mi? (biri unutulursa arayuz o tusu
    #    yakmak ister ama ekranda karsiligi olmaz — sessiz bir bosluk olurdu)
    for ad in ETKIN:
        assert ad in TUSLAR, f"cizimde yok: {ad}"

    # 2. Her sekil tuvalin icinde mi? (disina tasan tus kirpilir, gorunmez)
    for ad, sekil in TUSLAR.items():
        if sekil[0] == "kutu":
            k = sekil[1]
            kutu = QRectF(k)
        else:
            m, r = sekil[1], sekil[2]
            kutu = QRectF(m.x() - r, m.y() - r, 2 * r, 2 * r)
        assert 0 <= kutu.left() and kutu.right() <= TUVAL[0], (ad, kutu)
        assert 0 <= kutu.top() and kutu.bottom() <= TUVAL[1], (ad, kutu)

    # 3. Tuslar birbirinin uzerine binmemeli (binen iki tus tek tus gibi gorunur)
    def kutula(s):
        if s[0] == "kutu":
            return QRectF(s[1])
        return QRectF(s[1].x() - s[2], s[1].y() - s[2], 2 * s[2], 2 * s[2])

    adlar = list(TUSLAR)
    for i, a in enumerate(adlar):
        for b in adlar[i + 1:]:
            ortak = kutula(TUSLAR[a]).intersected(kutula(TUSLAR[b]))
            assert ortak.isEmpty(), f"ust uste binen tuslar: {a} / {b}"

    # 4. Govde yolu tuslari kapsamali (tuslar govdenin disinda kalmamali); ust
    #    omuz tuslari (L1/L2/R1/R2) bilincli olarak govdenin USTUNDE durur.
    govde = govde_yolu().boundingRect()
    for ad in ("up", "down", "left", "right", "start"):
        assert govde.contains(kutula(TUSLAR[ad])), f"govdenin disinda: {ad}"

    # 5. Renk cevirici tasarim.py metinlerini anlamali
    c = _renk(T.beyaz(0.5))
    assert (c.red(), c.green(), c.blue()) == (255, 255, 255) and abs(c.alphaF() - 0.5) < 0.01
    assert _renk(T.AKSAN).name().lower() == T.AKSAN.lower()

    print("kol_ikon testleri OK — tus listesi, tuval siniri, cakisma, govde, renk")
