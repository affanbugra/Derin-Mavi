# -*- coding: utf-8 -*-
"""Klavye ve oyun kolu kontrolleri — TEK KAYNAK.

Arayuzdeki "Kontroller" penceresi bu tablolari gosterir. Amac: hangi tusun ne is
yaptigi unutulmasin, video anlatiminda (sartname Yetenek 1) okunacak liste hazir olsun.

⚠ BIR KONTROLU DEGISTIRDIYSEN BURAYI DA DEGISTIR. Bu dosya komut URETMEZ, yalniz
  anlatir; gercek davranis `arayuz_qt.py` (klavye) ve `gamepad.py` (kol) icindedir.
  Ikisi ayrilirsa kapi testi kirmiziya duser:
    * `python app/kontroller.py`             — kol tablosu <-> gamepad.py / kol_ikon.py
    * `python app/kapi_testleri_arayuz.py`   — klavye tablosu <-> arayuz_qt.py tuslari

Kendi kendini test:  python app/kontroller.py   (pencere acmaz)
"""
from html import escape

from PySide6.QtCore import Qt

import tasarim as T

# Satir: (tuslar, is, aciklama, Qt tuslari). Qt tuslari, testin arayuzun gercekten
# dinledigi tuslarla karsilastirmasi icindir.
KLAVYE = (
    (("W", "↑"), "Yukarı", "Kısa dokunuş 1°, basılı tutunca sürekli. Yalnız Manuel mod.",
     (Qt.Key_W, Qt.Key_Up)),
    (("S", "↓"), "Aşağı", "Kısa dokunuş 1°, basılı tutunca sürekli. Yalnız Manuel mod.",
     (Qt.Key_S, Qt.Key_Down)),
    (("A", "←"), "Sola", "Kısa dokunuş 1°, basılı tutunca sürekli. Yalnız Manuel mod.",
     (Qt.Key_A, Qt.Key_Left)),
    (("D", "→"), "Sağa", "Kısa dokunuş 1°, basılı tutunca sürekli. Yalnız Manuel mod.",
     (Qt.Key_D, Qt.Key_Right)),
    (("R",), "Merkeze al", "0° / 0°'a motor hızıyla kademeli döner; yön tuşu keser. "
     "Yalnız Manuel mod.", (Qt.Key_R,)),
    (("Space + B",), "Ateş aç / kes", "İkisi birlikte, her modda. Tek tuş bir şey yapmaz. "
     "ACİL DURDUR'da ve atışa yasak alanda açılmaz.", (Qt.Key_Space, Qt.Key_B)),
    (("Z",), "Yakınlaştır", "Basılı tuttukça, en çok 4×. Yalnız Manuel + Aşama 1; "
     "yalnız ekran.", (Qt.Key_Z,)),
    (("X",), "Uzaklaştır", "Basılı tuttukça, 1×'e (eski hâline) kadar. Yalnız Manuel + "
     "Aşama 1.", (Qt.Key_X,)),
    (("Esc",), "ACİL DURDUR", "Her modda, her durumda; ateş de kesilir. Yalnız durdurur — "
     "devam için ekrandaki DEVAM ET butonu.", (Qt.Key_Escape,)),
)

# Satir: (kol_ikon adlari, tus, is, aciklama). is = None -> tus BOS (bir sey yapmaz).
# Adlar kol_ikon.TUSLAR'daki adlardir; test, is'i olanlarin kol_ikon.ETKIN ile ayni
# oldugunu denetler (ekranda yanan tus = tabloda yazan tus).
KOL = (
    (("sol_cubuk",), "Sol joystick", "Yatay + dikey",
     "Analog: ne kadar itersen o kadar hızlı. Bırakınca yumuşak durur."),
    (("up", "down", "left", "right"), "D-pad", "Yön",
     "Tam hızla tek yön. Joystick hareketliyken yok sayılır."),
    (("l2", "r2"), "L2 + R2", "Ateş aç / kes",
     "İkisi birlikte, tek dokunuş. Tek tetik bir şey yapmaz."),
    (("l1", "r1"), "L1 + R1", "Merkeze al",
     "İkisi birlikte; 0° / 0°'a kademeli. Tek tuş bir şey yapmaz."),
    (("start",), "Options / Start", "ACİL DURDUR", "Yalnız durdurur; devam ekrandan."),
    (("sag_cubuk",), "Sağ joystick", "Zoom",
     "Yalnız Manuel + Aşama 1. Yukarı yakınlaştırır (en çok 4×), aşağı 1×'e kadar "
     "uzaklaştırır. Yalnız ekran — gimbal'i ve otonomu etkilemez."),
    (("capraz", "daire", "kare", "ucgen"), "Çarpı / Daire / Kare / Üçgen", None, ""),
)

# Kısayolu olmayan, yalniz ekrandan yapilan isler (unutulmasin diye listede).
EKRAN = (
    ("DEVAM ET", "ACİL DURDUR'dan çıkış YALNIZ bu butonla. Donanım butonu basılıyken olmaz."),
    ("ATEŞ butonu", "Space + B ile aynı kapı."),
)


def _tus(ad):
    return (f"<span style='background:{T.D2}; color:{T.L1}; border-radius:4px;"
            f" font-family:{T.FM}; padding:1px 6px;'>&nbsp;{escape(ad)}&nbsp;</span>")


def _tablo(satirlar):
    govde = "".join(
        f"<tr><td style='padding:5px 14px 5px 0; white-space:nowrap;'>{tus}</td>"
        f"<td style='padding:5px 14px 5px 0; white-space:nowrap; color:{renk};'>"
        f"<b>{escape(is_)}</b></td>"
        f"<td style='padding:5px 0; color:{T.L2};'>{escape(aciklama)}</td></tr>"
        for tus, is_, aciklama, renk in satirlar)
    return f"<table cellspacing='0' cellpadding='0'>{govde}</table>"


def _renk(is_):
    if is_ is None:
        return T.L3
    return T.KIRMIZI if ("ATEŞ" in is_.upper() or "DURDUR" in is_.upper()) else T.L1


def html():
    """Kontroller penceresinin metni (Qt zengin metin)."""
    klavye = [(" ".join(_tus(t) for t in tuslar), is_, aciklama, _renk(is_))
              for tuslar, is_, aciklama, _ in KLAVYE]
    kol = [(_tus(tus), is_ or "— boş", aciklama, _renk(is_))
           for _, tus, is_, aciklama in KOL]
    ekran = [(_tus(ad), "", aciklama, T.L1) for ad, aciklama in EKRAN]
    baslik = (f"<p style='color:{T.L2}; font-size:11px; letter-spacing:0.6px;"
              f" margin:14px 0 4px 0;'>{{}}</p>")
    return (baslik.format("KLAVYE") + _tablo(klavye)
            + baslik.format("OYUN KOLU") + _tablo(kol)
            + baslik.format("YALNIZ EKRANDAN") + _tablo(ekran))


def klavye_tuslari():
    """Tablodaki tum Qt tuslari (test arayuzun dinledikleriyle karsilastirir)."""
    return {k for *_, tuslar in KLAVYE for k in tuslar}


if __name__ == "__main__":
    import gamepad as G
    import kol_ikon as KI

    # 1. Kol tablosundaki her ad ekrandaki kol resminde var; her ad bir kez gecer.
    adlar = [ad for satir in KOL for ad in satir[0]]
    assert len(adlar) == len(set(adlar)), "kol tablosunda ayni tus iki kez"
    for ad in adlar:
        assert ad in KI.TUSLAR, f"kol resminde yok: {ad}"

    # 2. Is'i olan tuslar = ekranda etkin (parlak) cizilen tuslar. Biri degisip oteki
    #    unutulursa pencere "bos" derken resim tusu yakar (ya da tersi).
    etkin = {ad for adlar_, _, is_, _ in KOL if is_ for ad in adlar_}
    assert etkin == set(KI.ETKIN), f"tablo / kol_ikon.ETKIN ayrisiyor: {etkin ^ set(KI.ETKIN)}"

    # 3. Cubuk duzeni gamepad.py ile ayni: iki eksen SOL cubukta, sag cubuk Y = zoom.
    if G.PYGAME_VAR:
        import pygame
        assert G.CB_EKSEN_PAN == pygame.CONTROLLER_AXIS_LEFTX
        assert G.CB_EKSEN_TILT == pygame.CONTROLLER_AXIS_LEFTY, "dikey sol cubukta degil"
        assert G.CB_EKSEN_ZOOM == pygame.CONTROLLER_AXIS_RIGHTY, "zoom sag cubuk Y degil"
    assert (G.EKSEN_PAN, G.EKSEN_TILT) == (0, 1), "ham yol: dikey sol cubuk Y (1) olmali"

    # 4. Tabloda yazan is, gamepad.Durum'un gercek karariyla ayni: ACIL DURDUR / merkez
    #    yalniz tabloda oyle yazan tus(lar)la tetiklenir (ornek: Daire artik durdurmaz).
    for adlar_, tus, is_, _ in KOL:
        d = G.Durum()
        d.basili, d.kenar = set(adlar_), set(adlar_)
        assert d.estop == (is_ == "ACİL DURDUR"), f"{tus}: tablo ile acil durdur ayrisiyor"
        assert d.merkez == (is_ == "Merkeze al"), f"{tus}: tablo ile merkez ayrisiyor"
        assert d.ates_kenar == (is_ == "Ateş aç / kes"), f"{tus}: tablo ile ates ayrisiyor"

    # 5. HTML uretilir ve her tus/is metinde gecer.
    h = html()
    for tuslar, is_, _, _ in KLAVYE:
        assert escape(is_) in h and all(escape(t) in h for t in tuslar)
    for _, tus, _, _ in KOL:
        assert escape(tus) in h
    print("kontroller testleri OK — kol tablosu <-> kol_ikon/gamepad, html")
