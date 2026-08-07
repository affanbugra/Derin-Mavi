# -*- coding: utf-8 -*-
"""DERIN MAVI — Laptop <-> ESP32 SERI PROTOKOLU (TEK KAYNAK).

Bu dosya, ESP32'de GERCEKTEN CALISAN kodun konustugu protokolu tarif eder
(AccelStepper tabanli surus — bkz. esp32/derin_mavi_esp32/derin_mavi_esp32.ino).

DONANIM (ESP32'ye bagli):
    pan  motoru : YATAY eksen (azimut)   — step motor, STEP 6 / DIR 7
                  motor 15 disli -> buyuk cark 83 disli = **5.533:1 rediksiyon**
    tilt motoru : DIKEY eksen (yukselis) — step motor, STEP 4 / DIR 5, ENABLE 17
                  pan tarafinda ENABLE 16
    acil stop   : GPIO 15 — NO buton, basilinca LOW. Kart once lazeri, sonra hareketi,
                  sonra surucu ENABLE hatlarini (16/17) keser.
    lazer       : GPIO 18 — **PWM tetik** (1 kHz), guc %0-100 arasi ayarlanir
                  (25 DEGIL: ESP32-S3'te GPIO 22/23/24/25 fiziksel olarak YOKTUR)
    Surucu cozunurlugu: **6400 step/tur** (1/32 mikroadim).

KOMUTLAR — ASCII satir, '\\n' ile biter (ESP: Serial.readStringUntil('\\n')):
    P<derece>    pan  MUTLAK hedef acisi     "P45.00"
    T<derece>    tilt MUTLAK hedef acisi     "T12.50"
    S<der/sn>    tavan hiz                   "S40.0"   ┐ hiz duzeyi (3 kademe)
    A<der/sn2>   ivme                        "A100.0"  ┘
    G<yuzde>     lazer GUCU (%0-100)         "G40"     — "ne kadar" (kalici ayar)
    L1 / L0      lazer ac / kes              — "ne zaman" (ayarli gucte tetikler)
                 ⚠ L1 SUREKLI TAZELENIR (bkz. ATES_TAZELE_MS): tazeleme kesilirse kart
                   lazeri KENDI keser. Kablo koparsa "kes" komutu gidemez — o yuzden
                   "acik kal" demeyi surdurmek, "kapan" demeyi beklemekten guvenlidir.
    STOP         acil durdur (motorlar kilitli, lazer kesilir)
    START        devam
    ESP'nin ayrica "P<derece>N<sapma>" salinim ozelligi var (gosterim/test icin);
    uygulama kullanmaz — bu yuzden gonderdigimiz sayilarda 'N' harfi ASLA olmamali.

⚠ HIZ NEDEN STEP/SN DEGIL DERECE/SN? Iki eksenin disli orani FARKLI: pan'da 5.533:1
  rediksiyon var, tilt'te de var ama orani heniz olculmedi. Ayni step/sn iki eksende bambaska
  aci hizi demek olurdu. Laptop her yerde DERECE konusur (P/T de derece), step'e cevirmek
  kartin isi — disli/mikroadim degisirse yalniz firmware sabiti degisir.

ESP32 -> laptop: **yapisal durum paketi YOK.** Kart insan-okur metin yazar
    ("PAN Merkez: 45.00", "SISTEM DURDURULDU!"). Bu satirlar alt cubukta oldugu gibi
    gosterilir; konum/lazer/hiz bilgisini arayuz KENDI komut ettiginden bilir
    (kontrol.py bunlari tutar). Kart konumu geri bildirmedigi surece ekrandaki aci
    "hedef"tir, olculmus konum degildir — arayuz de oyle yazar.

⚠ MUTLAK ACI (delta DEGIL). ESP `moveTo(derece * stepsPerDegree)` ile mutlak hedefe
  gider. Iki sonucu var, ikisi de LEHIMIZE:
    * Kaybolan bir paket kalici sapma yaratmaz — bir sonraki komut dogru yeri yeniden
      soyler (delta protokolunde kayip paket sonsuza dek birikirdi).
    * Ates komutu (L1) hareketi etkilemez; takip ve ates ayni anda calisir.

⚠ PAN SARMASIZ GONDERILIR. Ekranda azimut 0-360 gosterilir ama ESP'ye SUREKLI
  (birikimli) aci gider: 350°'den 10°'ye gecerken "P370" denir, "P10" DEGIL. Aksi
  halde motor kisa yoldan degil, 340° geri donerdi.

⚠ YAZILIMSAL LIMIT IKI TARAFTA DA VAR. Arayuz tilt'i 0..TILT_MAX arasinda tutar, ESP de
  kendi tarafinda ayni araliga kirpar (seri monitorden elle "T500" yazan biri
  mekanigi kirmasin diye). Tek tarafa guvenilmez.
"""

# ---- ESP32 mekanik sabitleri (esp32/derin_mavi_esp32/derin_mavi_esp32.ino ile AYNI olmali) ----
STEP_TUR = 6400.0                   # surucu cozunurlugu (1/32 mikroadim)
PAN_DISLI = 83.0 / 15.0             # motor 15 disli -> cark 83 disli = 5.533:1
TILT_DISLI = 1.0                    # ⚠ GECICI: dikey eksende de rediksiyon VAR ama orani
#   heniz olculmedi (ekip bildirecek). 1:1 kaldigi surece tilt acilari GERCEK aci degildir —
#   "60°" komutu gercekte 60/oran kadar dondurur. Oran gelince BURASI ve firmware'deki
#   TILT_GEAR_RATIO birlikte duzeltilecek.
PAN_STEP_DER = STEP_TUR * PAN_DISLI / 360.0     # ≈ 98.37 step/derece
TILT_STEP_DER = STEP_TUR * TILT_DISLI / 360.0   # ≈ 17.78 step/derece

# AccelStepper adimlari yazilimla uretir; ESP32'de guvenli ust sinir kabaca budur.
# Ustune cikilirsa kart adim kacirir/tikanir — hiz tablosu bu sinira gore secildi ve
# firmware de kendi tarafinda ayni degerle kirpar.
MAKS_STEP_SN = 8000.0

# 0° = ufuk, + = yukari (negatif tilt YOK). TILT_MAX = MEKANIK tavan; operator ayrica
# arayuzden kendi calisma sinirini (max_tilt_limit) bunun ALTINDA secebilir.
# ⚠ 07.08: 60° -> 90° -> **180°**. Arayuzdeki kaydirici bir ara 90'a kadar gidiyordu ama
#   burasi 60'ta kirptigi icin gimbal 60'ta takili kaliyordu (iki taraf farkli tavan
#   tanimliyordu). Kaydiricinin tavani artik BURADAN turer, tek kaynak.
# ⚠ TILT_MAX bir MEKANIK tavandir, gercek aciyi GARANTI ETMEZ: TILT_DISLI hala 1:1
#   varsayimi oldugu icin "90°" komutu gercekte 90/oran kadar dondurur. Oran olculup
#   duzeltilene kadar buradaki sayilar komut acisidir, fiziksel aci degil.
TILT_MIN, TILT_MAX = 0.0, 180.0

# Arayuzun ACILIS calisma siniri (operator ⚙ panelinden TILT_MAX'a kadar yukseltir).
# Tavan 180'e cikarildi ama varsayilan 90'da birakildi: kimse istemeden namluyu arkaya
# devirmesin. "Daha yukari cikmam lazim" diyen operator bilincli olarak yukseltir.
TILT_CALISMA_VARSAYILAN = 90.0

# ---- LAZER GUCU (PWM duty %) — firmware LAZER_GUC_VARSAYILAN ile AYNI olmali ----
# Lazer surucusunun PWM girisi duty oraniyla gucu belirler; tam guc kullanilmiyor.
# ⚠ Dusuk guc DWELL SURESINI uzatir: %40'ta balonun patlamasi tam guce gore ~2.5 kat
#   surer. Sure yarismada puana bagli (Asama 1 bonus suresi, Asama 2-3 tur sureleri),
#   bu yuzden gercek patlama suresi OLCULUP bu deger yeniden degerlendirilmelidir.
LAZER_GUC_MIN, LAZER_GUC_MAX = 0, 100
LAZER_GUC_VARSAYILAN = 40

# ---- ATES OLU ADAM ANAHTARI ----
# Lazer acik kalmak icin karta duzenli "L1" tazelemesi gitmelidir; gitmezse kart lazeri
# KENDI keser. Kart tarafi 1 sn bekler; biz 250 ms'de bir tazeliyoruz ki birkac kacan
# tazeleme lazeri gereksiz yere kesmesin.
ATES_TAZELE_MS = 250
ATES_ZAMAN_ASIMI_MS = 1000          # firmware ATES_ZAMAN_ASIMI_MS ile AYNI olmali

# ---- HIZ DUZEYLERI (3 kademe) — arayuz, mock ve ESP32 AYNI tabloyu okur ----
H_YAVAS, H_NORMAL, H_HIZLI = 1, 2, 3
HIZ_AD = {H_YAVAS: "Yavaş", H_NORMAL: "Normal", H_HIZLI: "Hızlı"}
HIZ_VARSAYILAN = H_NORMAL
HIZ_SEVIYELER = (H_YAVAS, H_NORMAL, H_HIZLI)

# Duzey basina (tavan hiz derece/sn, ivme derece/sn²) — DARBOGAZ EKSEN PAN'dir:
# 5.533:1 rediksiyon + 6400 step/tur => 98.37 step/derece, yani 80°/s bile ~7870 step/sn
# demek. Tablo MAKS_STEP_SN sinirinin altinda kalacak sekilde secildi (test bunu dogrular).
# Ivme hizla birlikte artar: step motor yuksek tavan hiza dusuk ivmeyle cikamaz (hedefe
# varmadan komut degisir), dusuk hizda yuksek ivme ise adim kacirtir.
HIZ_TABLO = {
    H_YAVAS:  (15.0, 40.0),     # hassas nisan / dwell
    H_NORMAL: (40.0, 100.0),    # varsayilan: takip
    H_HIZLI:  (75.0, 200.0),    # genis aci tarama, hedef degistirme
}


def hiz_kirp(h):
    """Gecersiz/bilinmeyen duzeyi varsayilana cevirir."""
    return h if h in HIZ_TABLO else HIZ_VARSAYILAN


def derece_sn(seviye):
    """Duzeyin tavan hizi (derece/sn) — arayuzde gosterim icin."""
    return HIZ_TABLO[hiz_kirp(seviye)][0]


def pan_step_sn(seviye):
    """Duzeyin PAN ekseninde karsiligi (step/sn). Sinira yakinligi gormek icin."""
    return derece_sn(seviye) * PAN_STEP_DER


def tilt_kirp(derece):
    return max(TILT_MIN, min(TILT_MAX, derece))


# ---- komut ureticiler (tek cikis noktasi: kimse elle string kurmaz) ----
def pan(derece):
    """Pan MUTLAK hedef acisi. Sarmasiz (birikimli) aci verilmelidir."""
    return f"P{derece:.2f}\n"


def tilt(derece):
    """Tilt MUTLAK hedef acisi (TILT_MIN..TILT_MAX arasina kirpilir)."""
    return f"T{tilt_kirp(derece):.2f}\n"


def hiz(seviye):
    """Hiz duzeyi -> iki satirlik komut: tavan hiz (der/sn) + ivme (der/sn²)."""
    h, iv = HIZ_TABLO[hiz_kirp(seviye)]
    return f"S{h:.1f}\n", f"A{iv:.1f}\n"


def lazer(ac):
    """Lazeri AYARLI GUCTE ac / kes. Guc ayri komuttur (bkz. lazer_guc)."""
    return "L1\n" if ac else "L0\n"


def guc_kirp(yuzde):
    return max(LAZER_GUC_MIN, min(LAZER_GUC_MAX, int(round(yuzde))))


def lazer_guc(yuzde):
    """Lazer gucu (%). Kalicidir: sonraki her L1 bu gucte yakar.

    Neden L<yuzde> DEGIL de ayri komut? "L1" bugun 'ac' demek; L'ye yuzde yuklenseydi
    mevcut her cagri sessizce %1 guce duserdi (kod calisir gorunur, lazer yanmaz).
    Ayrica "ne kadar" ile "ne zaman" ayri kavramlar — hiz tarafinda da S/A ile P/T boyle."""
    return f"G{guc_kirp(yuzde)}\n"


DUR = "STOP\n"          # acil durdur
DEVAM = "START\n"       # devam


def satir_yeniden_baslama_mi(satir):
    """Kartin YENIDEN BASLADIGINI (reset) gosteren satir mi?

    Neden onemli: reset sonrasi kartin konum sayaci SIFIRDAN baslar (AccelStepper yeniden
    kurulur) ama laptop hala eski hedefi bilir. Fark edilmezse sonraki her komut kaymis
    referansa gore hesaplanir ve ekrandaki aci gercek konumu gostermez. Besleme
    dalgalanmasi/brown-out sessizce bu duruma yol acar — o yuzden acilis satirini
    yakalayip iki tarafi da sifirlariz."""
    u = satir.upper()
    return "SISTEM AKTIF" in u or "ESP-ROM" in u


def satir_konum(satir):
    """Kartin bildirdigi (pan, tilt) konumu — "Konum P45.00 / T12.50" (yoksa None).

    Kart normalde konum geri bildirimi YAPMAZ; bunu yalnizca ACIL DURDURMADA yazar.
    Sebep: durdurma aninda kartin hedefi "durdugum yer"e cekilir, laptop ise son KOMUT
    ettigi aciyi bilir — motor hedefe varmadan durduysa ikisi ayrisir. Bu satir olmadan
    acil durdurmadan sonra ekrandaki aci gercek konumu gostermezdi."""
    u = satir.upper()
    if "KONUM P" not in u:
        return None
    try:
        # Bosluklar atilir: "P45.00 / T12.50" ve "P45.00/T12.50" ayni sekilde cozulur.
        duz = u.split("KONUM P", 1)[1].replace(" ", "")
        pan_s, tilt_s = duz.split("/T", 1)
        return float(pan_s), float(tilt_s)
    except (ValueError, IndexError):
        return None


def satir_tilt_max(satir):
    """Kartin acilis banner'indaki "TILT_MAX: 180.0" degeri (yoksa None).

    Firmware guncellenmeyi unutulursa iki taraf FARKLI tavan bilir ve gimbal sessizce
    eski limitte takilir — arayuz 120 gosterirken kart 90'da kirpar. Bu satir sayesinde
    uyusmazlik acilista yakalanir."""
    u = satir.upper()
    if "TILT_MAX:" not in u:
        return None
    try:
        return float(u.split("TILT_MAX:", 1)[1].strip().split()[0])
    except (ValueError, IndexError):
        return None


def satir_estop_mu(satir):
    """ESP'nin metin cikisindan E-Stop'a girdigini anlar.

    Kart yapisal durum yollamadigi icin tek ipucu bu. Seri monitorden elle STOP yazan
    biri ya da (ileride) donanim butonu bu satiri uretir; arayuz o zaman atesi birakir."""
    return "DURDURUL" in satir.upper()


if __name__ == "__main__":
    # ESP'nin ayristirma mantigini birebir taklit eden dogrulama:
    #   komut.trim().toUpperCase() -> charAt(0) eksen, substring(1).toFloat() deger
    def esp_gibi_coz(satir):
        s = satir.strip().upper()
        return s[0], float(s[1:])

    assert pan(45) == "P45.00\n"
    assert esp_gibi_coz(pan(-12.34)) == ("P", -12.34)        # negatif aci
    assert esp_gibi_coz(pan(370.0)) == ("P", 370.0)          # sarmasiz aci
    # 'N' salinim ayracidir: sayilarimizda ASLA gecmemeli (yoksa ESP komutu salinim sanir)
    for s in (pan(123.45), tilt(59.99), hiz(H_HIZLI)[0], hiz(H_HIZLI)[1],
              lazer(True), lazer_guc(40)):
        assert "N" not in s.upper().rstrip()[1:], s
        assert s.endswith("\n"), s

    # tilt iki tarafta da kirpilir
    assert esp_gibi_coz(tilt(500)) == ("T", TILT_MAX)
    assert esp_gibi_coz(tilt(-500)) == ("T", TILT_MIN)

    # hiz duzeyleri: 3 kademe, artan, hepsi surucu/AccelStepper sinirinin ALTINDA
    assert set(HIZ_TABLO) == set(HIZ_SEVIYELER) == set(HIZ_AD)
    assert [HIZ_TABLO[h][0] for h in HIZ_SEVIYELER] == sorted(HIZ_TABLO[h][0] for h in HIZ_SEVIYELER)
    assert [HIZ_TABLO[h][1] for h in HIZ_SEVIYELER] == sorted(HIZ_TABLO[h][1] for h in HIZ_SEVIYELER)
    assert hiz(H_YAVAS) == ("S15.0\n", "A40.0\n"), hiz(H_YAVAS)
    assert hiz(99) == hiz(HIZ_VARSAYILAN)                     # gecersiz -> varsayilan
    for h in HIZ_SEVIYELER:                                   # PAN darbogaz eksen
        assert pan_step_sn(h) < MAKS_STEP_SN, (h, pan_step_sn(h))

    # mekanik: 6400 step/tur + 83/15 rediksiyon
    assert abs(PAN_STEP_DER - 98.370) < 0.01, PAN_STEP_DER
    assert abs(TILT_STEP_DER - 17.778) < 0.01, TILT_STEP_DER

    # LAZER GUCU: ayri komut, kirpilir, "L1" hala tam bir ac komutu olarak kalir
    assert lazer_guc(40) == "G40\n"
    assert esp_gibi_coz(lazer_guc(0)) == ("G", 0.0)
    assert lazer_guc(250) == f"G{LAZER_GUC_MAX}\n" and lazer_guc(-5) == f"G{LAZER_GUC_MIN}\n"
    assert lazer_guc(39.6) == "G40\n"                         # ESP toInt() alir: tam sayi gitmeli
    assert lazer(True) == "L1\n", "guc komutu L1'in anlamini degistirmemeli"

    # OLU ADAM ANAHTARI: tazeleme periyodu zaman asiminin en az yarisi kadar SIK olmali.
    # Aksi halde birkac kacan tazeleme lazeri ates ortasinda sondurur (ve dwell bozulur).
    assert ATES_TAZELE_MS * 2 <= ATES_ZAMAN_ASIMI_MS, (ATES_TAZELE_MS, ATES_ZAMAN_ASIMI_MS)

    assert satir_estop_mu("SISTEM DURDURULDU! Motorlar kilitli.")
    assert not satir_estop_mu("PAN Merkez: 45.00")
    assert not satir_estop_mu("LAZER KAPALI (%40)")           # ates kesme E-Stop sayilmaz
    print("protokol testleri OK — ESP32 metin komutlari + 3 kademe hiz + lazer gucu")
