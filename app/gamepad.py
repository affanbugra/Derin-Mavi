# -*- coding: utf-8 -*-
"""USB gamepad okuyucu — manuel kontrolun UCUNCU girdisi (D-pad ve klavyeden sonra).

Sartname Yetenek 1 kullanici komut arayuzlerini "UI/joystick/klavye" diye sayar; joystick
video icin dogrudan puandir (CLAUDE.md §2).

DUZEN (24.09): SOL cubuk = yatay + dikey (iki eksen), SAG cubuk Y = ZOOM (yalniz
Manuel + Asama 1; gimbal'i HIC surmez), D-pad = iki eksen · L2+R2 birlikte = ATES ac (tekrar basinca kes) · L1+R1
birlikte = merkeze al (kademeli; 24.09'dan beri tek basina degil) · Options/Start =
ACIL DURDUR (24.09'dan beri Daire/B DEGIL). Tek tusla ates YOKTUR.
ACIL DURDUR koldan yalniz KURULUR, asla KALDIRILMAZ (24.09): eskiden Options ikinci
basista DEVAM ediyordu — yanlislikla iki kez basmak acil durdurmayi kaldiriyordu.
Devam yalniz arayuzdeki "DEVAM ET" butonuyla, bilincli bir eylemle olur.

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
    # Takim karari 22.09: ATES iki omuz TETIGI birden (L2+R2) — tek tusla ates
    # istemiyoruz, klavyedeki "Space+B 2 sn" kuralinin kol karsiligi budur.
    CB_MERKEZ = (pygame.CONTROLLER_BUTTON_LEFTSHOULDER,     # L1 + R1 birlikte: merkeze al
                 pygame.CONTROLLER_BUTTON_RIGHTSHOULDER)
    # ACIL DURDUR yalniz Options/Start (24.09). Daire/B eskiden ikinci E-Stop tusuydu;
    # yuz tuslarinin yaninda kazara basiliyordu, kaldirildi.
    CB_ESTOP = pygame.CONTROLLER_BUTTON_START
    CB_TETIK = (pygame.CONTROLLER_AXIS_TRIGGERLEFT,     # L2 / R2 (analog)
                pygame.CONTROLLER_AXIS_TRIGGERRIGHT)
    # 24.09: iki eksen de SOL cubukta (X = yatay, Y = dikey). 22.09'daki "sol = yatay,
    # sag = dikey" bolmesi kaldirildi — operator tek elle nisan istedi. SAG cubuk Y
    # yalniz goruntu ZOOM'u verir (hareket DEGIL). Degisirse kontroller.py'yi guncelle.
    CB_EKSEN_PAN = pygame.CONTROLLER_AXIS_LEFTX
    CB_EKSEN_TILT = pygame.CONTROLLER_AXIS_LEFTY
    CB_EKSEN_ZOOM = pygame.CONTROLLER_AXIS_RIGHTY
    # GameController'da D-pad ayri bir "hat" degil, dort dugmedir.
    CB_DPAD = ((pygame.CONTROLLER_BUTTON_DPAD_UP, 0.0, 1.0, "up"),
               (pygame.CONTROLLER_BUTTON_DPAD_DOWN, 0.0, -1.0, "down"),
               (pygame.CONTROLLER_BUTTON_DPAD_LEFT, -1.0, 0.0, "left"),
               (pygame.CONTROLLER_BUTTON_DPAD_RIGHT, 1.0, 0.0, "right"))
    # GameController eksenleri -32768..32767 tam sayi doner (joystick'te -1..1 float).
    CB_EKSEN_OLCEK = 32767.0

# Tetik esigi: tetik analogdur (0..1). Yarisi gecince "basili" sayilir — daha
# dusuk olsaydi tetige degmek atesi kurmaya baslardi.
TETIK_ESIK = 0.5

# Yedek yol: ham Joystick numaralari (Xbox/XInput duzeni varsayilir).
# `python app/gamepad.py` hangi dugmenin hangi numara oldugunu canli gosterir.
BTN_L1, BTN_R1 = 4, 5     # omuz dugmeleri
BTN_L2, BTN_R2 = 6, 7     # DualSense'te tetikler dugme olarak da gorunur
BTN_ESTOP = 9             # Options/Start (ham duzende cogu padde 9)
EKSEN_L2, EKSEN_R2 = 4, 5       # tetikler eksen olarak gelirse

# Analog cubuk (ham yol): SOL X = pan, SOL Y = tilt; sag cubuk okunmaz. Y ekseni
# SDL'de yukari = NEGATIF; tilt'te yukari = ARTI oldugu icin isaret cevrilir (yoksa
# cubugu yukari itince namlu asagi inerdi).
EKSEN_PAN = 0             # sol cubuk X
EKSEN_TILT = 1            # sol cubuk Y (XInput/DirectInput duzeninde 1)
EKSEN_ZOOM = 3            # sag cubuk Y (XInput duzeninde 3) — yalniz zoom


def _olu_bolge(v):
    """Olu bolgeyi uygular ve KALAN araligi yeniden 0..1'e yayar.

    Duz kesme (|v|<esik -> 0) yapilsaydi cubuk esigi gectigi anda hiz 0'dan 0.15'e
    sicrardi; yeniden olcekleme sayesinde hareket sifirdan yumusak baslar."""
    if abs(v) < OLU_BOLGE:
        return 0.0
    isaret = 1.0 if v > 0 else -1.0
    return isaret * min(1.0, (abs(v) - OLU_BOLGE) / (1.0 - OLU_BOLGE))


class Durum:
    """Bir yoklamanin sonucu.

    * `pan`/`tilt`  : -1..1 (sol cubuk veya D-pad)
    * `zoom`        : -1..1 (sag cubuk Y; yukari = +, yakinlastir). Hareket DEGILDIR.
    * `basili`      : O AN basili tuslarin adlari — arayuzdeki kol resmini yakar
                      ve "iki tetik birlikte 2 sn" gibi SURE kurallarini besler.
    * `kenar`       : bu yoklamada YENI basilanlar — ac/kapa komutlari icin.

    Neden iki kume: ates/E-Stop birer ac-kapa (kenar gerekir), ama atesi kurmak
    icin tetiklerin BASILI KALMASI gerekir (seviye gerekir). Ikisi de lazim."""

    __slots__ = ("pan", "tilt", "zoom", "basili", "kenar")

    def __init__(self):
        self.pan = 0.0
        self.tilt = 0.0
        self.zoom = 0.0
        self.basili = set()
        self.kenar = set()

    @property
    def hareket_var(self):
        return self.pan != 0.0 or self.tilt != 0.0

    @property
    def estop(self):
        """Options/Start BU yoklamada basildi mi (ACIL DURDUR — yalniz kurar)."""
        return "start" in self.kenar

    @property
    def merkez(self):
        """L1 VE R1 BU yoklamada birlikte basili hale geldi mi (merkeze al). Tek omuz
        tusu bir sey yapmaz: kazara dokunus gimbal'i merkeze kosturmasin (24.09)."""
        return {"l1", "r1"} <= self.basili and bool({"l1", "r1"} & self.kenar)

    @property
    def ates_basili(self):
        """Iki tetik birden basili mi (atesi kurma kosulu)."""
        return {"l2", "r2"} <= self.basili

    @property
    def ates_kenar(self):
        """Iki tetik BU yoklamada birlikte basildi mi (ac/kapa komutu)."""
        return self.ates_basili and bool({"l2", "r2"} & self.kenar)


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

    def _koy(self, d, ad, basili):
        """Tusu duruma yazar: `basili` seviye, `kenar` bu yoklamada YENI basilanlar."""
        onceki = self._onceki.get(ad, False)
        self._onceki[ad] = basili
        if basili:
            d.basili.add(ad)
            if not onceki:
                d.kenar.add(ad)

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
        d.zoom = -_olu_bolge(c.get_axis(CB_EKSEN_ZOOM) / CB_EKSEN_OLCEK)

        # D-pad analog cubukla AYNI alanlari besler: hassas nisan icin dijital yon cogu
        # zaman cubuktan kolaydir. Cubuk zaten hareketliyse D-pad yok sayilir.
        for btn, kpan, ktilt, ad in CB_DPAD:
            if c.get_button(btn):
                self._koy(d, ad, True)
                if not d.hareket_var:
                    d.pan, d.tilt = kpan, ktilt
            else:
                self._koy(d, ad, False)

        for ad, btn in (("l1", CB_MERKEZ[0]), ("r1", CB_MERKEZ[1]), ("start", CB_ESTOP)):
            self._koy(d, ad, bool(c.get_button(btn)))
        for ad, eksen in (("l2", CB_TETIK[0]), ("r2", CB_TETIK[1])):
            self._koy(d, ad, c.get_axis(eksen) / CB_EKSEN_OLCEK > TETIK_ESIK)

    def _oku_joystick(self, d):
        """Ham Joystick yolu — SDL cihazi tanimadi, numaralar XInput duzeni VARSAYILIR."""
        j = self.js
        d.pan = _olu_bolge(float(j.get_axis(EKSEN_PAN)))
        d.tilt = -_olu_bolge(float(j.get_axis(EKSEN_TILT)))
        if EKSEN_ZOOM < j.get_numaxes():
            d.zoom = -_olu_bolge(float(j.get_axis(EKSEN_ZOOM)))

        if j.get_numhats() > 0:
            hx, hy = j.get_hat(0)
            for ad, acik in (("left", hx < 0), ("right", hx > 0),
                             ("down", hy < 0), ("up", hy > 0)):
                self._koy(d, ad, acik)
            if not d.hareket_var:
                d.pan, d.tilt = float(hx), float(hy)

        def bas(no):
            return bool(j.get_button(no)) if no < j.get_numbuttons() else False

        def eksen(no):
            return float(j.get_axis(no)) if no < j.get_numaxes() else -1.0

        for ad, btn in (("l1", BTN_L1), ("r1", BTN_R1), ("start", BTN_ESTOP)):
            self._koy(d, ad, bas(btn))
        # Tetik: kimi padde dugme, kimi padde eksen (-1..1). Ikisi de kabul edilir.
        for ad, btn, eks in (("l2", BTN_L2, EKSEN_L2), ("r2", BTN_R2, EKSEN_R2)):
            self._koy(d, ad, bas(btn) or (eksen(eks) + 1.0) / 2.0 > TETIK_ESIK)

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

    # Durum semantigi (cihazsiz test edilebilir): ates IKI tetik birden ister ve
    # basili tutmak komutu TEKRARLAMAZ (yoksa lazer 50 ms'de bir acilip kapanirdi).
    d = Durum()
    d.basili, d.kenar = {"l2"}, {"l2"}
    assert not d.ates_basili and not d.ates_kenar, "tek tetik atesi kurmamali"
    d.basili, d.kenar = {"l2", "r2"}, {"r2"}
    assert d.ates_basili and d.ates_kenar
    d.kenar = set()
    assert d.ates_basili and not d.ates_kenar, "basili tutmak tekrar tetikledi"
    d.basili, d.kenar = {"l1"}, {"l1"}
    assert not d.merkez, "tek omuz tusu merkeze aldi (L1+R1 birlikte olmali)"
    d.basili, d.kenar = {"l1", "r1"}, {"r1"}
    assert d.merkez and not d.estop
    d.kenar = set()
    assert not d.merkez, "basili tutmak merkeze almayi tekrar tetikledi"
    d.basili, d.kenar = {"daire"}, {"daire"}
    assert not d.estop, "Daire hala acil durduruyor (yalniz Options/Start olmali)"
    d.basili, d.kenar = {"start"}, {"start"}
    assert d.estop and not d.merkez
    d.kenar = set()
    assert not d.estop, "basili tutmak acil durdurmayi tekrar tetikledi"
    # Cubuk duzeni (24.09): SOL cubuk iki ekseni surer, SAG cubuk hicbir sey yapmaz.
    # Sahte GameController ile gercek okuma yolu denenir (cihaz gerekmez).
    if PYGAME_VAR:
        class _SahteCtrl:
            def __init__(self, eksenler):
                self.eksenler = eksenler

            def get_axis(self, no):
                return self.eksenler.get(no, 0)

            def get_button(self, no):
                return False

        def _cubuk(eksenler):
            g.ctrl, g._onceki = _SahteCtrl(eksenler), {}
            d = Durum()
            g._oku_controller(d)
            return d

        tam = int(CB_EKSEN_OLCEK)
        d = _cubuk({pygame.CONTROLLER_AXIS_LEFTY: -tam})     # sol cubuk YUKARI
        assert d.tilt == 1.0 and d.pan == 0.0, "sol cubuk Y dikeyi surmuyor"
        d = _cubuk({pygame.CONTROLLER_AXIS_LEFTX: tam})
        assert d.pan == 1.0 and d.tilt == 0.0, "sol cubuk X yatayi surmuyor"
        d = _cubuk({pygame.CONTROLLER_AXIS_RIGHTX: tam, pygame.CONTROLLER_AXIS_RIGHTY: -tam})
        assert not d.hareket_var, "sag cubuk gimbal'i suruyor (yalniz zoom olmali)"
        assert d.zoom == 1.0, "sag cubuk YUKARI zoom vermiyor"
        d = _cubuk({pygame.CONTROLLER_AXIS_RIGHTY: tam})
        assert d.zoom == -1.0, "sag cubuk ASAGI uzaklastirmiyor"
        d = _cubuk({pygame.CONTROLLER_AXIS_LEFTY: -tam})
        assert d.zoom == 0.0, "sol cubuk zoom veriyor"
        g.ctrl = None
    print("olu bolge + cubuk duzeni testleri OK")

    if not g.bagli:
        print(f"Gamepad yok ({g.hata}) — uygulama yine de calisir, klavye/D-pad aktif.")
        print("Takip uygulama ACIKKEN takarsaniz arayuz ~2 sn icinde kendiliginden bulur.")
        raise SystemExit(0)

    print(f"Gamepad: {g.ad}")
    if g.standart_harita:
        print("  yol: SDL GameController — dugme duzeni STANDART (her padde ayni)")
    else:
        print("  yol: ham Joystick — SDL bu cihazi tanimiyor, XInput duzeni VARSAYILIYOR.")
        print(f"       eksen: {g.js.get_numaxes()}  dugme: {g.js.get_numbuttons()}"
              f"  hat: {g.js.get_numhats()}")
        print("       Yanlis tusa dusuyorsa gamepad.py'deki BTN_* numaralarini asagidaki")
        print("       'basili' ciktisina bakarak duzeltin.")
    print("\nDuzen: sol cubuk=yatay+dikey, sag cubuk Y=zoom (Manuel+A1), D-pad=yon · L2+R2=ates"
          " · L1+R1=merkez · Options/Start=ACIL DURDUR (yalniz kurar)")
    print("Cubugu oynatin / dugmelere basin (Ctrl+C ile cikis).")
    try:
        while True:
            d = g.oku()
            olaylar = [ad for ad, v in (("ATES(L2+R2)", d.ates_basili),
                                        ("E-STOP", d.estop),
                                        ("MERKEZ", d.merkez)) if v]
            olaylar.append("basili:" + ",".join(sorted(d.basili)))
            ham = ""
            if g.js is not None:
                ham = " ham:" + str([i for i in range(g.js.get_numbuttons())
                                     if g.js.get_button(i)])
            print(f"\rpan {d.pan:+.2f}  tilt {d.tilt:+.2f}  zoom {d.zoom:+.2f}  {' '.join(olaylar):28s}{ham}   ",
                  end="", flush=True)
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\nbitti")
        g.kapat()
