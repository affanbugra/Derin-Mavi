# -*- coding: utf-8 -*-
"""USB gamepad okuyucu — manuel kontrolun UCUNCU girdisi (D-pad ve klavyeden sonra).

Sartname Yetenek 1 kullanici komut arayuzlerini "UI/joystick/klavye" diye sayar; joystick
video icin dogrudan puandir (CLAUDE.md §2).

⚠ BU MODUL KOMUT URETMEZ, YALNIZCA OKUR. Arayuz okunan durumu kendi guvenlik kapilarindan
  gecirir (`_aci_hareket`, `_ates_bas`, `_estop_bas`). Gamepad'in kendi yolu OLMAMALIDIR:
  gecmiste ikinci bir ates yolu acilmis ve E-Stop denetimini atlamisti (CLAUDE.md §12 B1).

⚠ DONANIM-BAGIMSIZ (CLAUDE.md ilke 7): pygame kurulu degilse ya da cihaz takili degilse
  ozellik sessizce KAPALI kalir — uygulama yine acilir, klavye/D-pad calismaya devam eder.
  Cihaz calisirken cikarilirsa okuma durur, arayuz kilitlenmez.

Kendi kendine test:  python app/gamepad.py   (cihaz yoksa da calisir, "yok" der)
"""
import os

# pygame bir SDL penceresi ACMAMALI: bu bir arayuz uygulamasi, ikinci bir pencere
# (ya da gorunmez bir video baglami) Qt ile cakisir.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
# pygame acilista konsola "Hello from the pygame community" banner'i basar; bu uygulama
# Baslat.bat'tan calisiyor ve o pencerede yalnizca BIZIM mesajlarimiz olmali.
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

try:
    import pygame
    PYGAME_VAR = True
except ImportError:                       # kutuphane yok -> ozellik kapali, uygulama calisir
    pygame = None
    PYGAME_VAR = False

try:                                      # SDL GameController API (tercih edilen — asagi bak)
    from pygame._sdl2 import controller as sdl_controller
    CONTROLLER_VAR = PYGAME_VAR
except Exception:
    sdl_controller = None
    CONTROLLER_VAR = False


# ---- Ayarlar ----
# Analog cubuk merkezde dururken bile ±0.05-0.10 gurultu uretir. Olu bolge olmazsa
# gimbal hic durmaz, surekli suruklenir (ve ates sirasinda nisan kayar).
OLU_BOLGE = 0.15

# ⚠ IKI OKUMA YOLU VAR, SIRA ONEMLI:
#
# 1) SDL **GameController** (tercih): SDL'in kendi cihaz veritabani (gamecontrollerdb)
#    her padi standart bir duzene esler — A tusu hangi padde olursa olsun A'dir.
# 2) SDL **Joystick** (yedek): SDL cihazi tanimiyorsa HAM numaralar gelir.
#
# Neden onemli: ham numaralar padden pade DEGISIR. Xbox/XInput duzeninde 7 = Start iken
# PlayStation DualSense'te 7 = R2'dir. Sabit numara yazsaydik ACIL DURDUR baska bir pad
# takildiginda yanlis tusa duserdi — kabul edilemez.
if PYGAME_VAR:
    CB_ATES = pygame.CONTROLLER_BUTTON_A                # atesi ac/kes (ATES butonuyla ayni)
    CB_MERKEZ = pygame.CONTROLLER_BUTTON_Y              # merkeze al (0°, 0°)
    CB_ESTOP = pygame.CONTROLLER_BUTTON_START           # ACIL DURDUR / DEVAM
    CB_HIZ_ASAGI = pygame.CONTROLLER_BUTTON_LEFTSHOULDER
    CB_HIZ_YUKARI = pygame.CONTROLLER_BUTTON_RIGHTSHOULDER
    CB_EKSEN_PAN = pygame.CONTROLLER_AXIS_LEFTX
    CB_EKSEN_TILT = pygame.CONTROLLER_AXIS_LEFTY
    # GameController'da D-pad ayri bir "hat" degil, dort dugmedir.
    CB_DPAD = ((pygame.CONTROLLER_BUTTON_DPAD_UP, 0.0, 1.0),
               (pygame.CONTROLLER_BUTTON_DPAD_DOWN, 0.0, -1.0),
               (pygame.CONTROLLER_BUTTON_DPAD_LEFT, -1.0, 0.0),
               (pygame.CONTROLLER_BUTTON_DPAD_RIGHT, 1.0, 0.0))
    # GameController eksenleri -32768..32767 tam sayi doner (joystick'te -1..1 float).
    CB_EKSEN_OLCEK = 32767.0

# Yedek yol: ham Joystick numaralari (Xbox/XInput duzeni varsayilir).
# `python app/gamepad.py` hangi dugmenin hangi numara oldugunu canli gosterir.
BTN_ATES = 0          # A
BTN_MERKEZ = 3        # Y
BTN_HIZ_ASAGI = 4     # LB
BTN_HIZ_YUKARI = 5    # RB
BTN_ESTOP = 7         # Start/Menu

# Sol analog cubuk. Y ekseni SDL'de yukari = NEGATIF; tilt'te yukari = ARTI oldugu icin
# isaret cevrilir (yoksa cubugu yukari itince namlu asagi inerdi).
EKSEN_PAN = 0
EKSEN_TILT = 1


def _olu_bolge(v):
    """Olu bolgeyi uygular ve KALAN araligi yeniden 0..1'e yayar.

    Duz kesme (|v|<esik -> 0) yapilsaydi cubuk esigi gectigi anda hiz 0'dan 0.15'e
    sicrardi; yeniden olcekleme sayesinde hareket sifirdan yumusak baslar."""
    if abs(v) < OLU_BOLGE:
        return 0.0
    isaret = 1.0 if v > 0 else -1.0
    return isaret * min(1.0, (abs(v) - OLU_BOLGE) / (1.0 - OLU_BOLGE))


class Durum:
    """Bir yoklamanin sonucu. Eksenler -1..1, dugmeler KENAR TETIKLI (basildigi an True).

    Neden kenar tetikli: ates/E-Stop birer ac-kapa. Seviye okunsaydi dugme basili
    tutuldugu surece her yoklamada (50 ms) tekrar tetiklenir, lazer yanip sonerdi."""

    __slots__ = ("pan", "tilt", "ates", "estop", "merkez", "hiz_yukari", "hiz_asagi")

    def __init__(self):
        self.pan = 0.0
        self.tilt = 0.0
        self.ates = False
        self.estop = False
        self.merkez = False
        self.hiz_yukari = False
        self.hiz_asagi = False

    @property
    def hareket_var(self):
        return self.pan != 0.0 or self.tilt != 0.0


class Gamepad:
    """Tek bir USB gamepad. Cihaz yoksa `bagli` False'tur ve `oku()` bos durum verir."""

    def __init__(self):
        self.js = None             # ham Joystick (yedek yol)
        self.ctrl = None           # SDL GameController (tercih edilen yol)
        self.ad = ""
        self.hata = None
        self._onceki = {}          # dugme no -> onceki basili durumu (kenar tespiti)
        if not PYGAME_VAR:
            self.hata = "pygame kurulu değil (pip install pygame)"
            return
        try:
            pygame.init()
            pygame.joystick.init()
            if CONTROLLER_VAR:
                sdl_controller.init()
        except Exception as e:
            self.hata = f"pygame başlatılamadı: {e}"
            return
        self.tara()

    # ---- baglanti ----
    @property
    def bagli(self):
        return self.ctrl is not None or self.js is not None

    @property
    def standart_harita(self):
        """True ise dugmeler SDL tarafindan standarda eslendi (her padde ayni)."""
        return self.ctrl is not None

    def tara(self):
        """Takili ilk gamepad'i acar. Uygulama calisirken cagirilabilir (tak-calistir).

        Once GameController denenir (standart harita), olmazsa ham Joystick'e dusulur."""
        if not PYGAME_VAR:
            return False
        self.ctrl = self.js = None
        self._onceki.clear()
        try:
            pygame.joystick.quit()      # cihaz listesini tazele (sicak takma icin sart)
            pygame.joystick.init()
            if pygame.joystick.get_count() == 0:
                self.ad = ""
                self.hata = "gamepad takılı değil"
                return False

            if CONTROLLER_VAR:
                try:
                    sdl_controller.quit()
                    sdl_controller.init()
                    for i in range(pygame.joystick.get_count()):
                        if sdl_controller.is_controller(i):
                            self.ctrl = sdl_controller.Controller(i)
                            self.ad = self.ctrl.name or "Gamepad"
                            self.hata = None
                            return True
                except Exception:
                    self.ctrl = None    # tanimadi -> ham joystick'e dus

            self.js = pygame.joystick.Joystick(0)
            self.js.init()
            self.ad = self.js.get_name()
            self.hata = None
            return True
        except Exception as e:
            self.ctrl = self.js = None
            self.ad = ""
            self.hata = f"gamepad açılamadı: {e}"
            return False

    def _kenar(self, no, basili):
        """Dugme BU yoklamada basildi mi? (basili tutmak tekrar tetiklemez)"""
        onceki = self._onceki.get(no, False)
        self._onceki[no] = basili
        return basili and not onceki

    # ---- okuma ----
    def oku(self):
        """Gamepad'in o anki durumu. Cihaz yoksa/koptuysa BOS durum doner (hareket yok).

        Kopan cihazda istisna firlatmayiz: arayuz timer'i bunu 50 ms'de bir cagiriyor,
        tek bir kopma tum arayuzu hataya dusurmemeli."""
        d = Durum()
        if not self.bagli:
            return d
        try:
            pygame.event.pump()             # SDL durumunu tazele (bu olmadan degerler donar)
            if self.ctrl is not None:
                self._oku_controller(d)
            else:
                self._oku_joystick(d)
        except Exception:
            self.ctrl = self.js = None
            self.hata = "gamepad bağlantısı koptu"
            return Durum()
        return d

    def _oku_controller(self, d):
        """SDL GameController yolu — dugme duzeni SDL tarafindan standarda eslenmis."""
        c = self.ctrl
        d.pan = _olu_bolge(c.get_axis(CB_EKSEN_PAN) / CB_EKSEN_OLCEK)
        d.tilt = -_olu_bolge(c.get_axis(CB_EKSEN_TILT) / CB_EKSEN_OLCEK)

        # D-pad analog cubukla AYNI alanlari besler: hassas nisan icin dijital yon cogu
        # zaman cubuktan kolaydir. Cubuk zaten hareketliyse D-pad yok sayilir.
        if not d.hareket_var:
            for btn, kpan, ktilt in CB_DPAD:
                if c.get_button(btn):
                    d.pan, d.tilt = kpan, ktilt
                    break

        d.ates = self._kenar(CB_ATES, bool(c.get_button(CB_ATES)))
        d.estop = self._kenar(CB_ESTOP, bool(c.get_button(CB_ESTOP)))
        d.merkez = self._kenar(CB_MERKEZ, bool(c.get_button(CB_MERKEZ)))
        d.hiz_yukari = self._kenar(CB_HIZ_YUKARI, bool(c.get_button(CB_HIZ_YUKARI)))
        d.hiz_asagi = self._kenar(CB_HIZ_ASAGI, bool(c.get_button(CB_HIZ_ASAGI)))

    def _oku_joystick(self, d):
        """Ham Joystick yolu — SDL cihazi tanimadi, numaralar XInput duzeni VARSAYILIR."""
        j = self.js
        d.pan = _olu_bolge(float(j.get_axis(EKSEN_PAN)))
        d.tilt = -_olu_bolge(float(j.get_axis(EKSEN_TILT)))

        if j.get_numhats() > 0 and not d.hareket_var:
            hx, hy = j.get_hat(0)
            d.pan, d.tilt = float(hx), float(hy)

        def bas(no):
            return bool(j.get_button(no)) if no < j.get_numbuttons() else False

        d.ates = self._kenar(BTN_ATES, bas(BTN_ATES))
        d.estop = self._kenar(BTN_ESTOP, bas(BTN_ESTOP))
        d.merkez = self._kenar(BTN_MERKEZ, bas(BTN_MERKEZ))
        d.hiz_yukari = self._kenar(BTN_HIZ_YUKARI, bas(BTN_HIZ_YUKARI))
        d.hiz_asagi = self._kenar(BTN_HIZ_ASAGI, bas(BTN_HIZ_ASAGI))

    def kapat(self):
        try:
            if self.ctrl is not None:
                self.ctrl.quit()
            if self.js is not None:
                self.js.quit()
            if PYGAME_VAR:
                pygame.joystick.quit()
        except Exception:
            pass
        self.ctrl = self.js = None


if __name__ == "__main__":
    import time

    g = Gamepad()
    # Olu bolge matematigi cihazsiz da dogrulanabilir.
    assert _olu_bolge(0.0) == 0.0 and _olu_bolge(0.10) == 0.0      # gurultu yutulur
    assert _olu_bolge(1.0) == 1.0 and _olu_bolge(-1.0) == -1.0     # uc degerler tam
    assert 0.0 < _olu_bolge(0.20) < 0.10                           # esikten hemen sonra KUCUK
    assert abs(_olu_bolge(-0.5) + _olu_bolge(0.5)) < 1e-9          # simetrik
    print("olu bolge testleri OK")

    if not g.bagli:
        print(f"Gamepad yok ({g.hata}) — uygulama yine de calisir, klavye/D-pad aktif.")
        print("Takip uygulama ACIKKEN takarsaniz arayuz ~2 sn icinde kendiliginden bulur.")
        raise SystemExit(0)

    print(f"Gamepad: {g.ad}")
    if g.standart_harita:
        print("  yol: SDL GameController — dugme duzeni STANDART (A/Y/Start her padde ayni)")
    else:
        print("  yol: ham Joystick — SDL bu cihazi tanimiyor, XInput duzeni VARSAYILIYOR.")
        print(f"       eksen: {g.js.get_numaxes()}  dugme: {g.js.get_numbuttons()}"
              f"  hat: {g.js.get_numhats()}")
        print("       Yanlis tusa dusuyorsa gamepad.py'deki BTN_* numaralarini asagidaki")
        print("       'basili' ciktisina bakarak duzeltin.")
    print("\nCubugu oynatin / dugmelere basin (Ctrl+C ile cikis).")
    try:
        while True:
            d = g.oku()
            olaylar = [ad for ad, v in (("ATES", d.ates), ("E-STOP", d.estop),
                                        ("MERKEZ", d.merkez), ("HIZ+", d.hiz_yukari),
                                        ("HIZ-", d.hiz_asagi)) if v]
            ham = ""
            if g.js is not None:
                ham = " ham:" + str([i for i in range(g.js.get_numbuttons())
                                     if g.js.get_button(i)])
            print(f"\rpan {d.pan:+.2f}  tilt {d.tilt:+.2f}  {' '.join(olaylar):28s}{ham}   ",
                  end="", flush=True)
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\nbitti")
        g.kapat()
