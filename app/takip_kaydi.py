# -*- coding: utf-8 -*-
"""DERIN MAVI — TAKIP KARA KUTUSU: otonom takip dongusunun her karesini diske yazar.

NEDEN. Sahada "takip kotu" demek kolay, NEDEN kotu oldugunu soylemek zor: kutu mu
titriyor, ppd mi yanlis, gecikme mi telafi edilmiyor, kilit mi atliyor? Bunlarin
hepsi ayni belirtiyi (salinim + geriden gelme) uretir ve hicbiri ekrana bakarak
ayirt edilemez. Bu modul her otonom karede TEK SATIR yazar; `takip_analiz.py`
o satirlardan ppd'yi ve toplam gecikmeyi OLCER, salinimi sayar.

TASARIM KURALLARI
  * Takibi ASLA bozmaz: her yazma try/except icinde, hata sessizce yutulur ve
    kayit kapanir (bir log dosyasi ugruna gorev kaybedilmez).
  * Ana is parcaciginda cagrilir ama diske yazma AYRI bir is parcaciginda olur;
    kuyruk dolarsa en eski satir dusurulur (kayit gecikmeyi BUYUTMEZ).
  * Dosya `loglar/takip_<tarih>.csv`. Repoya girmez (.gitignore).
  * Baslik SABIT: analiz araci sutun adina gore okur, sirasina gore degil.

Kendi kendini test:  python app/takip_kaydi.py   (gecici dizine yazar, siler)
"""
import os
import queue
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_DIZIN = os.path.join(os.path.dirname(HERE), "loglar")

# Kuyruk tavani: ~30 sn'lik kare (60 FPS). Dolarsa en eski satir atilir — kayit
# yuzunden takip yavaslamaz. Dusen satir sayisi dosya sonuna not dusulur.
KUYRUK_TAVANI = 2000
YAZMA_ARALIGI = 0.5        # sn — bu kadarda bir diske flush (cokmede veri kaybi sinirli)

SUTUNLAR = [
    "t",             # kaydin yazildigi an (time.time)
    "t_kare",        # karenin YAKALANDIGI an (kamera zaman damgasi)
    "gecikme_ms",    # t - t_kare: kare yakalandi -> komut uretildi
    "kip",           # yorunge | konum | pd
    "kaynak",        # model | renk | roi | hayalet | yok
    "id", "conf",
    "x1", "y1", "x2", "y2",
    "nisan_x", "nisan_y",
    "ex_px", "ey_px", "olu_x_px", "olu_y_px", "kare_w", "kare_h",
    "pan_kare", "tilt_kare",        # eksenin KARE ANINDAKI acisi (kartin bildirdigi)
    "pan_simdi", "tilt_simdi",      # eksenin SU ANKI acisi
    "ppd",                          # o karede kullanilan piksel/derece
    "kest_pan", "kest_pan_hiz",     # kestiricinin dunya acisi + acisal hizi
    "kest_tilt", "kest_tilt_hiz",
    "kom_pan", "kom_pan_hiz",       # karta giden komut (mutlak aci / hiz)
    "kom_tilt", "kom_tilt_hiz",
    "engel",                        # komut gitmediyse sebebi
    "fps",
]


class TakipKaydi:
    """Tek dosyalik, is parcacigi guvenli CSV kaydi."""

    def __init__(self, dizin=None, on_ek=""):
        self.dizin = LOG_DIZIN if dizin is None else dizin
        self.on_ek = on_ek
        self.yol = None
        self._kuyruk = queue.Queue(maxsize=KUYRUK_TAVANI)
        self._is = None
        self._calis = False
        self._dusen = 0
        self.satir_sayisi = 0
        self.hata = None

    # ---- yasam dongusu -------------------------------------------------
    def baslat(self):
        if self._calis:
            return True
        try:
            os.makedirs(self.dizin, exist_ok=True)
            ad = f"takip_{self.on_ek}{time.strftime('%Y%m%d_%H%M%S')}.csv"
            self.yol = os.path.join(self.dizin, ad)
            self._dosya = open(self.yol, "w", encoding="utf-8", newline="")
            self._dosya.write(",".join(SUTUNLAR) + "\n")
        except Exception as e:                  # disk dolu, izin yok...
            self.hata = str(e)
            self.yol = None
            return False
        self._calis = True
        self._is = threading.Thread(target=self._dongu, name="takip_kaydi", daemon=True)
        self._is.start()
        return True

    def kapat(self):
        if not self._calis:
            return
        self._calis = False
        try:
            self._kuyruk.put_nowait(None)       # uyandirma isareti
        except queue.Full:
            pass
        if self._is is not None:
            self._is.join(timeout=2.0)
        self._is = None

    # ---- yazma ---------------------------------------------------------
    def yaz(self, **alanlar):
        """Bir kare satiri. Bilinmeyen alan bos birakilir; fazladan alan YOK SAYILMAZ,
        sessizce atilir (sutun listesi analiz aracinin sozlesmesidir)."""
        if not self._calis:
            return
        try:
            self._kuyruk.put_nowait(alanlar)
        except queue.Full:
            # En eskiyi at, yenisini koy: son saniyeler her zaman daha degerlidir.
            try:
                self._kuyruk.get_nowait()
                self._kuyruk.put_nowait(alanlar)
                self._dusen += 1
            except queue.Empty:
                pass

    def _dongu(self):
        son_flush = time.time()
        try:
            while True:
                try:
                    kayit = self._kuyruk.get(timeout=0.2)
                except queue.Empty:
                    kayit = None
                    if not self._calis:
                        break
                if kayit is not None:
                    self._dosya.write(self._satir(kayit))
                    self.satir_sayisi += 1
                simdi = time.time()
                if simdi - son_flush >= YAZMA_ARALIGI:
                    self._dosya.flush()
                    son_flush = simdi
                if not self._calis and self._kuyruk.empty():
                    break
        except Exception as e:
            self.hata = str(e)
        finally:
            try:
                if self._dusen:
                    self._dosya.write(f"# dusen_satir,{self._dusen}\n")
                self._dosya.flush()
                self._dosya.close()
            except Exception:
                pass

    @staticmethod
    def _satir(alanlar):
        parcalar = []
        for ad in SUTUNLAR:
            v = alanlar.get(ad)
            if v is None:
                parcalar.append("")
            elif isinstance(v, float):
                parcalar.append(f"{v:.4f}")
            else:
                s = str(v)
                parcalar.append(s.replace(",", ";") if "," in s else s)
        return ",".join(parcalar) + "\n"


# Uygulama tek kayit tutar (arayuz_qt bunu kullanir).
_kayit = None


def kaydi_al():
    return _kayit


def baslat(dizin=None, on_ek=""):
    """Kaydi baslatir (zaten acikra ayni kayit doner). Doner: TakipKaydi ya da None."""
    global _kayit
    if _kayit is not None and _kayit._calis:
        return _kayit
    k = TakipKaydi(dizin=dizin, on_ek=on_ek)
    _kayit = k if k.baslat() else None
    return _kayit


def kapat():
    global _kayit
    if _kayit is not None:
        _kayit.kapat()
        _kayit = None


def yaz(**alanlar):
    if _kayit is not None:
        _kayit.yaz(**alanlar)


if __name__ == "__main__":
    import shutil
    import tempfile

    gecici = tempfile.mkdtemp()
    try:
        k = TakipKaydi(dizin=gecici, on_ek="test_")
        assert k.baslat(), k.hata
        k.yaz(t=1.0, t_kare=0.95, kip="yorunge", kaynak="model", ex_px=12.5,
              bilinmeyen_alan="atilmali")
        k.yaz(t=2.0, kaynak="renk", engel="olu bolge, durdu")     # virgullu metin
        k.kapat()
        satirlar = open(k.yol, encoding="utf-8").read().strip().split("\n")
        assert satirlar[0] == ",".join(SUTUNLAR)
        assert len(satirlar) == 3, satirlar
        ilk = dict(zip(SUTUNLAR, satirlar[1].split(",")))
        assert ilk["kip"] == "yorunge" and ilk["ex_px"] == "12.5000", ilk
        assert ilk["kest_pan"] == "", "bilinmeyen alan bos kalmali"
        # Virgul sutunlari kaydirmamali (analiz araci sutun sayar)
        assert len(satirlar[2].split(",")) == len(SUTUNLAR), satirlar[2]
        assert "olu bolge; durdu" in satirlar[2]

        # KAYIT TAKIBI BOZMAZ: kuyruk dolsa bile yaz() beklemez ve patlamaz.
        k2 = TakipKaydi(dizin=gecici, on_ek="dolu_")
        assert k2.baslat()
        k2._calis = True
        for i in range(KUYRUK_TAVANI + 50):       # yazici is parcacigi yetismese bile
            k2.yaz(t=float(i))
        k2.kapat()
        assert k2.hata is None

        # Dizin yazilamazsa uygulama devam etmeli (kayit sessizce kapali)
        k3 = TakipKaydi(dizin="/olmayan/kok/dizin")
        assert k3.baslat() is False and k3.yol is None
        k3.yaz(t=1.0)                              # patlamamali
        print("takip_kaydi testleri OK — baslik, alan esleme, virgul, dolu kuyruk, yazilamayan dizin")
    finally:
        shutil.rmtree(gecici, ignore_errors=True)
