# -*- coding: utf-8 -*-
"""DERIN MAVI - Algi cekirdegi (perception core).

Kamera + YOLO tespit + RENK ile dost/dusman mantiginin TEK KAYNAGI. Arayuz
(arayuz_qt.py) bunu kullanir. Donanim-bagimsizdir (bkz. CLAUDE.md ilke 7).

Kamera kaynagi: DERINMAVI_CAM env (index / dosya / RTSP-URL); tanimsizsa otomatik tarama.
"""
import os
import time
import tempfile
import threading
import cv2

# SAHI (Slicing Aided Hyper Inference): uzak/kucuk nesneler icin dilimli cikarim.
# Lazy import — kurulu degilse SAHI modu kapalildir, hata vermez.
try:
    from sahi import AutoDetectionModel
    from sahi.predict import get_sliced_prediction
    _SAHI_KURULU = True
except ImportError:
    _SAHI_KURULU = False

from renk_analizi import renk_oranlari

_qmedia_ready = False


def _ensure_qmedia():
    """QMediaDevices kullanilabilir mi? (PySide6.QtMultimedia lazy import)"""
    global _qmedia_ready
    if _qmedia_ready:
        return True
    try:
        from PySide6.QtMultimedia import QMediaDevices  # noqa: F401
        _qmedia_ready = True
        return True
    except ImportError:
        return False


# ---------------- Sinif adlari ----------------
# Model hangi sinifi uretirse uretsin kutu ASLA sessizce atilmaz; DISPLAY yalnizca
# "guzel Turkce ad" tablosudur, bilinmeyen sinif modelin HAM adiyla gosterilir.
# (Eski kod `if cls not in DISPLAY: continue` diyordu; model 'F16'/'iha' gibi ufak
#  bir ad farkiyla egitilmisse TUM tespitler uyarisiz yok oluyordu.)
# Anahtarlar _sadelestir()'den gecmis halleriyle yazilir. Yeni bir model farkli ad
# kullaniyorsa buraya tek satir eklemek yeterli.
DISPLAY = {"f16": "F-16", "helikopter": "Helikopter", "drone": "İHA", "fuze": "Füze"}
DISPLAY_CV = {"f16": "F-16", "helikopter": "Helikopter", "drone": "IHA", "fuze": "Fuze"}

BALON = "balon"      # nisan noktasi sinifi (CLAUDE.md §7: balon maketin ALTINDA)
HEDEF_SINIFLARI = {"f16", "helikopter", "drone", "fuze"}


def kanonik(ad):
    """Sinif adini karsilastirilabilir hale getirir: kucuk harf, ayirici yok.
    'F-16' -> 'f16' · 'Mini_Drone' -> 'minidrone'. Eslesme aranmaz, kutu atilmaz."""
    s = str(ad).strip().lower()
    for ch in ("-", "_", ".", " "):
        s = s.replace(ch, "")
    return s


def goster_ad(kanon, ham):
    """Arayuz adi: bilineni Turkce'ye cevir, bilinmeyeni HAM haliyle goster."""
    return DISPLAY.get(kanon, str(ham))


def goster_ad_cv(kanon, ham):
    """OpenCV cizimi icin ASCII ad (cv2.putText Turkce karakter basamaz)."""
    if kanon in DISPLAY_CV:
        return DISPLAY_CV[kanon]
    return str(ham).encode("ascii", "replace").decode("ascii")


def balon_sinifi_mi(ad):
    """Farkli veri setlerindeki balon adlarini tek sinif olarak tanir.

    Ornekler: ``balon``, ``balloon``, ``green-balloon``, ``red_balloon``.
    Renk modelin sinif adinda bulunsa da arayuzde hepsi ayni BALON nesnesidir.
    """
    k = kanonik(ad)
    return k == BALON or k.endswith("balon") or k.endswith("balloon")


def modelde_hedef_var(model):
    return any(kanonik(a) in HEDEF_SINIFLARI
               for a in getattr(model, "names", {}).values())


def modelde_balon_var(model):
    return any(balon_sinifi_mi(a) for a in getattr(model, "names", {}).values())


def _balon_arama_penceresi(box, kare_sekli):
    """Bir hedefin govdesi ve hemen altindaki balon icin kirpilacak bolge."""
    h, w = kare_sekli[:2]
    x1, y1, x2, y2 = box
    kw, kh = max(1, x2 - x1), max(1, y2 - y1)
    return (max(0, int(x1 - 0.45 * kw)),
            max(0, int(y1 + 0.25 * kh)),
            min(w, int(x2 + 0.45 * kw)),
            min(h, int(y2 + 1.75 * kh)))


def ek_balonlari_tespit_et(modeller, frame, hedefler):
    """Balonu yalniz taninmis hedeflerin govde+alt bolgesinde arar.

    Tam kare taranmaz. Once ana model F16/helikopter/drone/fuze tanir; sonra ek
    balon modeli her gercek hedefin alt penceresinde calisir. Boylece sahnedeki
    bagimsiz balonlar bu hedefe aitmis gibi gosterilmez.
    """
    # DOSTUN BALONU ARANMAZ (23.09, takim karari): dost vurmak -10 puan, o hedefe
    # zaten ates edilmez -> balonunu bulmak hicbir ise yaramaz, ama bedava da
    # degildir (ek model her hedef icin bir kez daha kosar, FPS dusurur).
    # Asama 1-2'de taraf HIC okunmaz ve tip "Hedef"tir; oradaki her hedef aranir.
    gercek_hedefler = [d for d in hedefler
                       if d.get("cls") in HEDEF_SINIFLARI and not d.get("hayalet")
                       and d.get("tip") != "Dost"]
    if not modeller or not gercek_hedefler:
        return []
    a = ayar_al()
    esik = float(a["gosterim"])
    imgsz = int(a["cozunurluk"])
    pencereler = [_balon_arama_penceresi(d["box"], frame.shape) for d in gercek_hedefler]
    kirpintilar = [frame[y1:y2, x1:x2] for x1, y1, x2, y2 in pencereler]
    gecerli = [(d, p, k) for d, p, k in zip(gercek_hedefler, pencereler, kirpintilar)
               if k.size]
    if not gecerli:
        return []
    gercek_hedefler, pencereler, kirpintilar = map(list, zip(*gecerli))
    adaylar = []
    for model in modeller:
        try:
            results = model.predict(kirpintilar, conf=esik, iou=float(a["iou"]),
                                    max_det=int(a["maks_tespit"]), verbose=False,
                                    imgsz=imgsz)
        except Exception as e:
            print(f"[UYARI] Ek balon modeli calistirilamadi: {e}")
            continue
        for hedef, pencere, r in zip(gercek_hedefler, pencereler, results or []):
            ox, oy, _, _ = pencere
            hx1, hy1, hx2, hy2 = hedef["box"]
            hcx = (hx1 + hx2) * 0.5
            hcy = (hy1 + hy2) * 0.5
            hw = max(1, hx2 - hx1)
            for b in (r.boxes if r.boxes is not None else []):
                ham_ad = r.names[int(b.cls)]
                if not balon_sinifi_mi(ham_ad):
                    continue
                conf = float(b.conf)
                lx1, ly1, lx2, ly2 = [int(v) for v in b.xyxy[0].tolist()]
                box = (lx1 + ox, ly1 + oy, lx2 + ox, ly2 + oy)
                bcx = (box[0] + box[2]) * 0.5
                bcy = (box[1] + box[3]) * 0.5
                # Balon, taninan maketin yatay hizasinda ve govde merkezinin altinda.
                if abs(bcx - hcx) <= 0.95 * hw and bcy >= hcy:
                    adaylar.append((conf, box))

    # Birden fazla balon modeli ayni nesneyi bulursa en guvenli kutuyu bir kez goster.
    kalan = []
    for conf, box in sorted(adaylar, reverse=True):
        if not any(_ortusme(box, eski) >= 0.70 for eski in kalan):
            kalan.append(box)
    return kalan


def _model_listesi(model_veya_modeller):
    if isinstance(model_veya_modeller, (list, tuple)):
        return list(model_veya_modeller)
    return [model_veya_modeller]


def model_sinif_ozeti(model):
    """Alt cubuk teshisi: '2 sınıf · fuze, helikopter'. Arayuz 4 tip + balon vaat
    ederken model 2 sinifliysa bu gercek gizli kalmasin."""
    adlar = []
    for m in _model_listesi(model):
        for ad in getattr(m, "names", {}).values():
            if ad not in adlar:
                adlar.append(ad)
    if not adlar:
        return "model sınıfları okunamadı"
    kisa = ", ".join(adlar[:6]) + ("…" if len(adlar) > 6 else "")
    return f"{len(adlar)} sınıf · {kisa}"


def eksik_siniflar(model):
    """Sartnamenin gerektirdigi ama modelde OLMAYAN siniflar (uyari icin)."""
    adlar = [a for m in _model_listesi(model)
             for a in getattr(m, "names", {}).values()]
    var = {kanonik(a) for a in adlar}
    return [g for g in ("f16", "helikopter", "drone", "fuze", BALON)
            if (g != BALON and g not in var) or (g == BALON and not any(balon_sinifi_mi(a) for a in adlar))]

# ---------------- Canli ayarlar (arayuzdeki "⚙" panelinden) ----------------
# Varsayilanlar ULTRALYTICS'IN KENDI VARSAYILANLARIDIR: ayarlara dokunmayan biri ham
# `yolo track source=0` ile ayni davranisi gorur. Sapmak isteyen panelden sapar.
#
# model.track()'e verilen conf KASITLI olarak dusuktur (BESLEME_CONF): ByteTrack'in
# fikri dusuk skorlu kutulari da alip ikinci asamada eslestirmektir, modele yuksek
# conf verilirse o kutular NMS'te olur. Filtreleme tracker (hassasiyet) + cizim
# (gosterim) katmanlarinda yapilir.
BESLEME_CONF = 0.05

VARSAYILAN_AYAR = {
    # --- Yarisma gunu kacis kapisi ---
    "tum_kameralar": 0,     # 1: dahili/telefon dahil TUM kameralar listelensin
    "hassasiyet": 0.25,     # ByteTrack new_track_thresh + track_high_thresh
    "gosterim": 0.25,       # bu guvenin altindaki kutu CIZILMEZ
    "kararlilik": 30,       # ByteTrack track_buffer: kayip kutu kac kare yasar
    "cozunurluk": 640,      # model.track(imgsz=)
    "iou": 0.70,            # NMS IoU esigi
    # Cakisan kutu temizligi: iki kutunun kucugunun bu kadari otekinin icindeyse AYNI
    # nesnedir, biri elenir. NMS'in yapamadigi is (o sinif ici calisir) — gorevde ayni
    # alanda iki hedef bulunmaz. 0.99 = pratikte kapali.
    "ortusme": 0.60,
    "maks_tespit": 300,     # kare basina en fazla kutu (max_det)
    # --- nisan.py (Otonom takip geometrisi) ---
    "fov": 60.0,            # kameranin yatay gorus acisi (derece)
    # keremtakip: otonom_v4 sahadaki kararlı ayarları. final_v6'nın 0.60/0.06
    # çifti kutu gürültüsünü büyütüp motorlarda belirgin titreme üretiyordu.
    "kp": 0.25,             # takip gucu: hatanin dortte biri tek adimda kapanir
    "kd": 0.0,              # türev öngörüsü kapalı: tespit gürültüsü motora taşınmaz
    "olu_bolge": 0.02,      # merkeze bu kadar yakinsa komut yok (dwell icin sart)
    # Kamera-lazer boresight/paralaks kalibrasyonu (CLAUDE.md §7): lazer kameranin
    # optik ekseninden fiziksel olarak ayri montajli, ikisi ayni noktayi gostermez.
    # Kalibrasyon: lazeri manuel modda bir hedefe TAM ISABET ettir, ekranda hedefin
    # (eskiden merkezde cizilen) nisangahtan ne kadar kaydigina bak, o kadar ayarla.
    # Kare genisligi/yuksekliginin orani (%) — cozunurlukten bagimsiz kalsin diye.
    "lazer_ofset_x": 0.0,   # + : lazer, kamera eksenine gore SAGA vuruyor
    "lazer_ofset_y": 0.0,   # + : lazer, kamera eksenine gore ASAGI vuruyor
    # Balon nisan ofseti: nisan noktasi kutunun ALT KENARINDAN bu kadar asagi kayar,
    # birim = HEDEF KUTUSUNUN YUKSEKLIGI. Model balonu goremedigi icin (best.pt 4
    # sinif, balon YOK) balonun yeri maketten GEOMETRIK olarak kestirilir.
    # Neden kutu yuksekligine oranli, sabit ACI degil: balon maketin altinda SABIT
    # bir FIZIKSEL mesafede durur; bunun acisal karsiligi mesafeyle degisir (30 cm
    # -> 5 m'de 3.4 derece, 15 m'de 1.1 derece). Kutu yuksekligi de mesafeyle ayni
    # oranda kuculdugu icin oransal ofset 5/10/15 m'de KENDILIGINDEN dogru kalir;
    # sabit aci 15 m'de lazeri balonun cok altina, bosluga gonderirdi.
    "balon_ofset": 0.40,
    # 1 = nisan noktasi hedef kutusunun MERKEZI (balon yokken arac takibi);
    # 0 = balon (kutunun altina balon_ofset kadar). Saha: balonsuz takip denemesinde
    # nisan noktasi kutunun 0.9 boy ALTINDA kaldigi icin hedef merkezin ustundeyken
    # namlu ASAGI indi. Yarisma balon ister; varsayilan bu yuzden 0 kalir.
    "nisan_govde": 0,
    # --- surekli takip (hedef_kestirici.EksenTakip; konum bildiren kartta) ---
    # Piksel / EKSEN DERECESI, 1280 px genislikte. OLCULDU (22.09, 3 tekrar, aci ile
    # goruntu kaymasinin en iyi oturdugu deger): pan 19.6/18.6/17.8, tilt 11.1/13.4/12.7.
    # Iki eksen FARKLI: tilt "derecesi" namlu kalibrasyonudur, kamera ayni oranda
    # donmuyor. Tek deger (12) pan'da %40 hata demekti -> fazla duzeltme.
    # Tilt'te sabit ppd YOK: kol acisi once kamera acisina cevrilir
    # (tilt_surucu.KAMERA_PPD_TABLO), kamera acisinda ppd = pan ile ayni.
    "takip_ppd_pan": 18.7,
    # (Otonom tilt tavani / pan siniri AYARI YOK — 23.09 kullanici karari: otonom takip
    # arayuzdeki hareket penceresine uyar, gizli sinir tutulmaz. Bkz. bolge.py.)
    # ⚠ Kol 48'in USTUNDE kamera/kol orani OLCULMEDI (KAMERA_PPD_TABLO orada tahmin);
    # o bolgede kontrol kazanci modelden sapabilir.
    # Disli boslugu baslangic tahmini (derece). Olculen: tilt 0.1-0.9, pan 0.2-0.7.
    # Kontrolcu calisirken kendisi ogrenir (EksenTakip.bosluk_kest).
    "takip_bosluk": 0.8,
    # Kare kameradan OKUNDUGUNDA zaten bu kadar eskidir (pozlama + USB + decode).
    # Olcum, eksenin karenin CEKILDIGI andaki acisiyla eslenir; okunma ani
    # kullanilirsa hareket halinde hedef aci bu sure x eksen hizi kadar kayar.
    # ⚠ KUCUK TARAFTA TUT: benzetimde gercekten 40 ms BUYUK girilince duran hedefte
    # salinim basladi (64 yon degisimi), 40 ms KUCUK girilince zararsizdi.
    # OLCULDU (22.09): 60 FPS'te iki arka-plan faz kaymasi denemesi 40/40 ms,
    # 30 FPS'te 80/80 ms. Uygulama 60 FPS istedigi icin varsayilan 40 ms;
    # kamera FPS'i degisirse yeniden olculmeli.
    "kamera_gecikme": 0.04,
    # KILIT PENCERESI: kilitli hedef ana taramada bulunamazsa son yerinin cevresi
    # TAM COZUNURLUKTE kirpilip ikinci kez taranir (kucuk/uzak hedef 2x buyur).
    "roi_tespit": 1,
    "roi_esik": 0.30,
    # UZAK HEDEF EDINIMI (kilit YOKKEN). Olculdu (22.09, kucultulmus gercek drone,
    # 60 ornek/boy): tam kare 640 taramasi 35 px ve alti drone'u HIC bulamiyor
    # (%0; 15 m'de 30 cm drone ~21 px). Ana akis 640'ta kalir; kilit yokken
    # `arama_cozunurluk` seyrek denenir ve yalniz guclu bir ana-tarama adayi
    # yoksa her `uzak_tarama_periyot` karede bir kare 2x buyutulmus 12 parcaya
    # bolunup taranir (25 px: %75, 18 px: %55). Bulunan aday kilit penceresiyle
    # (3x) dogrulaninca kilit kurulur. GPU'suz makinede agirdir: 0 ile kapatilir.
    "arama_cozunurluk": 1280,
    "uzak_tarama": 1,
    "uzak_tarama_periyot": 4,
    # Uzak taramanin NEREYE bakacagini renk secsin (bkz. kirmizi_oneri): hedefler
    # kirmizi oldugu icin esit karo taramasindan hem daha isabetli hem daha ucuz.
    # 0 = eski esit karo taramasi.
    "uzak_kirmizi": 1,
    # ZOR ORNEK TOPLAMA: modelin zorlandigi kareler app/veri_toplama/'ya yazilir
    # (sonraki egitim icin). 1 sn'de en fazla 1, oturumda en fazla 300 kare.
    "zor_ornek": 1,
    # Olu bolge (ates hassasiyeti) HEDEF KUTUSUNUN YUKSEKLIGININ orani olarak.
    # Sartname (s.19): "kesit alanina gore belli bir buyuklukte balon" -> balonun
    # boyu hedefin boyuyla ORANTILI, sabit degil. Dolayisiyla "lazer balonun icinde
    # mi" olcutu de kutuyla orantili olmali; kareye oranli SABIT bir yuzde uzak
    # hedefte cok gevsek kalir. Olculen: kare genisliginin %2'si = 1920 px'te 38 px;
    # 15 m'de balon yaricapi bunun altina duser -> sistem "hedefteyim" deyip ates
    # eder ama lazer balonun yanina gider (10-15 m tam bizim ortak imha bandimiz).
    # Kutuya oranli olunca ayni isabet guvencesi 5 m'de de 15 m'de de gecerli olur.
    "olu_bolge_kutu": 0.12,
    "onay_esigi": 0.70,     # kesin tanima icin gereken min. guven
    "onay_tekrari": 3,      # kesin tanima icin gereken ardisik yuksek-guven kare sayisi
    "kamera_fps": 30,       # kameradan istenen saniyelik kare hizi
    # POZLAMA (DirectShow log2 saniye; 0 = otomatik). Olculdu (22.09, OBSBOT Meet 2,
    # oda isigi): otomatik ~15.6 ms (-6) poz; -7 (7.8 ms) parlaklik 133 -> 117, yani
    # isik yetiyor ve HAREKET BULANIKLIGI YARIYA iner (pan 60 der/sn'de ~17 px -> ~9 px).
    # Sahada donerken drone guveni bulaniklikla %90'dan %50'lere dusuyordu. -8 kareyi
    # yariya karartiyor. Kare cok karanlik cikarsa (ort < POZ_KARANLIK) otomatige doner.
    # ⚠ 23.09 KORIDOR: ayni -7 + icerde ayarlanmis kazanc aydinlik koridorda goruntuyu
    # BEYAZLATTI (parlaklik 233/255) — 15 m'deki hedef gorulmedi. Kameranin kendi otomatik
    # pozlamasi ayni yerde 129 verdi (60 FPS). Salon isigi bilinmedigi ve pan donerken
    # isik degistigi icin varsayilan OTOMATIK; elle pozlama ayardan secilebilir.
    "kamera_pozlama": 0,
    # --- SAHI (Slicing Aided Hyper Inference) ---
    # Uzak/kucuk nesne tespiti icin goruntuyu ust uste binen dilimlere bolup her dilimde
    # ayri cikarim yapar. Normal YOLO'nun kacirdigi kucuk hedefleri yakalar ama yavas.
    # ByteTrack takibi SAHI modunda DEVRE DISI kalir (gimbal yok, takip ID gerekmez).
    "sahi": 0,              # 0=kapali, 1=acik (anahtar tipi)
    "sahi_dilim": 640,      # her dilimin kenar uzunlugu (px) — model imgsz ile ayni olmali
    "sahi_ortusme": 0.20,   # komsu dilimlerin ortusme orani (0-0.5)
}
AYAR = dict(VARSAYILAN_AYAR)

# Bozuk/eski ayarlar.json degerleri sisteme sizmasin diye gecerli araliklar.
AYAR_SINIR = {
    "hassasiyet": (0.05, 0.95), "gosterim": (0.05, 0.95),
    "kararlilik": (5, 300), "cozunurluk": (320, 1280),
    "iou": (0.10, 0.95), "ortusme": (0.30, 0.99), "maks_tespit": (1, 1000),
    "fov": (20.0, 140.0),
    "kp": (0.05, 1.50), "kd": (0.0, 0.50), "olu_bolge": (0.0, 0.10),
    "lazer_ofset_x": (-0.15, 0.15), "lazer_ofset_y": (-0.15, 0.15),
    "balon_ofset": (0.0, 2.0), "olu_bolge_kutu": (0.02, 0.60), "nisan_govde": (0, 1),
    "takip_ppd_pan": (4.0, 60.0), "takip_bosluk": (0.0, 4.0), "kamera_gecikme": (0.0, 0.3),
    "roi_tespit": (0, 1), "roi_esik": (0.05, 0.95),
    "arama_cozunurluk": (320, 1920), "uzak_tarama": (0, 1), "uzak_tarama_periyot": (1, 30), "uzak_kirmizi": (0, 1), "zor_ornek": (0, 1),
    "onay_esigi": (0.10, 0.99), "onay_tekrari": (1, 10),
    "kamera_fps": (5, 120),
    "kamera_pozlama": (-13, 0),
    "sahi": (0, 1), "sahi_dilim": (320, 1280), "sahi_ortusme": (0.05, 0.50),
}

_ayar_kilit = threading.Lock()   # AYAR: GUI thread yazar, algi thread okur
_tracker_yeniden_kur = True      # hassasiyet/kararlilik degisince tracker yeniden kurulur

# ByteTrack ayarlarini canli degistirebilmek icin kendi yaml'imizi yazariz.
_TRACKER_YAML = os.path.join(tempfile.gettempdir(), "derinmavi_bytetrack.yaml")


def _tracker_yaml_yaz(a):
    """Guncel ayarlarla ByteTrack config'i yazar. Ultralytics varsayilan sablonu;
    yalnizca hassasiyet ve kararlilik kullanicidan gelir."""
    hass = float(a["hassasiyet"])
    with open(_TRACKER_YAML, "w", encoding="utf-8") as f:
        f.write(
            "tracker_type: bytetrack\n"
            f"track_high_thresh: {hass:.3f}\n"
            "track_low_thresh: 0.05\n"
            f"new_track_thresh: {hass:.3f}\n"
            f"track_buffer: {int(a['kararlilik'])}\n"
            "match_thresh: 0.8\n"
            "fuse_score: True\n"
        )


def ayar_al():
    """Ayarlarin o anki kopyasi. analiz_et kare basina TEK kez cagirir ki kare
    ortasinda ayar degisince yari-eski/yari-yeni karisim olusmasin."""
    with _ayar_kilit:
        return dict(AYAR)


def _kirp(k, v):
    """Bir ayar degerini gecerli araliga kirpar; cevrilemezse varsayilana doner."""
    alt, ust = AYAR_SINIR.get(k, (None, None))
    try:
        v = float(v)
    except (TypeError, ValueError):
        return VARSAYILAN_AYAR[k]
    if alt is not None:
        v = max(alt, min(ust, v))
    return int(round(v)) if isinstance(VARSAYILAN_AYAR[k], int) else v


def ayar_guncelle(**kw):
    """Arayuzden gelen ayar degisikligini uygular (canli). Bilinmeyen anahtar yok
    sayilir, bozuk deger araliga kirpilir. Tracker'i etkileyen ayar degisirse
    tracker bir sonraki karede yeniden kurulur."""
    global _tracker_yeniden_kur
    with _ayar_kilit:
        for k, v in kw.items():
            if k not in AYAR:
                continue
            yeni = _kirp(k, v)
            if k in ("kararlilik", "hassasiyet") and yeni != AYAR[k]:
                _tracker_yeniden_kur = True
            AYAR[k] = yeni
    _sinirlari_uygula()


def _sinirlari_uygula():
    """AYAR'daki "kacis kapisi" degerlerini ilgili modullere yansitir.

    TEK KAPI: ayar hangi yoldan gelirse gelsin (panel, ayarlar.json, Sifirla)
    buradan gecer — boylece "arayuzde yazan sayi" ile "sistemin uyguladigi sayi"
    ayrisamaz. Ice aktarim fonksiyon icinde: modul dongusu olusmasin."""
    try:
        import kamera as _k
        _k.tum_kameralar_ayarla(AYAR.get("tum_kameralar"))
    except Exception:
        pass

# BGR renkler (kutu cizimleri)
RED = (32, 32, 191)      # dusman (yalniz A3)
BLUE = (168, 88, 18)     # dost (yalniz A3) / belirsiz
HEDEF = (0, 170, 255)    # A1/A2: taraf ayrimi yok, hepsi hedef
YELLOW = (60, 200, 235)  # balon (nisan noktasi) / orta guven
ORANGE = (0, 165, 255)   # belirsiz / onay bekliyor
GREEN = (40, 200, 40)    # yuksek guven

CAM_SOURCE = os.environ.get("DERINMAVI_CAM", "").strip()

# Windows'ta DSHOW ONCE denenir: acilisi MSMF'ten cok daha hizlidir (~0.2s vs ~2-5s).
# Kamera DSHOW'da siyah verirse (bazi dahili kameralar) MSMF'e otomatik dusulur.
if os.name == "nt":
    _BACKENDS = [(cv2.CAP_DSHOW, "DSHOW"), (cv2.CAP_MSMF, "MSMF")]
else:
    _BACKENDS = [(cv2.CAP_ANY, "ANY")]

_cached_open = None
AKTIF_INDEX = None   # su an acik olan kamera index'i (arayuz secim listesi icin)


# ---------------- Kamera (donanim-bagimsiz) ----------------
AC_TIMEOUT = 4.0   # tek bir VideoCapture acilisi icin ust sinir (sn) — asla asili kalma

# Istenen kamera formati (kamera desteklemezse OpenCV en yakinina duser).
# 640x480'de 15 m'deki 30 cm'lik IHA ~8 piksel olur, model goremez.
ISTENEN_W = int(os.environ.get("DERINMAVI_CAM_W", "1280"))
ISTENEN_H = int(os.environ.get("DERINMAVI_CAM_H", "720"))
ISTENEN_FPS = int(os.environ.get("DERINMAVI_CAM_FPS", "30"))


def _cap_ayarla(cap):
    """Acilan kameraya format + tampon ayarlarini uygular.

    BUFFERSIZE=1: OpenCV birkac kare tamponlar ve cap.read() tamponun EN ESKI
    karesini verir. Inference kameradan yavas olunca tampon dolu kalir ve goruntu
    ~200-350 ms geride gider (kutu nesnenin arkasinda kalir).
    MJPG: cogu webcam 720p'yi sikistirilmamis YUY2 ile ~10 FPS, MJPG ile 30 FPS
    verir; MJPG istenmezse cozunurluk yukseltmek kare hizini sessizce dusurur.
    SIRA: FOURCC once, cozunurluk sonra (tersi bazi surucularde yok sayilir)."""
    try:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    except Exception:
        pass
    for prop, deger in ((cv2.CAP_PROP_BUFFERSIZE, 1),
                        (cv2.CAP_PROP_FRAME_WIDTH, ISTENEN_W),
                        (cv2.CAP_PROP_FRAME_HEIGHT, ISTENEN_H),
                        (cv2.CAP_PROP_FPS, int(AYAR.get("kamera_fps", ISTENEN_FPS)))):
        try:
            cap.set(prop, deger)
        except Exception:
            pass   # her backend her prop'u desteklemez
    return cap


def kamera_bilgi(cap):
    """Kameranin GERCEKTEN verdigi format (istenen degil) — alt cubuk/teshis icin."""
    if cap is None:
        return None
    try:
        return {"w": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                "h": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                "fps": float(cap.get(cv2.CAP_PROP_FPS) or 0.0)}
    except Exception:
        return None


class KameraOkuyucu:
    """Kamerayi kendi thread'inde surekli okur, yalnizca EN SON kareyi tutar.

    cap.read() ana dongude cagrilirsa, inference kameradan yavas oldugu anda surucu
    tamponu dolar ve read() hep eski kareyi verir -> goruntu gecikir.
    Tampon drenaji cozum degil: grab() bloklayici oldugu icin "n kare at" yapmak
    FPS'i kamera_fps/n'e bolerdi. Ayri thread kamera hiziyla doner; oku() her zaman
    en taze kareyi verir, islenemeyen kareler atlanir."""

    def __init__(self, cap):
        self.cap = cap
        self._kare = None
        self._kare_t = 0.0        # karenin cap.read()'den DONDUGU an (time.time)
        self._sira = 0            # kac kare uretildi (ayni kareyi iki kez islememek icin)
        self._kilit = threading.Lock()
        self._calis = True
        self.hata_sayaci = 0
        self._th = threading.Thread(target=self._dongu, daemon=True)
        self._th.start()

    def _dongu(self):
        while self._calis:
            cap = self.cap
            if cap is None:
                time.sleep(0.01)
                continue
            ok, frame = cap.read()
            if not ok or frame is None:
                self.hata_sayaci += 1
                time.sleep(0.01)
                continue
            self.hata_sayaci = 0
            t = time.time()
            with self._kilit:
                self._kare = frame
                self._kare_t = t
                self._sira += 1

    def oku(self, son_sira=None):
        """En taze kareyi dondurur: (kare, sira). Yeni kare yoksa (None, sira).
        `son_sira` verilirse ayni kare tekrar islenmez."""
        with self._kilit:
            if self._kare is None or (son_sira is not None and self._sira == son_sira):
                return None, self._sira
            return self._kare, self._sira

    def son_kare_zamani(self):
        """Son karenin kameradan OKUNDUGU an. Surekli takip kareyi eksen acisiyla bu
        zamana gore esler; tuketicinin kareyi aldigi an (video dongusu, GUI yogunlugu)
        degiskendir ve olcum hatasina donusur."""
        with self._kilit:
            return self._kare_t

    def cap_degistir(self, yeni_cap):
        """Kamera degisiminde (arayuzden secim) okuyucuyu yeni cap'e baglar."""
        with self._kilit:
            self._kare = None
        self.cap = yeni_cap
        self.hata_sayaci = 0

    def kapat(self):
        self._calis = False
        self._th.join(timeout=1.0)
        if self.cap is not None:
            self.cap.release()
            self.cap = None


POZ_KARANLIK = 70          # ortalama gri seviye: bunun altinda elle poz iptal
POZ_HEDEF = (100, 150)     # kazanc ayariyla hedeflenen ortalama gri
POZ_PARLAK = 190           # bunun ustunde (kazanc en alttayken bile) elle poz iptal


def _pozlama_uygula(cap):
    """Elle kisa pozlama (hareket bulanikligina karsi) + parlakligi kazancla (gain) toparla.

    OBSBOT/DirectShow elle pozlamaya gecince kazanci da sabitliyor: ayni -7 poz bir
    acilista parlaklik 117, digerinde 79 verdi (olculdu). Kazanc 0..64; ikili aramayla
    ortalama gri POZ_HEDEF araligina getirilir. Ulasilamazsa (karanlik salon, kazanc
    desteklenmiyor) kamera tamamen OTOMATIGE doner. Doner: uygulanan poz (0 = otomatik)."""
    poz = int(AYAR.get("kamera_pozlama", 0))

    def parlaklik():
        ort = None
        for _ in range(8):                     # yeni ayar birkac karede oturur
            ok, kare = cap.read()
            if ok and kare is not None:
                ort = float(kare.mean())
        return ort

    try:
        if poz == 0:
            cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75)
            return 0
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)
        cap.set(cv2.CAP_PROP_EXPOSURE, poz)
        alt, ust = 0.0, 64.0
        ort = parlaklik()
        for _ in range(7):
            if ort is None or POZ_HEDEF[0] <= ort <= POZ_HEDEF[1]:
                break
            if ort < POZ_HEDEF[0]:
                alt = float(cap.get(cv2.CAP_PROP_GAIN))
            else:
                ust = float(cap.get(cv2.CAP_PROP_GAIN))
            if not cap.set(cv2.CAP_PROP_GAIN, round((alt + ust) / 2)):
                break
            ort = parlaklik()
        if ort is None or ort < POZ_KARANLIK:
            print(f"[UYARI] Elle pozlama {poz} yeterli isik vermedi (ort {ort}); otomatige donuldu.")
            cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75)
            return 0
        if ort > POZ_PARLAK:
            # Kazanc en alttayken bile beyazlik: isik icerde ayarlanandan cok fazla.
            # Doygun kirmizi pembeye/beyaza doner, uzak kucuk hedef kaybolur.
            print(f"[UYARI] Elle pozlama {poz} fazla parlak (ort {ort:.0f}); otomatige donuldu.")
            cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75)
            return 0
        print(f"Kamera pozlama {poz} (~{1000 / 2 ** -poz:.1f} ms), kazanc "
              f"{cap.get(cv2.CAP_PROP_GAIN):.0f}, parlaklik {ort:.0f}")
        return poz
    except Exception:
        return 0


def _grab_gercek(cap):
    """Kameradan gercek (siyah olmayan) kare gelip gelmedigini hizlica test eder."""
    for _ in range(5):
        ok, frame = cap.read()
        if ok and frame is not None and frame.mean() > 3:
            return True
    return False


def _ac_timeout(idx, backend, timeout=AC_TIMEOUT):
    """VideoCapture'i zaman asimiyla acar. Acilis takilirsa (or. MSMF+OBSBOT 21s)
    None doner; takilan cap arka planda serbest birakilir. Boylece UI asla donmaz."""
    kutu = {}

    def _worker():
        cap = cv2.VideoCapture(idx, backend)
        if kutu.get("iptal"):
            cap.release()
        else:
            kutu["cap"] = cap

    th = threading.Thread(target=_worker, daemon=True)
    th.start()
    th.join(timeout)
    if th.is_alive():          # sure asildi
        kutu["iptal"] = True
        return None
    return kutu.get("cap")


def _dene(idx, backend, ad):
    """idx+backend'i zaman asimiyla acar; gercek kare verirse cap, yoksa None."""
    global AKTIF_INDEX
    cap = _ac_timeout(idx, backend)
    if cap is not None and cap.isOpened():
        _cap_ayarla(cap)                      # format + BUFFERSIZE=1 (A3) — test KARESINDEN ONCE
        if _grab_gercek(cap):
            _pozlama_uygula(cap)
            bilgi = kamera_bilgi(cap) or {}
            print(f"Kamera acildi: index {idx}, backend {ad}, "
                  f"format {bilgi.get('w')}x{bilgi.get('h')} @{bilgi.get('fps')}")
            AKTIF_INDEX = idx
            return cap
    if cap is not None:
        cap.release()
    return None


def _ac_index(idx):
    """Belirli index'i acar: once DSHOW (hizli), sonra MSMF (yavas, son care)."""
    for backend, ad in _BACKENDS:
        cap = _dene(idx, backend, ad)
        if cap is not None:
            return cap
    return None


# Telefonu webcam yapan uygulamalar (kamera darbogazinda pratik bir yedek — bkz. CLAUDE.md §12).
TELEFON_UYG = {"droidcam": "DroidCam", "ivcam": "iVCam", "iriun": "Iriun"}
# Dahili kamera ipuclari: "Integrated Camera" gibi acik adlar + laptop sensor kod adlari.
DAHILI_IPUCU = ("integrated", "built-in", "facetime", "techfront", "ov97", "ov56", "ov27")


def _guzel_kamera_adi(raw: str) -> str:
    """Ham aygit adini secim listesinde okunakli hale getirir. Amac tek: operator
    "hangisi laptopun kamerasi, hangisi taktigim kamera" ayrimini gorsun.

        'ov9734_techfront_camera'      -> 'PC Kamerası'
        'OBSBOT Meet SE StreamCamera'  -> 'USB Kamera · OBSBOT Meet SE'
        'USB2.0 HD UVC WebCam'         -> 'USB Kamera'

    Tanimadigi cihaz HAM adiyla gecer — hicbir kamera listede kaybolmaz.
    (Bu ad yalnizca gorunustur; kamera secimi/karar mantigi index ile calisir.)"""
    low = raw.lower().replace("_", " ")
    for anahtar, ad in TELEFON_UYG.items():
        if anahtar in low:
            return f"Telefon Kamerası · {ad}"
    if "virtual" in low:
        return "Sanal Kamera"
    if any(k in low for k in DAHILI_IPUCU):
        return "PC Kamerası"

    # Harici/USB: teknik son ekleri atip marka adini birak.
    temizle = raw
    for suf in ("StreamCamera", "Stream Camera", "WebCam", "Webcam", "UVC",
                "USB2.0", "USB 2.0", "USB3.0", "USB 3.0", "Camera", "Cam", "HD"):
        temizle = temizle.replace(suf, "").replace(suf.lower(), "")
    marka = " ".join(temizle.split()).strip(" -·.,")
    return f"USB Kamera · {marka}" if marka else "USB Kamera"


def kameralari_listele_qt():
    """QMediaDevices ile sistemdeki TUM kameralari gercek isimleriyle listeler.

    Doner: [{"index": int, "name": str, "is_default": bool, "resolutions": [(w, h), ...]}, ...]
    Her kamera icin OpenCV index'i eslestirilir (Windows'ta QMediaDevices sirasi
    genellikle OpenCV MSMF backend sirasi ile aynidir).
    """
    if not _ensure_qmedia():
        return []
    try:
        from PySide6.QtMultimedia import QMediaDevices
        cams = QMediaDevices.videoInputs()
        sonuc = []
        for i, cam in enumerate(cams):
            res_set = set()
            for fmt in cam.videoFormats():
                r = fmt.resolution()
                res_set.add((r.width(), r.height()))
            res_list = sorted(list(res_set), key=lambda x: x[0]*x[1], reverse=True)
            sonuc.append({
                "index": i,
                "name": _guzel_kamera_adi(cam.description()),
                "is_default": cam.isDefault(),
                "resolutions": res_list
            })
        return sonuc
    except Exception:
        return []


def kameralari_listele(max_idx=5):
    """Eski OpenCV index taramasi (fallback). Yeni kod kameralari_listele_qt() kullanir."""
    bulunan = []
    for i in range(max_idx):
        for backend, _ in _BACKENDS:
            cap = cv2.VideoCapture(i, backend)
            ok = cap.isOpened()
            cap.release()
            if ok:
                bulunan.append(i)
                break
    return bulunan


def ac_kaynak(idx):
    """Belirli bir kamera index'ini acar (arayuzden secim icin) ve hatirlar."""
    global _cached_open
    cap = _ac_index(idx)
    if cap is not None:
        _cached_open = idx
    return cap


def _aday_indexler():
    """Denenecek kamera index'lerini oncelik sirasiyla: USB/harici once, PC sona."""
    idxs = []
    qt_cams = kameralari_listele_qt()
    if qt_cams:
        sirali = sorted(qt_cams, key=lambda c: 1 if "PC Kamerası" in c["name"] else 0)
        idxs = [c["index"] for c in sirali]
    for i in range(4):   # QMediaDevices eksikse/bulamazsa tamamla
        if i not in idxs:
            idxs.append(i)
    return idxs


def open_camera():
    """Kamera kaynagini DINAMIK ve HIZLI cozer.

    Oncelik: env override -> onceki calisan -> IKI FAZLI tarama.
    Iki fazli tarama: once TUM indexler DSHOW ile (her biri ~0.5s), calisan
    ilkini al; hicbiri olmazsa MSMF ile (yavas ama zaman-asimli, son care).
    Boylece kotu/siyah veren bir kamera (or. MSMF'te 21s asilan OBSBOT) tum
    acilisi kilitlemez.
    """
    global _cached_open
    # 1. env override (index / dosya / URL)
    if CAM_SOURCE:
        if CAM_SOURCE.isdigit():
            cap = _ac_index(int(CAM_SOURCE))
            if cap is not None:
                _cached_open = int(CAM_SOURCE)
                return cap
        else:
            cap = cv2.VideoCapture(CAM_SOURCE)
            if cap.isOpened() and _grab_gercek(cap):
                print(f"Kamera acildi: kaynak {CAM_SOURCE}")
                return cap
            cap.release()
    # 2. onceki calisan index (hizli yeniden baglanma)
    if _cached_open is not None:
        cap = _ac_index(_cached_open)
        if cap is not None:
            return cap
    # 3. iki fazli tarama: faz1 = tum indexler DSHOW, faz2 = tum indexler MSMF
    adaylar = _aday_indexler()
    for backend, ad in _BACKENDS:          # _BACKENDS = [DSHOW(hizli), MSMF(yavas)]
        for idx in adaylar:
            cap = _dene(idx, backend, ad)
            if cap is not None:
                _cached_open = idx
                return cap
    return None


# ---------------- Takip (ByteTrack) ----------------
# model.track(persist=True) her nesneye kalici ID verir ve kisa kayiplarda takibi
# surdurur. Kendi coasting/EMA katmanimiz YOK (hayalet + cift kutu yaratiyordu);
# dogrudan ByteTrack'in o karedeki kutusu cizilir.
#
# ID'li kutuya gosterim esiginde kucuk bir tolerans taninir: takibe girmis nesne bir
# kare zayiflayinca titremesin. Ama esik yine UYGULANIR — eski kod "ID varsa guven
# ne olursa olsun goster" diyordu ve olu tespitler track_buffer boyunca hayalet
# kutu olarak ekranda kaliyordu.
ID_TOLERANS = 0.80   # ID'li kutu icin esik bu oranla yumusatilir (0.25 -> 0.20)

# ONAYLANMIS hedef pratikte hic elenmez. Amac operatorun kuralidir: "bir hedef bir kez
# %70 uzerinde dogrulandiysa artik onu TAKIP ET." Onaylanmis bir kutunun guveni bir kac
# kare dususte diye kaybolursa takip/dwell kopar; onay zaten yalnizca uzun sureli
# zayiflikta (ONAY_BOZULMA) dusurulur, tek karelik dususle degil.
ONAYLI_ESIK = 0.02

# Onayli bir track bu kadar kare UST USTE onay esiginin altinda kalirsa onay DUSER.
# Olmasaydi bir kez yanlis onaylanan sinif ID yasadigi surece duzelmezdi.
ONAY_BOZULMA = 15

# Normal takip 640 px'te hizli kalir. Kilitli hedef bir kare kaybolduktan sonra her
# YENIDEN_BUL_PERIYOT karede bir dinamik modellerde daha buyuk giris denenir. Sahadaki
# 640x360 referans karesinde drone 640 giriste tamamen kacarken 1024 giriste %34 ile
# bulundu. Her kareyi buyutmek gecikmeyi/salinimi artirir; seyrek kurtarma karesi
# bu maliyeti yalniz gercekten gerekli oldugunda oder. Sabit boyutlu ONNX/TensorRT
# modellerde cozumurluk degistirilmez.
YENIDEN_BUL_CARPAN = 2
YENIDEN_BUL_MAX = 1024
YENIDEN_BUL_PERIYOT = 4
ARAMA_YUKSEK_PERIYOT = 15

# Taraf hafizasi: yalniz A3 renk karari icin, kutu konumuna DOKUNMAZ. Renk bir an
# okunamazsa son bilinen taraf korunur -> dost/dusman etiketi yanip sonmez.
_taraf_hafiza = {}   # takip id -> "Düşman" | "Dost"
_takip_durumlari = {} # takip id -> aday/onayli sinif bilgisi
_kayip_sayaclari = {}  # takip id -> kac karedir gorulmedi
_kilitli_track_id = None  # Kalici takip icin kilitlenen hedefin ID'si
_kilitleme_yasagi_t = 0.0 # Otonom ates sonrasi bekleme suresi (timestamp)
_kilit_kayip_kare = 0     # kilitli hedef kac analiz karesidir GERCEK kutuyla gorulmedi
_arama_kare = 0            # kilit yokken seyrek yuksek-cozunurluk arama zamanlayicisi
_budama_sayaci = 0

# KILIT BIRAKMA — ZAMANLA, kare sayisiyla degil. Kilitli hedef bu sure GERCEK kutuyla
# (ByteTrack ya da kilit penceresi) gorulmezse kilit ve hayalet kutu duser.
# NEDEN: kilit eskiden ByteTrack'in track_buffer'i ("kararlilik", kayitli ayar 60 kare)
# kadar yasiyordu: 30 FPS'te 2 sn, yavas islemede 3 sn. O surede hayalet ekranda
# kaliyor ve KILIT VARKEN yeni hedefe otomatik kilit ve uzak tarama HIC calismiyordu
# (23.09 koridor: hedef gidince kutu kaldi; 15 m'deki yeni hedef ancak kamera elle
# kapatilip kilit dusunce goruldu). Asama 2'de 3 hedef ayni anda gelir — birini
# birakip digerine hemen gecmek gerekir. Kisa kopmalari (bulaniklik, tek kare
# kacirma) 0.5 sn rahatca kapsar; motor tarafi da 0.45 sn kestirimle kovalar.
KILIT_BIRAKMA_S = 0.5
_kilit_son_gercek = [None, 0.0]   # [kilitli id, o id'nin son GERCEK goruldugu an]

# VURULAN HEDEFLER: otonom atis tamamlanan hedef bir sure YENIDEN secilmez; DIGER
# hedeflere hemen kilitlenilir. Maket balonu patlasa da rayda gorunmeye devam eder;
# yasak olmazsa ayni hedefe tekrar tekrar ates edilirdi. Eskiden atistan sonra
# 10 sn HICBIR hedefe kilitlenilmiyordu (Asama 2: tur basina 3 hedef — kacirilan tur).
_vurulanlar = {}                  # takip id -> {"box": son kutu, "bitis": zaman}

RENK_ESIK = 0.02      # bu oranin altinda renk "okunamadi" sayilir
RENK_FARK_ESIK = 0.01 # kirmizi/cyan birbirine cok yakinsa taraf karari verme
BUDAMA_PERIYOT = 300  # kac karede bir olu ID'ler temizlenir


def takip_sifirla():
    """Taraf hafizasini ve takip durumlarini temizler (kamera degisince cagirilir)."""
    global _kilitli_track_id, _kilitleme_yasagi_t, _kilit_kayip_kare, _arama_kare
    _taraf_hafiza.clear()
    _takip_durumlari.clear()
    _kayip_sayaclari.clear()
    _kilitli_track_id = None
    _kilitleme_yasagi_t = 0.0
    _kilit_kayip_kare = 0
    _arama_kare = 0
    _uzak.update(aday=None, iyi=0, kotu=0, sayac=0)
    _vurulanlar.clear()
    _kilit_son_gercek[:] = [None, 0.0]


def hedef_vuruldu(saniye, simdi=None):
    """Kilitli hedefi VURULDU isaretler: kilit birakilir, bu hedef `saniye` boyunca
    yeniden secilmez; diger hedeflere HEMEN kilitlenilebilir. Doner: isaretlenen id."""
    global _kilitli_track_id, _kilit_kayip_kare, _arama_kare
    simdi = time.time() if simdi is None else simdi
    tid = _kilitli_track_id
    son = (_takip_durumlari.get(tid) or {}).get("son_det") if tid is not None else None
    if tid is not None and son is not None:
        _vurulanlar[tid] = {"box": tuple(son["box"]), "bitis": simdi + float(saniye)}
    _kilitli_track_id = None
    _kilit_kayip_kare = 0
    _arama_kare = 0
    return tid


def vurulan_mi(d):
    """Tespit, yasak suresi dolmamis bir vurulan hedef mi (ya da onun devami)?"""
    if d.get("id") is not None and d["id"] in _vurulanlar:
        return True
    return False


def _vurulanlari_guncelle(dets, simdi):
    """Vurulanlarin konumunu izler; ID degisirse yasagi AYNI YERDEKI yeni ID'ye tasir.

    ByteTrack hedefi kisa sure kaybedip yeni ID verebilir; yasak yalniz eski ID'de
    kalsaydi vurulmus maket "yeni hedef" sanilip tekrar ates edilirdi."""
    for tid in [t for t, v in _vurulanlar.items() if v["bitis"] <= simdi]:
        del _vurulanlar[tid]
    if not _vurulanlar:
        return
    gorulen = {d["id"]: d for d in dets if d.get("id") is not None and not d.get("hayalet")}
    for tid, v in list(_vurulanlar.items()):
        if tid in gorulen:
            v["box"] = tuple(gorulen[tid]["box"])
            continue
        for yid, d in gorulen.items():
            if yid not in _vurulanlar and _ayni_nesne_olabilir(d["box"], v["box"]):
                _vurulanlar[yid] = {"box": tuple(d["box"]), "bitis": v["bitis"]}
                break


def _vurulan_bolgede(kutu):
    """Uzak taramanin buldugu (ID'siz) aday vurulan bir hedefin yerinde mi?"""
    return any(_ayni_nesne_olabilir(kutu, v["box"]) for v in _vurulanlar.values())


def hedef_sec(track_id):
    """Arayuzdeki HEDEFLER listesinden ELLE hedef kilitleme.

    Ayni degiskeni (_kilitli_track_id) kullanir — otomatik kilitle AYNI mekanizma,
    tetikleyici (operator) farkli. track_id=None kilidi birakir, bir sonraki karede
    otomatik secim (en yuksek guvenli aday) devreye girer."""
    global _kilitli_track_id, _kilitleme_yasagi_t, _kilit_kayip_kare, _arama_kare
    # Arayuzde hedef tipi secildiyse elle tiklama da ayni guvenlik kapisindan
    # gecmelidir. Aksi halde operator "yalniz fuze" dedigi halde listeden yanlislikla
    # IHA'ya tiklayip namluyu istenmeyen tipe cevirebilirdi.
    if track_id is not None and _hedef_tipleri is not None:
        son = _takip_durumlari.get(track_id, {}).get("son_det") or {}
        if not son.get("cls") or not _tip_uygun(son["cls"]):
            return False
    _kilitli_track_id = track_id
    _kilitleme_yasagi_t = 0.0  # Elle secimde yasaki hemen kaldir
    _kilit_kayip_kare = 0
    _arama_kare = 0
    return True

# ---- ARANACAK HEDEF TIPLERI (operator arayuzden secer) ----
# Sartname: A2'de tip ayrimi yok (hepsi dusman, hepsi vurulur), A3'te TIPE GORE uygun
# menzil var (F16 10-15 m, Heli/Fuze 5-15 m, IHA 0-15 m) — operator o turda hangi tipi
# arayacagini soyler. Ayar KALICI DEGILDIR: her acilista "hepsi" ile baslar, cunku
# gecen turdan kalan bir suzgec yuzunden hedefi hic gormemek en pahali hatadir.
# ⚠ Yalniz OTOMATIK kilidi baglar: butun tespitler ekranda gorunmeye devam eder ve
# operator listeden ELLE her hedefi secebilir (hedef_sec suzgeci dinlemez).
_hedef_tipleri = None                    # None = hepsi


def _tip_kanonik(t):
    """Tip adini kanonik sinif adina cevirir. Arayuzun gosterdigi ad da kabul edilir
    ('Füze' -> 'fuze'): kanonik() Turkce harfi sadelestirmez, eslesme sessizce kacardi."""
    k = kanonik(t)
    for kanon, ad in list(DISPLAY.items()) + list(DISPLAY_CV.items()):
        if k == kanonik(ad):
            return kanon
    return k


def hedef_tipleri_ayarla(tipler=None):
    """Otonom kilidin arayacagi tipler. None/bos = hepsi. Doner: gecerli kume ya da None.

    Secim degisince mevcut kilit artik uygun degilse BIRAKILIR: operator "artik fuze
    ariyorum" dedigi anda namlunun drone'u kovalamaya devam etmesi beklenmez."""
    global _hedef_tipleri, _kilitli_track_id, _kilit_kayip_kare, _arama_kare
    secim = {_tip_kanonik(t) for t in (tipler or ()) if str(t).strip()}
    _hedef_tipleri = secim or None
    if (_kilitli_track_id is not None and _hedef_tipleri is not None
            and _kilitli_track_id in _takip_durumlari):
        son = _takip_durumlari[_kilitli_track_id].get("son_det") or {}
        if son.get("cls") and not _tip_uygun(son["cls"]):
            _kilitli_track_id = None
            _kilit_kayip_kare = 0
            _arama_kare = 0
    # Uzak edinim 3 karelik dogrulama yapar. Tip secimi bu arada degisirse eski
    # tipteki yarim aday yeni secimde kilide donusmemeli; edinimi temiz baslat.
    _uzak.update(aday=None, iyi=0, kotu=0, sayac=0)
    return hedef_tipleri()


def hedef_tipleri():
    """Secili tipler (kanonik) ya da None (hepsi)."""
    return None if _hedef_tipleri is None else set(_hedef_tipleri)


def _tip_uygun(cls):
    return _hedef_tipleri is None or kanonik(cls) in _hedef_tipleri


def hedefi_birak_ve_bekle(saniye):
    """Mevcut kilidi birakir ve belirtilen sure (saniye) boyunca yeni kilitlenmeyi engeller."""
    global _kilitli_track_id, _kilitleme_yasagi_t, _kilit_kayip_kare, _arama_kare
    _kilitli_track_id = None
    _kilitleme_yasagi_t = time.time() + saniye
    _kilit_kayip_kare = 0
    _arama_kare = 0

def kilitli_hedef():
    """Su an kilitli olan takip ID'sini doner (yok ise None). Arayuzun ayni hedefe
    tekrar tiklayinca kilidi birakmasi (toggle) icin kullanilir."""
    return _kilitli_track_id


def _hafiza_buda(canli_idler):
    """Goruntude olmayan ID'leri taraf hafizasindan siler; sozluk sinirsiz buyumesin."""
    global _budama_sayaci
    _budama_sayaci += 1
    if _budama_sayaci < BUDAMA_PERIYOT:
        return
    _budama_sayaci = 0
    for tid in [k for k in _taraf_hafiza if k not in canli_idler]:
        del _taraf_hafiza[tid]


def _taraf_belirle(frame, box, tid):
    """A3 taraf karari; zayif/kararsiz renkte eski karari korur veya Belirsiz kalir."""
    kirmizi, cyan = renk_oranlari(frame, box)
    okunamadi = max(kirmizi, cyan) < RENK_ESIK or abs(cyan - kirmizi) < RENK_FARK_ESIK
    if okunamadi:
        # Ilk karede renk okunamadi diye DUSMAN varsaymak dost hedefe ates riskidir.
        # Takip ID'sinin daha once guvenilir karari varsa onu koru; yoksa tarafsiz kal.
        return _taraf_hafiza.get(tid, "Belirsiz")
    taraf = "Dost" if cyan > kirmizi else "Düşman"
    if tid is not None:
        _taraf_hafiza[tid] = taraf
    return taraf


def anlik_kirmizi_kaniti(frame, box):
    """Otonom hareket/ates icin *bu karede* gorulen kirmizi kaniti.

    Taraf hafizasi burada kullanilmaz: hedef ortulurse onceki 'Dusman'
    karari ates iznine donusmemelidir. Bu yalniz ek bir kapidir; insan
    tespiti veya fiziksel lazer emniyeti yerine gecmez.
    """
    kirmizi, cyan = renk_oranlari(frame, box)
    return kirmizi >= RENK_ESIK and kirmizi - cyan >= RENK_FARK_ESIK


def _karar_ver(tid, sinif_adi, conf, onay_esigi, onay_tekrari):
    """Tek bir takip ID'si icin kesin-tanima karari. Doner: onayli sinif veya None.

    ⚠ SIFIRLAMA DEGIL, HISTEREZIS. Eski kural "onay_tekrari kadar ARDISIK yuksek-guven
      kare" idi: esigin altinda kalan tek bir kare sayaci sifirliyordu. Gercek videoda
      guven kare kare dalgalanir (%75, %68, %72, %71...), dolayisiyla onay ya hic
      gerceklesmiyor ya cok geciyordu — kutu "?" olarak kaliyordu. Artik zayif kare
      sayaci yalnizca BIR AZALTIR; guclu kareler cogunluktaysa onay gelir.

    Sinif yarisi da ayni mantikla cozulur (cogunluk oylamasi): baska bir sinif yuksek
    guvenle gelirse mevcut adayin puani duser, ancak puan tukendiginde aday degisir.
    Boylece tek karelik bir yanlis sinif tahmini adayi devirmez.

    ⚠ SINIF TEKILLIGI KALDIRILDI. Eskiden bir sinifi tek bir track "sahiplenirdi"
      (_kilitli_siniflar); ayni siniftan ikinci hedef ASLA onaylanamaz, sonsuza dek
      "belirsiz" kalirdi. Oysa sartname coklu hedef gerektiriyor: Asama 2'de 3 koldan
      ayni anda Fuze + Mini/Micro IHA geliyor, Asama 3'te dusman F16 ile dost F16 ayni
      karede olabiliyor. Ayirt etme isi zaten takip ID'sinin (ve A3'te rengin) isidir.
    """
    durum = _takip_durumlari.setdefault(
        tid, {"aday_sinif": None, "aday_sayac": 0, "onayli_sinif": None, "zayif": 0}
    )
    yuksek = conf >= onay_esigi

    # --- ONAYLI: sinif SABIT kalir; yalnizca uzun sureli zayiflik onayi dusurur ---
    if durum["onayli_sinif"] is not None:
        durum["zayif"] = 0 if yuksek else durum["zayif"] + 1
        if durum["zayif"] >= ONAY_BOZULMA:
            durum.update({"onayli_sinif": None, "aday_sinif": None,
                          "aday_sayac": 0, "zayif": 0})
            return None
        return durum["onayli_sinif"]

    # --- HENUZ ONAYSIZ: cogunluk oylamasi ---
    if not yuksek:
        durum["aday_sayac"] = max(0, durum["aday_sayac"] - 1)     # sifirlama YOK
    elif durum["aday_sinif"] == sinif_adi:
        durum["aday_sayac"] += 1
    else:
        durum["aday_sayac"] -= 1                                  # rakip sinif puan dusurur
        if durum["aday_sayac"] <= 0:
            durum["aday_sinif"] = sinif_adi
            durum["aday_sayac"] = 1

    if durum["aday_sayac"] >= onay_tekrari:
        durum["onayli_sinif"] = durum["aday_sinif"]
        durum["zayif"] = 0
        return durum["onayli_sinif"]
    return None


def _onayli_mi(tid):
    """Bu takip ID'si kesin tanindi mi? (cizim esigini secmek icin)"""
    return (tid is not None
            and _takip_durumlari.get(tid, {}).get("onayli_sinif") is not None)


def _ortusme(a, b):
    """Iki kutunun ortusme orani: kesisim / KUCUK kutunun alani (IoS).

    Neden IoU degil: IoU kesisimi BIRLESIME boler, dolayisiyla ic ice gecmis kutularda
    (kucuk kutu buyugun icinde) dusuk cikar — oysa bunlar en tipik cift-kutu halidir.
    Kucuk alana bolmek "bu kutunun ne kadari otekinin icinde" sorusunu sorar."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    kx = max(0, min(ax2, bx2) - max(ax1, bx1))
    ky = max(0, min(ay2, by2) - max(ay1, by1))
    kesisim = kx * ky
    if kesisim <= 0:
        return 0.0
    kucuk = min(max(1, (ax2 - ax1) * (ay2 - ay1)), max(1, (bx2 - bx1) * (by2 - by1)))
    return kesisim / kucuk


# Kilit koptuktan sonra ayni nesnenin YENIDEN bulunmasi icin arama yaricapi, son
# kutunun buyuk kenarinin kati cinsinden. Eskiden yalniz son kutuyla ORTUSEN kutu
# kabul ediliyordu (IoS > 0.3). Elde hizli hareket ettirilen hedefte tespit bir
# kac kare kesilince hedef zaten baska yerde olur, ortusme olmaz ve kilit bir daha
# gelmezdi — sahada 45 sn'lik testte 311 karede drone GORULDUGU halde takip
# edilmedi. Yaricap kutuyla olcekli: uzak (kucuk) hedefte arama alani da kuculur,
# kilit kadrajin baska ucundaki bir nesneye ATLAMAZ.
YENIDEN_KILIT_YARICAP = 1.0


# ---- KAMERA HAREKETI TELAFISI (ego-motion) ----
# Namlu dondukce SAHNE goruntude kayar: pan 60 der/sn ~ 1100 px/sn (19 px/der).
# ByteTrack'in Kalman tahmini ve kilit hafizasi (son_det: yeniden kilit yaricapi +
# hayalet kutu) KARE koordinatindadir; kamera donerken hedef "yerinden firlamis"
# gorunur -> ID degisir, yeniden kilit yaricapi kacar, hayalet yanlis yerde durur.
# Eksen acilari kartan BILINDIGI icin kayma olculmez, hesaplanir: arayuz her kareden
# once kamera_kaymasi_bildir(dx, dy) cagirir, analiz_et izleri bu kadar kaydirir.
_kamera_kayma = [0.0, 0.0]
_kayma_kilit = threading.Lock()


def kamera_kaymasi_bildir(dx, dy):
    """Onceki analiz karesinden bu yana KAMERA HAREKETININ goruntudeki etkisi (px,
    analiz edilen karenin koordinatinda). Birikir; analiz_et tuketir."""
    with _kayma_kilit:
        _kamera_kayma[0] += float(dx)
        _kamera_kayma[1] += float(dy)


def _kaymayi_uygula(model):
    with _kayma_kilit:
        dx, dy = _kamera_kayma
        _kamera_kayma[0] = _kamera_kayma[1] = 0.0
    if abs(dx) < 0.5 and abs(dy) < 0.5:
        return 0.0, 0.0
    try:
        for tr in getattr(getattr(model, "predictor", None), "trackers", None) or []:
            for s in list(getattr(tr, "tracked_stracks", [])) + list(getattr(tr, "lost_stracks", [])):
                m = getattr(s, "mean", None)
                if m is not None:
                    m[0] += dx
                    m[1] += dy
    except Exception:
        pass                      # tracker ic yapisi degisirse telafi sessizce devre disi
    for durum in _takip_durumlari.values():
        d = durum.get("son_det")
        if d is not None and d.get("box") is not None:
            x1, y1, x2, y2 = d["box"]
            durum["son_det"] = dict(d, box=(x1 + dx, y1 + dy, x2 + dx, y2 + dy))
    return dx, dy


# ---- KILIT PENCERESI (ROI) ile yeniden bulma ----
# Neden: 15 m'deki 30 cm'lik drone ~1.1 derece = 1280 px'lik karede ~21 px, modele
# giden 640'lik girdide ~10 px. YOLO bu boyutta kararsiz; hedef kare kare kaybolur,
# kilit hayalete duser. Kilitli hedefin son yerinin cevresi (en az 320 px, kutunun 4
# kati) TAM cozunurlukte kirpilip 640'ta taranir -> hedef ~2x buyuk gorunur.
# Yalniz kilit o karede ana taramada KAYIPKEN calisir (maliyet: o karede 2. cikarim).
# ⚠ AYRI MODEL NESNESI: model.track() modele ByteTrack geri cagrilarini kalici
# ekler; ayni nesneyle predict() cagrilirsa tracker KIRPIGI tam kare sanip izleri
# bozar. Ayni agirliklar ikinci bir YOLO nesnesiyle acilir (roi_modeli_ayarla ile
# disaridan da verilebilir — testler sahte model verir).
ROI_AZAMI_KAYIP = 90          # kare: bundan uzun kayipta pencere taramasi birakilir
# A2/A3: kilitli kutu bu kadar ARDISIK karede kirmizi gorunmezse kilit birakilir.
# Sahada (22.09 aksam) ByteTrack/kilit devri kilidi drone'u tutan kisinin govdesine
# ("F16 0.68" yanlis tespiti) tasidi ve kilit orada kaldi.
KIRMIZISIZ_AZAMI = 15
_kirmizisiz = [0]
ROI_EN_KUCUK = 213            # px: 640'lik girdide 3x buyutme
_roi_model = None
_roi_model_denendi = False


def roi_modeli_ayarla(m):
    global _roi_model, _roi_model_denendi
    _roi_model, _roi_model_denendi = m, True


def _roi_modeli_al(model):
    global _roi_model, _roi_model_denendi
    if _roi_model is None and not _roi_model_denendi:
        _roi_model_denendi = True
        yol = getattr(model, "ckpt_path", None) or getattr(model, "model_name", None)
        try:
            if yol:
                from ultralytics import YOLO
                _roi_model = YOLO(str(yol), task="detect")
        except Exception as e:
            print(f"[UYARI] Kilit penceresi modeli acilamadi ({e}); ozellik kapali.")
            _roi_model = None
    return _roi_model


def _roi_bul(m, frame, son_det, esik):
    """Son kutunun cevresini kirpip tarar; eski kilitle UYUMLU en guvenli kutu ya da None."""
    H, W = frame.shape[:2]
    x1, y1, x2, y2 = son_det["box"]
    cx, cy = (x1 + x2) * 0.5, (y1 + y2) * 0.5
    # Pencere = kutunun 6 kati, en az 213 px (640'a 3x buyur). Olculdu: 18 px drone'da
    # 213 px pencere %77, 320 px (2x) %58 buluyor; merkez S/4 kaysa da ayni.
    S = int(min(max(ROI_EN_KUCUK, 6 * max(x2 - x1, y2 - y1)), 640, W, H))
    ox = int(min(max(0, cx - S / 2), W - S))
    oy = int(min(max(0, cy - S / 2), H - S))
    r = m.predict(frame[oy:oy + S, ox:ox + S], conf=esik, imgsz=640, verbose=False)[0]
    en_iyi = None
    for b in (r.boxes if r.boxes is not None else []):
        if kanonik(r.names[int(b.cls)]) == BALON:
            continue
        bx1, by1, bx2, by2 = [int(v) for v in b.xyxy[0].tolist()]
        aday = {"box": (bx1 + ox, by1 + oy, bx2 + ox, by2 + oy), "conf": float(b.conf),
                "tip": son_det.get("tip"), "renk_tip": son_det.get("renk_tip")}
        if _yeniden_kilit_uyumlu(aday, son_det) and (en_iyi is None or aday["conf"] > en_iyi["conf"]):
            en_iyi = aday
    return en_iyi


# ---- ZOR ORNEK TOPLAMA ----
# Model yalniz 4 sinif ve sinirli gercek veriyle egitildi (CLAUDE.md §12). En degerli
# yeni veri, modelin SAHADA zorlandigi karelerdir. Uc durum kaydedilir:
#   roi     : kilit penceresi hedefi buldu, ana tarama tam karede KACIRDI
#             -> kare + YOLO etiketi (pencerenin buldugu kutu). En degerli ornek.
#   dusuk   : aktif hedef gorunuyor ama guveni dusuk (< onay esigi) -> kare + etiket
#   kayip   : kilit var, hedef hayalete dustu -> kare ETIKETSIZ (elle etiketlenecek)
# Etiket SAHTEdir (modelin/kilidin kendi kutusu): egitime girmeden once gozden
# gecirilmeli. Klasor: app/veri_toplama/<oturum>/{images,labels}/ (repoya girmez).
ZOR_ORNEK_ARALIK_S = 1.0
ZOR_ORNEK_AZAMI = 300
ZOR_ORNEK_DIZIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "veri_toplama")
_zor = {"son_t": 0.0, "son_bakis": 0.0, "sayi": 0, "oturum": None}


def _kacirma_mi(frame, dets, a):
    """Hedef renginde kompakt bir leke var ama HICBIR tespit onu kapsamiyor mu?

    Sahadaki "ben goruyorum, model gormuyor" ani budur ve egitim icin en degerli
    kare odur: model tam o gorunumde basarisiz oluyor. Leke kirmizi (= hedef rengi)
    ve KUCUK olmali; buyuk kirmizi yuzeyler (tisort, kutu) `kirmizi_oneri`nin
    dolgunluk/boy kapilarinda zaten eleniyor.

    ⚠ Kesin degil, ISARETTIR: kirmizi her leke hedef degildir. Bu yuzden kare
    ETIKETSIZ kaydedilir — etiketi insan koyar."""
    if not int(a.get("uzak_kirmizi", 1)):
        return None
    for leke in kirmizi_oneri(frame, sayi=4):
        if max(leke[2] - leke[0], leke[3] - leke[1]) > 120:
            continue                                  # yakin/buyuk cisim: kacirma sayilmaz
        if not any(_ortusme(leke, d["box"]) > 0.05 for d in dets):
            return leke
    return None


def _zor_ornek(frame, dets, active_idx, sinif_indeksi, a, simdi=None):
    """Kareyi modelin zorlandigi durumlarda kaydeder. Doner: kaydedilen tur ya da None."""
    if not int(a.get("zor_ornek", 0)):
        return None
    simdi = time.time() if simdi is None else simdi
    if _zor["sayi"] >= ZOR_ORNEK_AZAMI or simdi - _zor["son_t"] < ZOR_ORNEK_ARALIK_S:
        return None
    d = dets[active_idx] if 0 <= active_idx < len(dets) else None
    if _kilitli_track_id is None or d is None:
        # KILIT YOK: modelin hedefi hic bulamadigi hal. Renk kaniti varsa kaydet.
        # ⚠ Kirmizi leke aramasi 8.5 ms/kare: kare KAYDEDILMESE de calisirdi ve
        # kilit yokken her kareyi yerdi (19 FPS'te ~%16). Bakis da hiz sinirina tabi.
        if simdi - _zor["son_bakis"] < ZOR_ORNEK_ARALIK_S:
            return None
        _zor["son_bakis"] = simdi
        leke = _kacirma_mi(frame, dets, a)
        return None if leke is None else _zor_yaz(frame, "kacirma", None, None, simdi)
    if d.get("hayalet"):
        tur, etiket = "kayip", False
    elif d.get("roi"):
        tur, etiket = "roi", True
    elif d.get("conf", 100) < 100 * float(a.get("onay_esigi", 0.7)):
        tur, etiket = "dusuk", True
    else:
        return None
    idx = sinif_indeksi.get(d.get("cls")) if etiket else None
    if etiket and idx is None:
        return None                   # sinifi modelde karsiligi olmayan kutu etiketlenmez
    return _zor_yaz(frame, tur, d["box"] if etiket else None, idx, simdi)


def _zor_yaz(frame, tur, kutu, sinif_idx, simdi):
    """Kareyi (ve varsa etiketini) oturum klasorune yazar. Doner: tur ya da None."""
    if _zor["oturum"] is None:
        _zor["oturum"] = time.strftime("%Y%m%d_%H%M%S")
    kok = os.path.join(ZOR_ORNEK_DIZIN, _zor["oturum"])
    os.makedirs(os.path.join(kok, "images"), exist_ok=True)
    os.makedirs(os.path.join(kok, "labels"), exist_ok=True)
    ad = f"{tur}_{int(simdi * 1000)}"
    ok, veri = cv2.imencode(".jpg", frame)            # Turkce yol: imwrite yerine imencode
    if not ok:
        return None
    veri.tofile(os.path.join(kok, "images", ad + ".jpg"))
    H, W = frame.shape[:2]
    with open(os.path.join(kok, "labels", ad + ".txt"), "w", encoding="ascii") as f:
        if kutu is not None and sinif_idx is not None:
            x1, y1, x2, y2 = kutu
            f.write(f"{sinif_idx} {(x1 + x2) / 2 / W:.6f} {(y1 + y2) / 2 / H:.6f} "
                    f"{(x2 - x1) / W:.6f} {(y2 - y1) / H:.6f}\n")
    _zor["son_t"] = simdi
    _zor["sayi"] += 1
    return tur


# ---- UZAK HEDEF EDINIMI (kilit yokken) ----
UZAK_KARO = 320                # px; 640 girdide 2x buyur
_gpu_durumu = None


def _gpu_var():
    """CUDA var mi (bir kez bakilir). Uzak tarama (12 karo) ve 1280 arama GPU'da
    ~25-40 ms/kare; CPU'da (OpenVINO dahil) saniyede birkac kareye duser ve takibi
    oldururdu. GPU yoksa ikisi de KENDILIGINDEN kapanir, eski davranis surer."""
    global _gpu_durumu
    if _gpu_durumu is None:
        try:
            import torch
            _gpu_durumu = bool(torch.cuda.is_available())
        except Exception:
            _gpu_durumu = False
    return _gpu_durumu
UZAK_ADAY_ESIK = 0.35          # karo taramasinda aday sayilma guveni
UZAK_ADAY_OMUR = 5             # dogrulanamayan aday bu kadar kare sonra birakilir
_uzak = {"aday": None, "iyi": 0, "kotu": 0, "sayac": 0, "sonraki_id": -1}


def _uzak_karolar(W, H, S=UZAK_KARO):
    xs = list(range(0, max(1, W - S) + 1, int(S * 0.75))) or [0]
    ys = list(range(0, max(1, H - S) + 1, int(S * 0.75))) or [0]
    if xs[-1] != W - S:
        xs.append(max(0, W - S))
    if ys[-1] != H - S:
        ys.append(max(0, H - S))
    return [(x, y, x + S, y + S) for y in ys for x in xs]


# ---- KIRMIZI ONERI: nereye bakilacagini RENK soyler ----
# Hedeflerin tamami kirmizidir (A1/A2: hepsi; A3: dusman — zaten yalniz dusman
# kilitlenir). 15 m'de 30 cm drone ~21 px: modelin tam karede hic goremedigi boy.
# Kareyi esit karolara bolup HEPSINI taramak yerine, kirmizi lekelerin cevresini
# tararsak ayni buyutmeyi COK DAHA UCUZA aliriz.
KIRMIZI_ONERI_S, KIRMIZI_ONERI_V = 60, 40    # HSV doygunluk/parlaklik tabani
KIRMIZI_ONERI_EN_AZ = 4                      # px^2; daha kucugu gurultudur
KIRMIZI_ONERI_SAYI = 12                      # kare basina en cok pencere
KIRMIZI_ONERI_PENCERE = 214                  # px; 640'a buyutulunce ~3x


def kirmizi_oneri(frame, sayi=KIRMIZI_ONERI_SAYI):
    """Hedef renginde KUCUK ve KOMPAKT lekeler. Doner: kutu listesi, iyiden kotuye.

    Esikler olculerek secildi (271 gercek kare + kucultulmus gercek drone, 40 ornek):
    varsayilan RENK_ESIK degerleriyle (S>=110, V>=70) leke 21 px hedefin ancak
    %35'ini yakaliyordu — uzakta hedef bulaniklasir, rengi arka planla karisir ve
    doygunluk duser. S>=60 / V>=40 + hafif bulaniklastirma ile %88.

    Skor = dolgunluk x sqrt(alan): kirmizi tisort/kutu gibi BUYUK ve dagilmis
    yuzeyler degil, kucuk kompakt cisimler one cikar."""
    hsv = cv2.cvtColor(cv2.GaussianBlur(frame, (3, 3), 0), cv2.COLOR_BGR2HSV)
    m = (cv2.inRange(hsv, (0, KIRMIZI_ONERI_S, KIRMIZI_ONERI_V), (12, 255, 255)) |
         cv2.inRange(hsv, (168, KIRMIZI_ONERI_S, KIRMIZI_ONERI_V), (180, 255, 255)))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE,
                         cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
    n, _, ist, _ = cv2.connectedComponentsWithStats(m, 8)
    adaylar = []
    for i in range(1, n):
        x, y, w, h, alan = ist[i]
        if alan < KIRMIZI_ONERI_EN_AZ or max(w, h) > 240:
            continue
        if max(w, h) / max(1, min(w, h)) > 6:        # cizgi/kenar artigi
            continue
        adaylar.append((alan / float(w * h) * (alan ** 0.5), (x, y, x + w, y + h)))
    adaylar.sort(key=lambda t: -t[0])
    return [b for _, b in adaylar[:max(1, int(sayi))]]


def _oneri_penceresi(frame, kutu, kat=6.0, en_az=KIRMIZI_ONERI_PENCERE):
    """Lekenin cevresinden taranacak kare pencere (leke ORTADA kalir).

    ⚠ Pencereyi kucultup buyutmeyi artirmak TERS TEPIYOR: 96 px pencere (~6.7x)
    21 px hedefte %60, 214 px (~3x) %77 verdi — model 640'ta, sahnenin icinde
    egitildi; asiri buyutme baglami yok eder."""
    H, W = frame.shape[:2]
    x1, y1, x2, y2 = kutu
    yan = min(max(en_az, kat * max(x2 - x1, y2 - y1)), min(W, H))
    ax1 = int(max(0, min(W - yan, (x1 + x2) / 2 - yan / 2)))
    ay1 = int(max(0, min(H - yan, (y1 + y2) / 2 - yan / 2)))
    return ax1, ay1, int(ax1 + yan), int(ay1 + yan)


def _uzak_pencereler(frame, a):
    """Uzak taramanin bakacagi pencereler. Doner: (pencereler, kirmizi_kullanildi)."""
    if int(a.get("uzak_kirmizi", 1)):
        oneriler = kirmizi_oneri(frame)
        if oneriler:
            return [_oneri_penceresi(frame, b) for b in oneriler], True
    # Renk hic aday vermediyse (loş isik, hedef renksiz) eski esit karo taramasi.
    H, W = frame.shape[:2]
    return _uzak_karolar(W, H, min(UZAK_KARO, W, H)), False


def _uzak_tara(m, frame, dets, esik, a=None):
    """Kareyi buyutulmus pencerelerde tarar. Doner: mevcut tespitlerle cakismayan en
    guvenli aday {box, conf, cls} ya da None (yakin/orta hedefi ana tarama zaten bulur).

    OLCULDU (271 gercek kare, kucultulmus gercek drone, 40 ornek/boy) — isabet %,
    yanlis kutu/kare, sure:
      12 karo 2x (eski)   : 15 m %70 · 20 m %38 · 26 m %15 | 2.48 | 198 ms
      kirmizi oneri + 214 : 15 m %82 · 20 m %70 · 26 m %52 | 1.15 | 151 ms
    Yani renkle yonlendirilen tarama her boyda daha ISABETLI, yanlis alarmi YARISI
    ve daha HIZLI. (40 karo 3x taramak %80/%58 verir ama 454 ms — takibi oldururdu.)"""
    pencereler, _ = _uzak_pencereler(frame, a or {})
    kesitler = [frame[y1:y2, x1:x2] for x1, y1, x2, y2 in pencereler]
    kesitler = [k for k in kesitler if k.size]
    if not kesitler:
        return None
    sonuclar = m.predict(kesitler, conf=esik, imgsz=640, verbose=False)
    en_iyi = None
    for (ox, oy, _, _), r in zip(pencereler, sonuclar):
        for b in (r.boxes if r.boxes is not None else []):
            cls = kanonik(r.names[int(b.cls)])
            if cls == BALON:
                continue
            bx1, by1, bx2, by2 = [int(v) for v in b.xyxy[0].tolist()]
            kutu = (bx1 + ox, by1 + oy, bx2 + ox, by2 + oy)
            if not _tip_uygun(cls):
                continue                 # operator baska tip ariyor
            if _vurulan_bolgede(kutu):
                continue                 # vurulmus maket (balonu patladi, rayda duruyor)
            if any(_ortusme(kutu, d["box"]) > 0.3 for d in dets):
                continue
            if en_iyi is None or float(b.conf) > en_iyi["conf"]:
                en_iyi = {"box": kutu, "conf": float(b.conf), "cls": cls}
    return en_iyi


def _uzak_edinim(model, frame, dets, a, asama, gosterim):
    """Kilit YOKKEN cagrilir. Uzak adayi bulur/dogrular; dogrulaninca kilit kurar.
    Doner: aktif tespitin dets'e eklenmis indeksi ya da -1."""
    global _kilitli_track_id
    if not int(a.get("uzak_tarama", 1)) or not _gpu_var():
        return -1
    m = _roi_modeli_al(model)
    if m is None:
        return -1
    aday = _uzak["aday"]
    if aday is None:
        _uzak["sayac"] += 1
        if _uzak["sayac"] % max(1, int(a.get("uzak_tarama_periyot", 4))):
            return -1
        bulunan = _uzak_tara(m, frame, dets, UZAK_ADAY_ESIK, a)
        if bulunan is None:
            return -1
        _uzak.update(aday={"box": bulunan["box"], "cls": bulunan["cls"], "tip": None,
                           "renk_tip": None, "conf": bulunan["conf"]},
                     iyi=0, kotu=0, id=_uzak["sonraki_id"])
        _uzak["sonraki_id"] -= 1
        return -1
    # DOGRULAMA: aday bolgesi kilit penceresiyle (3x) taranir.
    roi = _roi_bul(m, frame, aday, float(a.get("roi_esik", 0.30)))
    if roi is None:
        _uzak["kotu"] += 1
        if _uzak["kotu"] >= UZAK_ADAY_OMUR:
            _uzak["aday"] = None
        return -1
    sid = _uzak["id"]
    kesin = _karar_ver(sid, aday["cls"], roi["conf"], float(a["onay_esigi"]),
                       int(a["onay_tekrari"]))
    renk_tip = _taraf_belirle(frame, roi["box"], sid) if asama == 3 else "Hedef"
    aday.update(box=roi["box"], conf=roi["conf"], renk_tip=renk_tip)
    if kesin is None:
        return -1
    if not _tip_uygun(kesin):
        _uzak["aday"] = None
        return -1
    # Asama 3: yalniz DUSMAN kilitlenir (dost vurmak -10).
    if asama == 3 and renk_tip != "Düşman":     # dost vurmak -10: A3'te yalniz dusman
        _uzak["aday"] = None
        return -1
    det = {"cls": kesin, "ham": kesin, "ad": goster_ad(kesin, kesin),
           "tip": renk_tip if asama == 3 else "Hedef", "renk_tip": renk_tip,
           "conf": int(round(roi["conf"] * 100)), "box": roi["box"], "id": sid, "roi": True}
    hafiza = dict(det)
    hafiza.pop("roi", None)
    _takip_durumlari[sid]["son_det"] = hafiza
    _kayip_sayaclari[sid] = 0
    _kilitli_track_id = sid
    _uzak["aday"] = None
    dets.append(det)
    return len(dets) - 1


def _ayni_nesne_olabilir(kutu, son_kutu):
    """Kilit koptuktan sonra `kutu`, son gorulen `son_kutu` ile ayni nesne olabilir mi?"""
    if _ortusme(kutu, son_kutu) > 0.3:
        return True
    sx, sy = (son_kutu[0] + son_kutu[2]) * 0.5, (son_kutu[1] + son_kutu[3]) * 0.5
    kx, ky = (kutu[0] + kutu[2]) * 0.5, (kutu[1] + kutu[3]) * 0.5
    boyut = max(son_kutu[2] - son_kutu[0], son_kutu[3] - son_kutu[1])
    return ((kx - sx) ** 2 + (ky - sy) ** 2) ** 0.5 <= YENIDEN_KILIT_YARICAP * boyut


def _yeniden_kilit_uyumlu(aday, son):
    """Yeni ID'li ``aday`` eski kilidin makul devami mi?

    Yalniz merkez yakinligi yetmez: eski hedefin yaninda beliren cok buyuk bir kutu
    (kol/insan) kilidi calabilir. A3'te bilinen bir dost/dusman tersligi de kesin
    ret sebebidir. Sinif esitligi bilerek zorunlu degildir; model ayni maketi ID
    degisiminden sonraki ilk karelerde farkli siniflayabilir.
    """
    if not _ayni_nesne_olabilir(aday["box"], son["box"]):
        return False
    aw = max(1.0, aday["box"][2] - aday["box"][0])
    ah = max(1.0, aday["box"][3] - aday["box"][1])
    sw = max(1.0, son["box"][2] - son["box"][0])
    sh = max(1.0, son["box"][3] - son["box"][1])
    oran = (aw * ah) / (sw * sh)
    if not 0.25 <= oran <= 4.0:
        return False
    son_taraf = son.get("renk_tip", son.get("tip"))
    aday_taraf = aday.get("renk_tip", aday.get("tip"))
    if son_taraf in ("Dost", "Düşman") and aday_taraf in ("Dost", "Düşman"):
        if son_taraf != aday_taraf:
            return False
    return True


def _takip_cozunurlugu(normal, sabit, kilit_var, kayip_kare, arama_kare=0,
                       arama_boyutu=None):
    """Normal veya seyrek yuksek-cozunurluk yeniden-bulma boyutunu sec."""
    if sabit is not None:
        return int(sabit)
    normal = int(normal)
    if kilit_var and kayip_kare > 0 and (kayip_kare - 1) % YENIDEN_BUL_PERIYOT == 0:
        return min(YENIDEN_BUL_MAX, normal * YENIDEN_BUL_CARPAN)
    if not kilit_var and arama_kare > 0 and arama_kare % ARAMA_YUKSEK_PERIYOT == 0:
        return max(normal, int(arama_boyutu)) if arama_boyutu is not None else min(
            YENIDEN_BUL_MAX, normal * YENIDEN_BUL_CARPAN)
    return normal


def _ana_taramada_guclu_aday(dets, a, asama=None):
    """Yakinda sinif onayini bekleyen kutu varken pahali uzak karo taramasi yapma.

    ⚠ Aranan TIPTEN olmayan guclu kutu (or. fuze ararken kadrajdaki drone) taramayi
    DURDURMAMALI — yoksa operator tip sectigi anda uzak hedef edinimi korlesir."""
    return any(d.get("id") is not None and d.get("conf", 0) >=
               100 * float(a["onay_esigi"]) and not d.get("hayalet")
               and _tip_uygun(d.get("cls")) and not vurulan_mi(d)
               and (asama not in (2, 3) or d.get("anlik_kirmizi", False)) for d in dets)


def _cift_kutulari_ele(dets, esik):
    """Ayni nesneye atilmis IKINCI kutuyu eler.

    GOREV GERCEGI (takim bilgisi): hedefler raya asili gelir, birbirinden ayridir —
    ayni alanda iki hedef ASLA bulunmaz. O halde yuksek ortusme her zaman modelin
    ayni nesneye iki kutu atmasidir.

    Bunu NMS yapamaz: Ultralytics NMS'i SINIF ICI calisir (agnostic degil). Model ayni
    maketi hem 'fuze' hem 'helikopter' sanarsa kutular %90 ortusse bile ikisi de hayatta
    kalir — "iou" ayarini kismak bu duruma hic dokunmaz.

    Hangisi kalir: once KESIN TANINMIS olan (onaylanmis tip, "belirsiz" degil), esitlikte
    guveni yuksek olan. Yalnizca guvene bakilsaydi, onaylanmis bir hedef o karede sansli
    cikan gecici bir kutu yuzunden elenebilirdi.

    ⚠ BALON bu temizlige HIC girmez: `dets`e degil ayri `balonlar` listesine yazilir.
      Balon maketin ALTINDA oldugu icin govdeyle ortusur; buraya dahil edilseydi nisan
      noktasi elenirdi (bkz. CLAUDE.md §7)."""
    if len(dets) < 2:
        return dets
    sira = sorted(range(len(dets)),
                  key=lambda i: (dets[i]["cls"] != "belirsiz", dets[i]["conf"]),
                  reverse=True)
    tutulan = []
    for i in sira:
        if all(_ortusme(dets[i]["box"], dets[j]["box"]) < esik for j in tutulan):
            tutulan.append(i)
    return [dets[i] for i in sorted(tutulan)]   # kutu sirasi korunur


def _kayiplari_temizle(gorulen_id_seti, kayip_esigi):
    """Gorulmeyen ID'lerin kayip sayacini artirir ve esigi asinca hafizadan siler.

    Esik ByteTrack'in track_buffer'indan ("kararlilik" ayari) turer. Sabit 60 karedeydi:
    tracker ID'yi 30 karede dusurup nesneye YENI ID verdigi icin bizim hafizamiz olu bir
    ID'yi tutmaya devam ediyor, geri gelen nesne ise sifirdan onay bekliyordu."""
    global _kilitli_track_id, _kilit_kayip_kare, _arama_kare
    for tid in list(_takip_durumlari.keys()):
        if tid in gorulen_id_seti:
            _kayip_sayaclari[tid] = 0
            continue
        _kayip_sayaclari[tid] = _kayip_sayaclari.get(tid, 0) + 1
        if _kayip_sayaclari[tid] >= kayip_esigi:
            _takip_durumlari.pop(tid, None)
            _kayip_sayaclari.pop(tid, None)
            if tid == _kilitli_track_id:
                _kilitli_track_id = None
                _kilit_kayip_kare = 0


# ---------------- SAHI: Dilimli Cikarim (uzak/kucuk nesneler) ----------------
# SAHI model nesnesi: lazy olarak ilk kullanımda olusturulur. Model degisirse (farkli .pt)
# cache bozulur ve yeniden olusturulur. Thread-safe: yalnizca inference thread kullanir.
_sahi_model_cache = None      # AutoDetectionModel nesnesi
_sahi_model_kaynak = None     # cache'lenmiş modelin kaynak yolu (degisim tespiti icin)


def _sahi_model_al(yolo_model, conf_esik=0.05):
    """SAHI AutoDetectionModel'i lazy yukler/cache'ler.

    Eger kurulu degilse veya model degismisse yeniden olusturulur. Ultralytics YOLO
    nesnesinden model yolunu cikarir."""
    global _sahi_model_cache, _sahi_model_kaynak
    if not _SAHI_KURULU:
        return None
    # Model yolunu al (ultralytics YOLO nesnesinden)
    model_yolu = getattr(yolo_model, "ckpt_path", None)
    if model_yolu is None:
        # Alternatif: model.model_name veya arguman
        model_yolu = getattr(yolo_model, "model_name", "best.pt")
    model_yolu = str(model_yolu)

    if _sahi_model_cache is not None and _sahi_model_kaynak == model_yolu:
        return _sahi_model_cache

    print(f"[SAHI] Model yukleniyor: {model_yolu}")
    try:
        _sahi_model_cache = AutoDetectionModel.from_pretrained(
            model_type="yolov8",
            model_path=model_yolu,
            confidence_threshold=conf_esik,
            device="cpu",
        )
        _sahi_model_kaynak = model_yolu
        print("[SAHI] Model hazir.")
    except Exception as e:
        print(f"[SAHI] Model yuklenemedi: {e}")
        _sahi_model_cache = None
    return _sahi_model_cache


def _analiz_sahi(model, frame, a, gosterim, estop=False, asama=None):
    """SAHI dilimli cikarim ile bir kareyi analiz eder.

    analiz_et() ile AYNI formati doner: (dets, balonlar, active_idx).
    ByteTrack takibi DEVRE DISI: nesneler ID almaz. Gimbal olmadigi icin
    kilit/takip gereksiz, yalnizca kare-bazli tespit yapilir.
    """
    sahi_mdl = _sahi_model_al(model, conf_esik=BESLEME_CONF)
    if sahi_mdl is None:
        # SAHI kullanilabilir degil, normal analiz_et'e geri dus
        return [], [], -1

    dilim = int(a.get("sahi_dilim", 640))
    ortusme = float(a.get("sahi_ortusme", 0.20))

    try:
        result = get_sliced_prediction(
            image=frame,
            detection_model=sahi_mdl,
            slice_height=dilim,
            slice_width=dilim,
            overlap_height_ratio=ortusme,
            overlap_width_ratio=ortusme,
            verbose=0,
        )
    except Exception as e:
        print(f"[SAHI] Cikarim hatasi: {e}")
        return [], [], -1

    balonlar = []
    dets = []
    model_adlari = getattr(model, "names", {})

    for pred in result.object_prediction_list:
        bbox = pred.bbox
        x1, y1 = int(bbox.minx), int(bbox.miny)
        x2, y2 = int(bbox.maxx), int(bbox.maxy)
        conf = pred.score.value
        ham_ad = pred.category.name
        cls = kanonik(ham_ad)

        if cls == BALON:
            if conf >= gosterim:
                balonlar.append((x1, y1, x2, y2))
            continue

        if conf < gosterim:
            continue

        if cls == "belirsiz":
            taraf = "Belirsiz"
        else:
            taraf = _taraf_belirle(frame, (x1, y1, x2, y2), None) if asama == 3 else "Hedef"

        dets.append({
            "cls": cls,
            "ham": ham_ad,
            "ad": "?" if cls == "belirsiz" else goster_ad(cls, ham_ad),
            "tip": taraf,
            "conf": int(round(conf * 100)),
            "box": (x1, y1, x2, y2),
            "id": None,    # SAHI modunda takip ID'si yok
        })

    # Cakisan kutu temizligi (ayni nesneye atilmis cift kutular)
    dets = _cift_kutulari_ele(dets, float(a["ortusme"]))

    # Kilit: SAHI modunda takip yok, en yuksek guvenli hedefi sec
    active_idx = -1
    if not estop and dets:
        if asama in (2, 3):
            # A2: tum hedefler dusmandir (sartname §5.4). A3: yalniz tarafi
            # "Dusman" okunan hedef kilitlenir — dost korumasi burasidir.
            aday = [i for i, d in enumerate(dets)
                    if asama != 3 or d["tip"] == "Düşman"]
        else:
            aday = list(range(len(dets)))
        if aday:
            active_idx = max(aday, key=lambda i: dets[i]["conf"])

    return dets, balonlar, active_idx


# ---------------- Tespit + karar ----------------
def analiz_et(model, frame, estop=False, asama=None):
    """Bir kareyi analiz eder. Doner: (dets, balonlar, active_idx).

    asama (sartname davranisi):
      1   : tanima/manuel secim; tum tespitler gosterilir
      2-3 : otonom ilk kilit icin anlik kirmizi kaniti gerekir; A3'te ayrica
            yalniz "Dusman" kilitlenir. Kutular renk kaniti olmasa da gosterilir.

    dets        : [{cls, ham, ad, tip, conf, box, id}, ...]
    balonlar    : [(x1,y1,x2,y2), ...] — nisan noktalari
    active_idx  : kilitli hedefin index'i; estop veya hedef yoksa -1
    """
    global _kilitli_track_id, _kilit_kayip_kare, _arama_kare
    a = ayar_al()
    gosterim = float(a["gosterim"])

    # ---- SAHI MODU: dilimli cikarim (uzak/kucuk nesneler icin) ----
    sahi_acik = _SAHI_KURULU and int(a.get("sahi", 0))
    if sahi_acik:
        return _analiz_sahi(model, frame, a, gosterim, estop, asama)

    # ByteTrack (model.track): Kalman-filtreli hareket tahmini var — kare-kare basit
    # IoU eslestirmenin (SAHI icin gelistirilmisti, bu branch SAHI kullanmiyor)
    # ONEMLI bir eksigi buydu: otonom modda gimbal kendi PD duzeltmesiyle donunce
    # kamera goruntusu de kayar, sonraki karede AYNI hedefin kutusu yeterince
    # ortusmeyip FARKLI bir ID alabiliyordu — kilit baska bir seye SIÇRAMASA bile
    # nisan hedefi (aim point) kararsizlasiyor, otonom modda "rastgele hareket, hedefi
    # takip etmiyor" sikayetine yol aciyordu (manuel modda otomatik kilit/nisan devre
    # disi oldugu icin gorunmuyordu). ByteTrack donen kamerada da ID'yi kaybetmez.
    _kaymayi_uygula(model)

    global _tracker_yeniden_kur
    if _tracker_yeniden_kur:
        _tracker_yaml_yaz(a)
        try:   # mevcut tracker'i dusur ki yeni ayarlarla yeniden kurulsun
            if getattr(model, "predictor", None) is not None and hasattr(model.predictor, "trackers"):
                del model.predictor.trackers
        except Exception:
            pass
        _tracker_yeniden_kur = False

    # conf=BESLEME_CONF kasitli dusuk (bkz. dosya basi): filtrelemeyi tracker
    # (hassasiyet) ve cizim (gosterim) yapar, NMS degil.
    #
    # TensorRT / ONNX sabit-boyutlu modeller: imgsz ayardan degil modelin kendi
    # boyutundan okunur. _fixed_imgsz ilk AssertionError'dan parse edilip saklanir.
    fixed_sz = getattr(model, "_fixed_imgsz", None)
    # Normal kare hep modelin egitildigi/olculen 640 boyutunda. 22.09 canli
    # deneyinde 1280'e DAIMA cikmak ayni yakin drone'da guveni %80'den %52'ye,
    # gercek kilidi %99'dan %0'a dusurdu. Uzak hedef icin yuksek boyut SEYREK
    # denenir; yakin hedefin sinif-onayini bozmaz.
    normal_sz = int(a["cozunurluk"])
    arama_sz = (max(normal_sz, int(a.get("arama_cozunurluk", 1280)))
                if _gpu_var() else normal_sz)
    secilen_imgsz = _takip_cozunurlugu(
        normal_sz, fixed_sz, _kilitli_track_id is not None,
        _kilit_kayip_kare, _arama_kare, arama_sz)
    track_kwargs = {
        "persist": True,
        "conf": BESLEME_CONF,
        "iou": float(a["iou"]),
        "max_det": int(a["maks_tespit"]),
        "tracker": _TRACKER_YAML,
        "verbose": False,
        "imgsz": secilen_imgsz,
    }

    try:
        results = model.track(frame, **track_kwargs)
    except AssertionError as e:
        msg = str(e)
        if "max model size" in msg:
            # Hata metninden modelin gercek boyutunu parse et: "(1, 3, 640, 640)"
            import re
            m = re.search(r"max model size[^\d]*(\d+),\s*(\d+)\)", msg)
            native_h = int(m.group(1)) if m else 640
            native_w = int(m.group(2)) if m else 640
            native_sz = max(native_h, native_w)
            model._fixed_imgsz = native_sz
            print(f"\n[UYARI] Model sabit boyutlu ({native_sz}px). "
                  f"Arayuzdeki cozunurluk yoksayiliyor.\n")
            # Predictor'i sifirla ki eski imgsz onbellekte kalmasin
            if getattr(model, "predictor", None) is not None:
                model.predictor = None
            track_kwargs["imgsz"] = native_sz
            results = model.track(frame, **track_kwargs)
        else:
            raise

    r = results[0]
    balonlar = []
    dets = []
    canli_idler = set()
    if r.boxes is not None:
        for b in r.boxes:
            ham_ad = r.names[int(b.cls)]     # modelin kendi sinif adi
            cls = kanonik(ham_ad)
            conf = float(b.conf)
            x1, y1, x2, y2 = [int(v) for v in b.xyxy[0].tolist()]
            tid = int(b.id.item()) if b.id is not None else None
            if tid is not None:
                canli_idler.add(tid)

            if cls == BALON:                 # nisan noktasi, hedef listesine girmez
                if conf >= gosterim:
                    balonlar.append((x1, y1, x2, y2))
                continue

            # KARAR ONCE, CIZIM ESIGI SONRA. Sira onemli: esik altinda kalan kare de
            # onay durumunu beslemelidir, yoksa onayli bir track zayifladiginda
            # `zayif` sayaci hic artmaz ve yanlis bir onay sonsuza dek yasardi.
            if tid is not None:
                kesin_cls = _karar_ver(tid, cls, conf, float(a["onay_esigi"]),
                                       int(a["onay_tekrari"]))
                if kesin_cls is None:
                    cls = "belirsiz"
                    ham_ad = "?"
                else:
                    cls = kesin_cls
                    ham_ad = kesin_cls

            # ONAYLANMIS hedef pratikte elenmez ("bir kez dogrulandiysa TAKIP ET"),
            # takibe girmis ama onaysiz kutuya kucuk tolerans, ID'siz kutuya tam esik.
            # Kilitli hedef her zaman gecer (esik 0) — kalici takibe engel olunmaz.
            if tid is not None and tid == _kilitli_track_id:
                esik = 0.0
            elif _onayli_mi(tid):
                esik = ONAYLI_ESIK
            elif tid is not None:
                esik = gosterim * ID_TOLERANS
            else:
                esik = gosterim
            if conf < esik:
                continue

            # Renk tarafi sinif onayindan BAGIMSIZ hesaplanir. Yeni ID ilk 2-3 kare
            # "belirsiz" siniftadir; o sirada renk bilgisini de kaybedersek eski
            # DUSMAN kilidi yakindaki DOST kutuya devredilebilir.
            renk_tip = _taraf_belirle(frame, (x1, y1, x2, y2), tid) \
                if asama == 3 else "Hedef"
            taraf = "Belirsiz" if cls == "belirsiz" else renk_tip

            det_obj = {"cls": cls, "ham": ham_ad, "ad": "?" if cls == "belirsiz" else goster_ad(cls, ham_ad),
                         "tip": taraf, "conf": int(round(conf * 100)),
                         "renk_tip": renk_tip, "box": (x1, y1, x2, y2), "id": tid}
            dets.append(det_obj)
            if tid is not None and tid in _takip_durumlari:
                _takip_durumlari[tid]["son_det"] = dict(det_obj)

    # Ayni nesneye atilmis cift kutulari ele (NMS sinif ici calistigi icin farkli
    # sinif etiketli ciftleri temizleyemez — bkz. _cift_kutulari_ele).
    dets = _cift_kutulari_ele(dets, float(a["ortusme"]))

    # Model, bir kisiyi yuksek guvenle maket sanabilir. A2/A3 otomatik kilitte
    # yalniz bu KARENIN kirmizisini kabul et; taraf hafizasi edinim izni degildir.
    if asama in (2, 3):
        for d in dets:
            d["anlik_kirmizi"] = anlik_kirmizi_kaniti(frame, d["box"])

    _hafiza_buda(canli_idler)
    _kayiplari_temizle(canli_idler, int(a["kararlilik"]))
    _vurulanlari_guncelle(dets, time.time())

    # Kilit: A3'te yalniz Düşman (dosta ates yok), A1/A2'de her tespit hedeftir.
    if estop:
        _kilitli_track_id = None

    active_idx = -1
    if not estop and dets:
        locked_idx = -1
        if _kilitli_track_id is not None:
            locked_idx = next((i for i, d in enumerate(dets) if d["id"] == _kilitli_track_id), -1)

        if locked_idx != -1:
            # Kilitli nesne dets icinde bulunduysa (sekli, sinifi ne olursa olsun) devam
            active_idx = locked_idx
        else:
            # Kilitli hedef dets icinde yok.
            if _kilitli_track_id is None:
                # HIC KILIT YOK: Ilk defa kilitlenmek uzere hedef ara
                if time.time() >= _kilitleme_yasagi_t:
                    if asama in (2, 3):
                        aday = [i for i, d in enumerate(dets)
                                if d["anlik_kirmizi"] and (asama != 3 or d["tip"] == "Düşman")]
                    else:
                        aday = list(range(len(dets)))
                    # Operator hangi TIPI aradigini sectiyse yalniz onlara kilitlen.
                    aday = [i for i in aday if _tip_uygun(dets[i]["cls"])
                            and not vurulan_mi(dets[i])]

                    if aday:
                        en_iyi = max(aday, key=lambda i: dets[i]["conf"])
                        # Tek karelik yuksek guvenli yanlis kutuya nisan alma. Ilk
                        # otomatik kilit, sinif histerezisi hedefi birkac karede
                        # ONAYLADIKTAN sonra kurulur. Operator elle secerek dusuk
                        # guvenli ama gercek bir hedefi yine aninda kilitleyebilir.
                        if dets[en_iyi]["id"] is not None and _onayli_mi(dets[en_iyi]["id"]):
                            _kilitli_track_id = dets[en_iyi]["id"]
                            active_idx = en_iyi
            else:
                # KILIT VARDI AMA KAYBOLDU: Asla baska bir nesneye (ornegin kola) atlama.
                # Tek istisna: Tracker objeyi kaybedip ayni yerde yeni bir ID ile bulmussa.
                if _kilitli_track_id in _takip_durumlari and "son_det" in _takip_durumlari[_kilitli_track_id]:
                    # Son goruldugu yerin YAKININDA (kutuyla olcekli yaricap) bir kutu var mi?
                    son_det = _takip_durumlari[_kilitli_track_id]["son_det"]
                    # A2/A3: yeni ID ancak BU KAREDE kirmizi gorunuyorsa devralabilir;
                    # yoksa drone'u tutan kisinin yanlis "maket" kutusu kilidi calar.
                    ayni_yerdekiler = [i for i, d in enumerate(dets)
                                       if _yeniden_kilit_uyumlu(d, son_det)
                                       and not vurulan_mi(d)
                                       and (asama not in (2, 3) or d.get("anlik_kirmizi"))]
                    if ayni_yerdekiler:
                        # Ayni nesne yeni ID almis! Kilidi buna devret (guven onemli degil)
                        en_iyi = max(ayni_yerdekiler, key=lambda i: dets[i]["conf"])
                        _kilitli_track_id = dets[en_iyi]["id"]
                        active_idx = en_iyi

                # Ayni yerde degilse, veya hafiza tamamen silindiyse HICBIR SEY YAPMA.
                # Kilit baska bir seye SIÇRAMAZ.

    # UZAK HEDEF EDINIMI: kilit yok ve ana tarama da kilitlenecek bir sey vermedi.
    if (active_idx == -1 and not estop and _kilitli_track_id is None
            and time.time() >= _kilitleme_yasagi_t
            and not _ana_taramada_guclu_aday(dets, a, asama)):
        try:
            active_idx = _uzak_edinim(model, frame, dets, a, asama, gosterim)
        except Exception as e:
            print(f"[UYARI] Uzak hedef taramasi basarisiz: {e}")
    elif _kilitli_track_id is not None:
        _uzak["aday"] = None

    # KILIT PENCERESI: ana tarama kilitli hedefi bulamadiysa son yerinin cevresini
    # tam cozunurlukte bir kez daha tara (bkz. _roi_bul). Bulunursa GERCEK tespittir
    # (kontrol girdisi olur), hayalet degil.
    if (active_idx == -1 and not estop and _kilitli_track_id is not None
            and int(a.get("roi_tespit", 1)) and _kilit_kayip_kare < ROI_AZAMI_KAYIP
            and "son_det" in _takip_durumlari.get(_kilitli_track_id, {})):
        son_det = _takip_durumlari[_kilitli_track_id]["son_det"]
        m_roi = _roi_modeli_al(model)
        roi = None
        if m_roi is not None:
            try:
                roi = _roi_bul(m_roi, frame, son_det, float(a.get("roi_esik", 0.30)))
            except Exception as e:
                print(f"[UYARI] Kilit penceresi taramasi basarisiz: {e}")
        if roi is not None:
            renk_tip = (_taraf_belirle(frame, roi["box"], _kilitli_track_id)
                        if asama == 3 else "Hedef")
            det_obj = dict(son_det, conf=int(round(roi["conf"] * 100)), box=roi["box"],
                           renk_tip=renk_tip, id=_kilitli_track_id, roi=True)
            det_obj.pop("hayalet", None)
            dets.append(det_obj)
            active_idx = len(dets) - 1
            hafiza = dict(det_obj)
            hafiza.pop("roi", None)          # hayalet bu kopyadan uretilir; isaret tasimasin
            _takip_durumlari[_kilitli_track_id]["son_det"] = hafiza
            # Hedef yalniz pencereyle izleniyorsa ByteTrack onu GORMUYOR; kayip sayaci
            # artmaya devam etse kilit `kararlilik` kare sonra (~1 sn) duserdi.
            _kayip_sayaclari[_kilitli_track_id] = 0

    # KIRMIZI KAYBI — YALNIZ ASAMA 3 (23.09'da A2'den kaldirildi): kilitli GERCEK kutu
    # art arda kirmizisiz kalirsa kilit baska bir nesneye (cogunlukla hedefi tutan
    # insana) kaymis demektir; birak ki gercek hedef yeniden edinilsin.
    # ⚠ A2'de artik calismaz: orada TUM hedefler dusmandir, rengi okuyamamak
    #   (isik/boya/uzaklik) kilidi birakmak icin sebep degildir — sistem hedefi
    #   takip edemez hale geliyordu. A3'te ise renk dost/dusman demektir, kalir.
    if asama == 3 and _kilitli_track_id is not None and 0 <= active_idx < len(dets):
        d_ = dets[active_idx]
        if not d_.get("hayalet") and not d_.get("roi"):
            kirmizi_ = d_.get("anlik_kirmizi")
            if kirmizi_ is None:
                kirmizi_ = anlik_kirmizi_kaniti(frame, d_["box"])
            _kirmizisiz[0] = 0 if kirmizi_ else _kirmizisiz[0] + 1
            if _kirmizisiz[0] >= KIRMIZISIZ_AZAMI:
                _kirmizisiz[0] = 0
                _kilitli_track_id = None
                _kilit_kayip_kare = 0
                active_idx = -1
    else:
        _kirmizisiz[0] = 0

    # ZAMANLA KILIT BIRAKMA (bkz. KILIT_BIRAKMA_S): buraya kadar GERCEK bir kutu
    # (kendi ID'si, yeni ID devri ya da kilit penceresi) bulunamadiysa ve son gercek
    # gorulmeden beri KILIT_BIRAKMA_S gectiyse kilit duser — hayalet de cizilmez,
    # otomatik kilit ve uzak tarama bir sonraki karede yeni hedefi arayabilir.
    if _kilitli_track_id is not None:
        simdi_k = time.time()
        if _kilit_son_gercek[0] != _kilitli_track_id or active_idx != -1:
            _kilit_son_gercek[:] = [_kilitli_track_id, simdi_k]
        elif simdi_k - _kilit_son_gercek[1] > KILIT_BIRAKMA_S:
            _kilitli_track_id = None
            _kilit_kayip_kare = 0
            _kilit_son_gercek[:] = [None, 0.0]

    # HAYALET HEDEF: kilitli nesne bu karede ne kendi ID'siyle ne de yakinindaki yeni
    # bir ID'yle bulunabildiyse son kutusu listeye eklenir (kutu istikrari).
    # ⚠ SIRA ONEMLI: hayalet, GERCEK tespitlerle yeniden eslestirme (yukarida)
    #   BASARISIZ OLDUKTAN SONRA eklenir. Eskiden kilit mantigindan ONCE ekleniyordu:
    #   kilit, kilitli ID'yi hayalette bulup "var" sayiyor, ayni nesnenin YENI ID'li
    #   gercek kutusunu hic denemiyordu. Kol hizli donunce ByteTrack ID degistirir;
    #   drone kadrajda net gorunurken hayaletin omru (kararlilik, ~1 sn) boyunca
    #   takip DURUYORDU. Sanal hareketli hedef testinde hedef yalniz karelerin
    #   %35-63'unde "gorulmustu"; kol dururken ayni acilarda %100 goruluyordu.
    if (active_idx == -1 and not estop and _kilitli_track_id is not None
            and _kilitli_track_id in _takip_durumlari
            and "son_det" in _takip_durumlari[_kilitli_track_id]):
        hayalet = dict(_takip_durumlari[_kilitli_track_id]["son_det"])
        hayalet.pop("roi", None)
        hayalet["conf"] = 1  # Cizimde KIRMIZI (dusuk guven) gorunmesi icin
        # ⚠ HAYALET = YALNIZ GOSTERIM, ASLA KONTROL GIRDISI DEGIL.
        # Kutu KARE KOORDINATLARINDA DONMUSTUR: gimbal donse bile yerinden
        # kipirdamaz. Gercek hedefte geri besleme kapanir (gimbal doner ->
        # hedef kadrajda kayar -> hata kuculur); hayalette hata HIC azalmaz,
        # PD ayni yone komut uretmeye devam eder ve namlu yazilimsal tavana
        # kadar tirmanir (16.08'de tilt'in 180'e dayanmasinin sebebi buydu:
        # 30 kare x ~15 FPS = 2 sn, Normal hizda 80 dereceye kadar kacis).
        # Bu bayragi okuyan yer: arayuz_qt.InferenceThread.run.
        hayalet["hayalet"] = True
        dets.append(hayalet)
        active_idx = len(dets) - 1

    # Bir sonraki analiz karesinin cozumurluk kararini besle. Hayalet gosterimde
    # aktif sayilsa da GERCEK tespit degildir; kayip sayaci ilerlemelidir.
    aktif_gercek = (0 <= active_idx < len(dets) and not dets[active_idx].get("hayalet"))
    if _kilitli_track_id is not None and not aktif_gercek:
        _kilit_kayip_kare += 1
    else:
        _kilit_kayip_kare = 0
    _arama_kare = _arama_kare + 1 if _kilitli_track_id is None else 0
    try:
        _zor_ornek(frame, dets, active_idx,
                   {kanonik(v): int(k) for k, v in (r.names or {}).items()}, a)
    except Exception as e:                # veri toplama asla takibi durdurmamali
        print(f"[UYARI] Zor ornek kaydedilemedi: {e}")
    return dets, balonlar, active_idx


def nisan_noktasi(box, balonlar=()):
    """Hedef kutusundan lazerin nisan alacagi pikseli cikarir. (x, y) doner.

    Nisan noktasi BALONDUR, maket govdesi DEGIL: imha kaniti balonun patlamasi
    ve balon maketin ALTINDA (CLAUDE.md §7).

    Iki yol, oncelik sirasiyla:
      1. GERCEK BALON TESPITI — model balonu goruyorsa (ileride 5. sinif) ve balon
         bu hedefin altinda/hizasindaysa dogrudan onun merkezine nisan alinir.
      2. GEOMETRIK KESTIRIM — bugunku model (best.pt) 4 sinif taniyor, balon YOK.
         Balonun yeri maketten hesaplanir: kutunun ALT KENARINDAN, kutu
         yuksekliginin `balon_ofset` kati kadar asagisi.

    Neden ORAN, neden sabit ACI degil: balon maketin altinda sabit bir FIZIKSEL
    mesafede durur; acisal karsiligi mesafeyle degisir (30 cm -> 5 m'de 3.4°,
    15 m'de 1.1°). Kutu yuksekligi de ayni oranda kuculdugu icin oransal ofset
    5/10/15 m'de KENDILIGINDEN dogru kalir.

    ⚠ BURASI TEK KAYNAK. Uc yer buradan beslenir: PD kontrolcusu
    (nisan.PDNisanci uzerinden), Qt canli gorunumdeki nisangah ve asagidaki
    draw_overlay. Ayri ayri hesaplansalardi ekran, lazerin gercekte gittigi
    yerden BASKA bir nokta gosterirdi — operator de kalibrasyonu (balon_ofset)
    neye gore cevirecegini goremezdi.
    """
    x1, y1, x2, y2 = box
    hx = (x1 + x2) * 0.5

    # GOVDE MODU: balonsuz arac takibi. Nisan noktasi kutunun merkezi olur,
    # balon tespiti/kestirimi yok sayilir. Bkz. VARSAYILAN_AYAR["nisan_govde"].
    if int(AYAR.get("nisan_govde", 0)):
        return (hx, (y1 + y2) * 0.5)

    # Birden fazla balon bu hedefin altina duserse (ek balon modeli ayni sahnede
    # birkac aday bulabilir) EN YAKIN olan secilir: balon maketin asilma
    # noktasindan sarkar, yani kutunun ALT ORTASINA en yakin aday odur. "Listede
    # ilk gelen" secilseydi nisan noktasi model sirasina gore kare kare
    # ziplayabilirdi — PD icin bu, hedefin kendisinin ziplamasiyla ayni sey.
    uygun = []
    for bx1, by1, bx2, by2 in balonlar:
        bcx = (bx1 + bx2) * 0.5
        bcy = (by1 + by2) * 0.5
        # Yatayda bu hedefin altinda mi (baskasinin balonu sayilmasin) ve
        # dikeyde govde merkezinden asagida mi?
        if x1 <= bcx <= x2 and bcy >= (y1 + y2) * 0.5:
            uygun.append(((bcx - hx) ** 2 + (bcy - y2) ** 2, bcx, bcy))
    if uygun:
        _, bcx, bcy = min(uygun)
        return (bcx, bcy)

    oran = float(AYAR.get("balon_ofset", VARSAYILAN_AYAR["balon_ofset"]))
    return (hx, y2 + (y2 - y1) * oran)


def draw_overlay(frame, dets, active_idx, balonlar=(), estop=False):
    """BGR kareye kutu + etiket + nisan cizer."""

    # --- Sabit Merkez Nisangahi (Lazer referansi) ---
    h, w = frame.shape[:2]
    mcx, mcy = w // 2, h // 2
    cv2.line(frame, (mcx - 20, mcy), (mcx + 20, mcy), (0, 255, 0), 2, cv2.LINE_AA)
    cv2.line(frame, (mcx, mcy - 20), (mcx, mcy + 20), (0, 255, 0), 2, cv2.LINE_AA)
    cv2.circle(frame, (mcx, mcy), 3, (0, 255, 0), -1, cv2.LINE_AA)

    for bx in balonlar:
        x1, y1, x2, y2 = bx
        cv2.rectangle(frame, (x1, y1), (x2, y2), YELLOW, 1, cv2.LINE_AA)
        cv2.putText(frame, "BALON", (x1, max(12, y1 - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, YELLOW, 1, cv2.LINE_AA)
    for i, d in enumerate(dets):
        tip = d["tip"]
        # Renkler yukaridaki paletten gelir. Bir sure burada CYAN ve GRAY yaziyordu;
        # ikisi de TANIMLI DEGILDI (13.08 sadelestirmesinde silinmisler) -> "Dost" ve
        # taraf-siz (A1/A2) her tespit NameError ile cokuyordu. Qt arayuzu kutulari
        # kendi cizdigi icin canli uygulamada bu yol calismiyor ve hata gorunmuyordu.
        if tip == "Dost":
            color = BLUE
        elif tip == "Düşman":
            color = RED
        else:
            color = HEDEF        # A1/A2: taraf ayrimi yok, hepsi hedef
        
        x1, y1, x2, y2 = d["box"]
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2, cv2.LINE_AA)
        
        # Juri icin yaziyi yana dogru uazatmak yerine IKI SATIRA boldum
        # 1. Satir: Dost/Dusman
        # 2. Satir: Hedef Tipi ve Skor
        tip_cv = {"Düşman": "Dusman", "Dost": "Dost"}.get(tip)
        ad_cv = "?" if d["cls"] == "belirsiz" else goster_ad_cv(d["cls"], d.get("ham", d["cls"]))
        
        f, fs, ft = cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1
        txt1 = f"{tip_cv}" if tip_cv else ""
        txt2 = f"{ad_cv} %{d['conf']}"
        
        (tw1, th1), _ = cv2.getTextSize(txt1, f, fs, ft) if txt1 else ((0,0), 0)
        (tw2, th2), _ = cv2.getTextSize(txt2, f, fs, ft)
        
        tw = max(tw1, tw2)
        toplam_h = (th1 + th2 + 6) if txt1 else th2
        
        ly = max(y1 - 5, toplam_h + 10)
        cv2.rectangle(frame, (x1, ly - toplam_h - 10), (x1 + tw + 8, ly + 4), color, -1, cv2.LINE_AA)
        
        if txt1:
            cv2.putText(frame, txt1, (x1 + 4, ly - th2 - 6), f, fs, (255, 255, 255), ft, cv2.LINE_AA)
        cv2.putText(frame, txt2, (x1 + 4, ly), f, fs, (255, 255, 255), ft, cv2.LINE_AA)
        # Nisan isareti yalniz kilitli hedefe (active_idx asamaya gore secildi, dosta cizilmez).
        # Kutu merkezine DEGIL, gimbalin gercekten nisan aldigi noktaya (balon) cizilir.
        if i == active_idx and not estop:
            hx, hy = nisan_noktasi(d["box"], balonlar)
            cx, cy = int(hx), int(hy)
            gcx, gcy = (x1 + x2) // 2, (y1 + y2) // 2
            cv2.line(frame, (gcx, gcy), (cx, cy), color, 1, cv2.LINE_AA)   # govde -> nisan bagi
            cv2.circle(frame, (cx, cy), 16, color, 2, cv2.LINE_AA)
            cv2.line(frame, (cx - 22, cy), (cx + 22, cy), color, 1, cv2.LINE_AA)
            cv2.line(frame, (cx, cy - 22), (cx, cy + 22), color, 1, cv2.LINE_AA)
    return frame


if __name__ == "__main__":
    ZOR_ORNEK_DIZIN = tempfile.mkdtemp()   # testler gercek veri_toplama klasorune yazmasin
    # Kendi kendine test — kamera/model gerektirmez.

    # Sinif adi sadelestirme; bilinmeyen sinif ATILMAZ, ham adiyla gosterilir.
    assert kanonik("F-16") == "f16"
    assert kanonik("Mini_Drone") == "minidrone"
    assert kanonik("kus") == "kus"
    assert goster_ad("f16", "F-16") == "F-16"           # bilinen -> Turkce ad
    assert goster_ad("kus", "kus") == "kus"             # bilinmeyen -> ham ad
    assert goster_ad_cv("drone", "drone") == "IHA"      # cizim icin ASCII

    # Bozuk/asiri ayar degerleri araliga kirpilir, bilinmeyen anahtar yok sayilir.
    ayar_guncelle(hassasiyet=9.9, kararlilik=-5, cozunurluk="abc", bilinmeyen=1)
    assert AYAR["hassasiyet"] == 0.95 and AYAR["kararlilik"] == 5
    assert AYAR["cozunurluk"] == VARSAYILAN_AYAR["cozunurluk"]   # cevrilemedi -> varsayilan
    assert "bilinmeyen" not in AYAR
    ayar_guncelle(**VARSAYILAN_AYAR)
    assert ayar_al() == VARSAYILAN_AYAR

    # Tracker yaml ultralytics varsayilanlariyla yazilmali.
    _tracker_yaml_yaz(ayar_al())
    ic = open(_TRACKER_YAML, encoding="utf-8").read()
    assert "new_track_thresh: 0.250" in ic and "track_buffer: 30" in ic, ic

    # Taraf hafizasi budanmali (sinirsiz buyumemeli).
    _taraf_hafiza.update({i: "Düşman" for i in range(50)})
    for _ in range(BUDAMA_PERIYOT):
        _hafiza_buda({1, 2, 3})
    assert set(_taraf_hafiza) == {1, 2, 3}, _taraf_hafiza
    takip_sifirla()

    # A3 taraf karari: renk yoksa yeni hedef DUSMAN varsayilmaz; eski guvenilir
    # karar korunur. Kirmizi/cyan neredeyse esitse tek karede taraf cevrilmez.
    _gercek_renk_oranlari = renk_oranlari
    try:
        renk_oranlari = lambda frame, box: (0.0, 0.0)
        assert _taraf_belirle(None, None, 91) == "Belirsiz"
        _taraf_hafiza[91] = "Dost"
        assert _taraf_belirle(None, None, 91) == "Dost"
        renk_oranlari = lambda frame, box: (0.040, 0.045)  # fark karar icin yetersiz
        assert _taraf_belirle(None, None, 91) == "Dost"
        renk_oranlari = lambda frame, box: (0.080, 0.020)
        assert _taraf_belirle(None, None, 92) == "Düşman"
        renk_oranlari = lambda frame, box: (0.020, 0.080)
        assert _taraf_belirle(None, None, 93) == "Dost"
    finally:
        renk_oranlari = _gercek_renk_oranlari
    takip_sifirla()

    # ---- KESIN TANIMA (_karar_ver) ----
    ESIK, TEKRAR = 0.70, 3

    def besle(tid, kareler):
        """kareler: [(sinif, conf), ...] -> son karedeki karar."""
        son = None
        for sinif, conf in kareler:
            son = _karar_ver(tid, sinif, conf, ESIK, TEKRAR)
        return son

    # 3 guclu kare -> onay
    assert besle(1, [("f16", 0.9)] * 3) == "f16"
    takip_sifirla()

    # DALGALI GUVEN: aradaki zayif kare onayi ENGELLEMEMELI (eski kod sifirlardi).
    # (+1 +1 -1 +1 +1 = 3) -> onay
    assert besle(1, [("f16", 0.9), ("f16", 0.8), ("f16", 0.5),
                     ("f16", 0.85), ("f16", 0.9)]) == "f16"
    takip_sifirla()

    # Surekli zayif kalan hedef onaylanmamali.
    assert besle(1, [("f16", 0.5)] * 20) is None
    takip_sifirla()

    # Tek karelik yanlis sinif tahmini adayi DEVIRMEMELI — yalnizca onayi geciktirir.
    # (+1 +1 -1(fuze) +1 = 2 -> heniz onay yok, ama aday hala f16)
    assert besle(1, [("f16", 0.9), ("f16", 0.9), ("fuze", 0.9), ("f16", 0.9)]) is None
    assert _takip_durumlari[1]["aday_sinif"] == "f16", "rakip sinif adayi devirdi"
    assert _karar_ver(1, "f16", 0.9, ESIK, TEKRAR) == "f16"   # bir kare daha -> onay
    takip_sifirla()

    # ISRARLI yanlis sinif adayi devirebilmeli (model gercekten fikir degistirdiyse).
    assert besle(1, [("f16", 0.9), ("f16", 0.9)]) is None
    assert besle(1, [("fuze", 0.9)] * 5) == "fuze", "israrli dogru sinif adayi deviremedi"
    takip_sifirla()

    # AYNI SINIFTAN IKI HEDEF: ikisi de onaylanmali (sartname: Asama 2'de 3 hedef,
    # Asama 3'te dusman F16 + dost F16 ayni karede olabilir).
    assert besle(1, [("f16", 0.9)] * 3) == "f16"
    assert besle(2, [("f16", 0.9)] * 3) == "f16", "ayni siniftan ikinci hedef onaylanmadi"
    takip_sifirla()

    # Onaydan sonra sinif SABIT: zayif kareler kutuyu kaybettirmez...
    besle(1, [("f16", 0.9)] * 3)
    assert besle(1, [("f16", 0.3)] * (ONAY_BOZULMA - 1)) == "f16"
    assert _onayli_mi(1)
    # ...ama UZUN sureli zayiflik onayi dusurur (yanlis onay sonsuza dek yasamasin).
    assert besle(1, [("f16", 0.3)] * 2) is None
    assert not _onayli_mi(1)
    takip_sifirla()

    # Onayli track baska sinif gorse bile tipini degistirmez (etiket titremesin).
    besle(1, [("f16", 0.9)] * 3)
    assert besle(1, [("fuze", 0.95)]) == "f16"
    takip_sifirla()

    # ---- CAKISAN KUTU TEMIZLIGI (_ortusme / _cift_kutulari_ele) ----
    # Ortusme orani kucuk kutuya gore olculur: ic ice kutu IoU ile yakalanmaz.
    assert _ortusme((0, 0, 100, 100), (0, 0, 100, 100)) == 1.0        # birebir ayni
    assert _ortusme((0, 0, 100, 100), (200, 200, 300, 300)) == 0.0    # hic degmiyor
    assert _ortusme((0, 0, 100, 100), (25, 25, 75, 75)) == 1.0        # kucuk TAMAMEN icinde
    assert abs(_ortusme((0, 0, 100, 100), (50, 0, 150, 100)) - 0.5) < 1e-6   # yarim

    def kutu(cls, conf, box, tid=1):
        return {"cls": cls, "ham": cls, "ad": cls, "tip": "Hedef",
                "conf": conf, "box": box, "id": tid}

    # Ayni nesneye iki FARKLI SINIF etiketi -> biri elenmeli (NMS'in yapamadigi is).
    d = _cift_kutulari_ele([kutu("fuze", 60, (10, 10, 110, 110)),
                            kutu("helikopter", 85, (12, 12, 112, 112))], 0.60)
    assert len(d) == 1 and d[0]["cls"] == "helikopter", d      # guveni yuksek olan kalir

    # KESIN TANINMIS hedef, o karede daha guvenli cikan "belirsiz" kutuya yenilmez.
    d = _cift_kutulari_ele([kutu("belirsiz", 95, (10, 10, 110, 110)),
                            kutu("f16", 55, (12, 12, 112, 112))], 0.60)
    assert len(d) == 1 and d[0]["cls"] == "f16", d

    # AYRI hedefler (Asama 2 surusu) korunmali — az ortusme eleme sebebi degil.
    ayri = [kutu("fuze", 80, (0, 0, 100, 100), 1),
            kutu("drone", 80, (90, 0, 190, 100), 2),
            kutu("fuze", 80, (300, 0, 400, 100), 3)]
    assert len(_cift_kutulari_ele(ayri, 0.60)) == 3, "ayri hedefler elendi"

    # Esik 0.99'da temizlik pratikte KAPALI olmali (operator kapatabilmeli).
    ikiz = [kutu("fuze", 60, (10, 10, 110, 110)), kutu("helikopter", 85, (12, 12, 112, 112))]
    assert len(_cift_kutulari_ele(ikiz, 0.99)) == 2

    # Kutu sirasi korunmali (active_idx bu listeye gore secilir).
    sirali = _cift_kutulari_ele([kutu("f16", 90, (0, 0, 50, 50), 1),
                                 kutu("drone", 70, (300, 300, 350, 350), 2)], 0.60)
    assert [x["cls"] for x in sirali] == ["f16", "drone"], sirali

    # Kayip ID hafizadan silinmeli; esik "kararlilik" ayarindan gelir.
    besle(7, [("f16", 0.9)] * 3)
    for _ in range(5):
        _kayiplari_temizle(set(), 5)
    assert 7 not in _takip_durumlari, "kayip ID hafizada kaldi"
    takip_sifirla()

    # ---- HAYALET HEDEF: gosterim yardimcisi, KONTROL GIRDISI DEGIL ----
    # Kutu kare koordinatlarinda DONMUS oldugu icin nisan alinirsa hata hic azalmaz
    # ve namlu yazilimsal tavana tirmanir (16.08: tilt 180'e dayandi). Bayragi
    # arayuz_qt.InferenceThread okur ve o karede komut URETMEZ.
    class _SahteKutu:
        def __init__(self, cls, conf, box, tid):
            self.cls, self.conf, self._box = cls, conf, box
            self.id = type("I", (), {"item": lambda s, v=tid: v})() if tid else None
            self.xyxy = [type("X", (), {"tolist": lambda s, b=box: list(b)})()]

    class _SahteSonuc:
        def __init__(self, kutular, adlar):
            self.boxes, self.names = kutular, adlar

    class _SahteModel:
        def __init__(self):
            self.kutular = [_SahteKutu(0, 0.95, (100, 100, 200, 180), 1)]
            self.son_imgsz = None
        def track(self, frame, **kw):
            self.son_imgsz = kw.get("imgsz")
            return [_SahteSonuc(self.kutular, {0: "f16"})]

    import numpy as _np
    kare = _np.zeros((480, 640, 3), _np.uint8)
    sahte = _SahteModel()
    takip_sifirla()
    ilk_aktifler = []
    for _ in range(4):                      # gercek tespitlerle kilit kurulsun
        dets, _b, aktif = analiz_et(sahte, kare, asama=1)
        ilk_aktifler.append(aktif)
    assert ilk_aktifler[:2] == [-1, -1], "onaysiz tek-kare kutuya erken nisan alindi"
    assert aktif >= 0, "gercek tespitte kilit kurulmadi"
    assert not dets[aktif].get("hayalet"), "gercek tespit hayalet isaretlenmemeli"

    sahte.kutular = []                      # hedef kayboldu -> hayalet devreye girer
    dets, _b, aktif = analiz_et(sahte, kare, asama=1)
    assert aktif >= 0, "hayalet aktif hedef olarak korunmali (kutu istikrari)"
    assert dets[aktif].get("hayalet") is True, "kayip hedef HAYALET isaretlenmeliydi"
    assert dets[aktif]["conf"] == 1

    # REGRESYON: ByteTrack ayni hedefi yakinda YENI ID ile tekrar buldugunda gercek
    # kutu hayaletten once degerlendirilmeli ve kilit yeni ID'ye aktarilmali. Hayalet
    # once eklenirse eski ID "hala goruluyor" sanilir, gercek ID hic denenmez ve
    # otonom takip kararlilik suresi boyunca (~1 sn) bos yere durur.
    sahte.kutular = [_SahteKutu(0, 0.95, (150, 100, 250, 180), 2)]
    dets, _b, aktif = analiz_et(sahte, kare, asama=1)
    assert aktif >= 0 and dets[aktif]["id"] == 2, (aktif, dets)
    assert not dets[aktif].get("hayalet"), "yeni ID'li GERCEK kutu yerine hayalet secildi"
    assert _kilitli_track_id == 2, "kilit yeni ByteTrack ID'sine aktarilmadi"
    assert sahte.son_imgsz == 1024, "kilit kaybinda yuksek-cozunurluk kurtarma karesi calismadi"

    # KILIT PENCERESI: ana tarama kilitli hedefi kaybetti; kirpilmis pencerede
    # bulunan uyumlu kutu GERCEK aktif hedef olur (hayalet degil), kare koordinatina
    # cevrilir. Uyumsuz (uzak) kutuya ise kilit ATLAMAZ -> hayalete duser.
    class _SahteRoi:
        def __init__(self, kutular):
            self.kutular, self.son_boyut = kutular, None

        def predict(self, kirpik, **kw):
            self.son_boyut = kirpik.shape[:2]
            return [_SahteSonuc(self.kutular, {0: "f16"})]

    son_kutu = _takip_durumlari[2]["son_det"]["box"]            # (150,100,250,180)
    ox = int(min(max(0, 200 - 480 / 2), 640 - 480)); oy = int(min(max(0, 140 - 480 / 2), 480 - 480))
    roi_m = _SahteRoi([_SahteKutu(0, 0.6, (160 - ox + 10, 100 - oy, 260 - ox + 10, 180 - oy), None)])
    roi_modeli_ayarla(roi_m)
    sahte.kutular = []
    dets, _b, aktif = analiz_et(sahte, kare, asama=1)
    assert roi_m.son_boyut == (480, 480), roi_m.son_boyut          # 6 x 100 px, kare yuksekligi sinir
    assert aktif >= 0 and dets[aktif].get("roi") and not dets[aktif].get("hayalet"), dets
    assert dets[aktif]["id"] == 2 and dets[aktif]["box"] == (170, 100, 270, 180), dets[aktif]
    roi_m.kutular = [_SahteKutu(0, 0.9, (5, 5, 60, 60), None)]     # kilitten uzak kutu
    dets, _b, aktif = analiz_et(sahte, kare, asama=1)
    assert dets[aktif].get("hayalet") and not dets[aktif].get("roi"), "uzak kutuya atladi"
    roi_modeli_ayarla(None)
    takip_sifirla()

    # ---- ZAMANLA KILIT BIRAKMA: giden hedefin kilidi/hayaleti yeni hedefi ENGELLEMEZ ----
    # 23.09 koridor: hedef gidince kutu kaldi; yeni hedef ancak kamera elle kapatilip
    # kilit dusunce goruldu. Kilit artik KILIT_BIRAKMA_S icinde gercek kutu gelmezse duser.
    sahte.kutular = [_SahteKutu(0, 0.95, (100, 100, 200, 180), 1)]
    for _ in range(4):
        dets, _b, aktif = analiz_et(sahte, kare, asama=1)
    assert _kilitli_track_id == 1
    sahte.kutular = []
    dets, _b, aktif = analiz_et(sahte, kare, asama=1)
    assert _kilitli_track_id == 1 and dets[aktif].get("hayalet"), "kisa kopmada kilit korunmali"
    _kilit_son_gercek[1] -= KILIT_BIRAKMA_S + 0.1        # sure doldu (gercek kutu yok)
    dets, _b, aktif = analiz_et(sahte, kare, asama=1)
    assert _kilitli_track_id is None, "giden hedefin kilidi dusmedi"
    assert aktif == -1 and not any(d.get("hayalet") for d in dets), "kilit dustu ama hayalet cizildi"
    sahte.kutular = [_SahteKutu(0, 0.95, (400, 250, 480, 310), 5)]   # YENI hedef baska yerde
    for _ in range(4):
        dets, _b, aktif = analiz_et(sahte, kare, asama=1)
    assert _kilitli_track_id == 5, "eski kilit dustukten sonra yeni hedefe kilitlenilmedi"
    takip_sifirla()

    # ---- VURULAN HEDEF: yalniz O hedef yasaklanir, digerine HEMEN gecilir ----
    iki = [_SahteKutu(0, 0.95, (100, 100, 200, 180), 1), _SahteKutu(0, 0.85, (400, 250, 480, 310), 3)]
    sahte.kutular = list(iki)
    for _ in range(4):
        dets, _b, aktif = analiz_et(sahte, kare, asama=1)
    assert _kilitli_track_id == 1, "kurulum: en guvenli hedefe kilit"
    assert hedef_vuruldu(10.0) == 1 and _kilitli_track_id is None
    dets, _b, aktif = analiz_et(sahte, kare, asama=1)
    assert _kilitli_track_id == 3, f"vuruldu sonrasi siradaki hedefe gecilmedi: {_kilitli_track_id}"
    # Vurulan maket ByteTrack'te YENI ID alsa da yasak onu izler; siradaki gidince
    # kilit ona geri DONMEZ.
    sahte.kutular = [_SahteKutu(0, 0.95, (104, 100, 204, 180), 9)]
    for _ in range(4):
        dets, _b, aktif = analiz_et(sahte, kare, asama=1)
    assert 9 in _vurulanlar, "yasak yeni ID'ye tasinmadi"
    _kilit_son_gercek[1] -= KILIT_BIRAKMA_S + 0.1
    for _ in range(4):
        dets, _b, aktif = analiz_et(sahte, kare, asama=1)
    assert _kilitli_track_id != 9, "vurulan maket (yeni ID) yeniden kilitlendi"
    # Yasak suresi dolunca yeniden secilebilir.
    for v in _vurulanlar.values():
        v["bitis"] = 0.0
    for _ in range(4):
        dets, _b, aktif = analiz_et(sahte, kare, asama=1)
    assert _kilitli_track_id == 9, "yasak suresi dolunca hedef yeniden secilmeli"
    takip_sifirla()
    assert not _vurulanlar

    # UZAK HEDEF EDINIMI: ana tarama (640/1280) kucuk hedefi hic gormuyor; karo taramasi
    # adayi bulur, kilit penceresi 3 karede dogrular, kilit kurulur ve hedef yalniz
    # pencereyle izlense de `kararlilik`tan uzun sure kilit DUSMEZ.
    class _ParlakModel:                                 # beyaz piksel kumesini "drone" bulur
        def predict(self, girdi, **kw):
            tek = not isinstance(girdi, list)
            out = []
            for k in ([girdi] if tek else girdi):
                ys, xs = _np.nonzero(k[:, :, 0] > 200)
                kut = [_SahteKutu(0, 0.9, (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1), None)] if len(xs) else []
                out.append(_SahteSonuc(kut, {0: "drone"}))
            return out
    bos_model = _SahteModel(); bos_model.kutular = []
    _gpu_durumu = True               # test donanimdan bagimsiz: GPU varmis gibi
    roi_modeli_ayarla(_ParlakModel())
    takip_sifirla()
    buyuk = _np.zeros((720, 1280, 3), _np.uint8)
    hx, hy = 900, 200
    kilit_kare = None
    for i in range(160):
        buyuk[:] = 0
        buyuk[hy:hy + 14, hx + i // 4:hx + i // 4 + 18] = 255   # 18x14 px, yavasca kayar
        dets, _b, aktif = analiz_et(bos_model, buyuk, asama=1)
        if aktif >= 0 and kilit_kare is None:
            kilit_kare = i
        if kilit_kare is not None:
            assert aktif >= 0 and not dets[aktif].get("hayalet"), (i, dets)
            bx1, by1, bx2, by2 = dets[aktif]["box"]
            assert abs(bx1 - (hx + i // 4)) <= 2 and abs(by1 - hy) <= 2, (i, dets[aktif]["box"])
    assert kilit_kare is not None and kilit_kare <= 8, kilit_kare     # tarama + 3 dogrulama
    assert _kilitli_track_id is not None and _kilitli_track_id < 0
    assert bos_model.son_imgsz == 640, bos_model.son_imgsz            # kilit varken normal
    # Asama 3: rengi okunamayan (beyaz) hedef DUSMAN sayilmaz -> kilit KURULMAZ
    takip_sifirla()
    arama_boyutlari = []
    for i in range(20):
        buyuk[:] = 0
        buyuk[hy:hy + 14, hx:hx + 18] = 255
        dets, _b, aktif = analiz_et(bos_model, buyuk, asama=3)
        arama_boyutlari.append(bos_model.son_imgsz)
    assert _kilitli_track_id is None and aktif == -1
    assert 640 in arama_boyutlari and 1280 in arama_boyutlari, arama_boyutlari
    roi_modeli_ayarla(None)
    takip_sifirla()

    # KIRMIZI KAPISI KILIT DEVRINDE (A2): kilitli kirmizi drone bir kare kaybolur,
    # yaninda koyu renkli yanlis "maket" kutusu (insan) belirir -> kilit ONA GECMEZ.
    # Kilitli ID'nin kutusu insana kayarsa KIRMIZISIZ_AZAMI kare sonra kilit birakilir.
    takip_sifirla()
    roi_modeli_ayarla(None)
    sahne = _np.zeros((480, 640, 3), _np.uint8)
    sahne[:] = (200, 200, 200)
    sahne[100:180, 100:200] = (0, 0, 255)                 # kirmizi drone
    sahne[100:180, 180:280] = (60, 60, 60)                # koyu gri insan govdesi
    drn = _SahteKutu(0, 0.95, (100, 100, 200, 180), 7)
    ins = _SahteKutu(0, 0.90, (180, 100, 280, 180), 8)
    sahte.kutular = [drn]
    for _ in range(5):
        dets, _b, aktif = analiz_et(sahte, sahne, asama=2)
    assert _kilitli_track_id == 7, _kilitli_track_id
    sahte.kutular = [ins]                                  # drone kayip, insan yakinda
    dets, _b, aktif = analiz_et(sahte, sahne, asama=2)
    assert _kilitli_track_id == 7 and (aktif < 0 or dets[aktif].get("hayalet")), (_kilitli_track_id, dets)
    # ByteTrack kilitli ID'yi (7) insanin kutusuna tasirsa:
    tasinan = _SahteKutu(0, 0.90, (180, 100, 280, 180), 7)
    sahte.kutular = [tasinan]
    # ASAMA 2'de kilit BIRAKILMAZ (23.09): orada tum hedefler dusmandir, rengi
    # okuyamamak (isik/boya/uzaklik) kilidi birakmak icin sebep degil.
    for _ in range(KIRMIZISIZ_AZAMI + 1):
        dets, _b, aktif = analiz_et(sahte, sahne, asama=2)
    assert _kilitli_track_id == 7, _kilitli_track_id
    # ASAMA 3'te renk dost/dusman demektir: kirmizisiz kalan kilit BIRAKILIR.
    for _ in range(KIRMIZISIZ_AZAMI + 1):
        dets, _b, aktif = analiz_et(sahte, sahne, asama=3)
    assert _kilitli_track_id is None, _kilitli_track_id
    takip_sifirla()

    # ZOR ORNEK: roi/dusuk etiketli, kayip etiketsiz kaydedilir; hiz siniri uygulanir
    _eski_dizin, ZOR_ORNEK_DIZIN = ZOR_ORNEK_DIZIN, tempfile.mkdtemp()
    try:
        _kilitli_track_id = 5
        _zor.update(son_t=0.0, son_bakis=0.0, sayi=0, oturum=None)
        kare2 = _np.zeros((100, 200, 3), _np.uint8)
        ay = {"zor_ornek": 1, "onay_esigi": 0.7}
        roi_det = [{"cls": "f16", "conf": 60, "box": (20, 10, 60, 50), "roi": True}]
        assert _zor_ornek(kare2, roi_det, 0, {"f16": 1}, ay, simdi=1000.0) == "roi"
        assert _zor_ornek(kare2, roi_det, 0, {"f16": 1}, ay, simdi=1000.5) is None   # hiz siniri
        kay = [{"cls": "f16", "conf": 1, "box": (0, 0, 5, 5), "hayalet": True}]
        assert _zor_ornek(kare2, kay, 0, {"f16": 1}, ay, simdi=1002.0) == "kayip"
        iyi = [{"cls": "f16", "conf": 90, "box": (0, 0, 5, 5)}]
        assert _zor_ornek(kare2, iyi, 0, {"f16": 1}, ay, simdi=1004.0) is None       # kolay kare
        kok = os.path.join(ZOR_ORNEK_DIZIN, _zor["oturum"])
        etiketler = sorted(os.listdir(os.path.join(kok, "labels")))
        assert len(etiketler) == 2 and len(os.listdir(os.path.join(kok, "images"))) == 2
        roi_txt = open(os.path.join(kok, "labels", [e for e in etiketler if e.startswith("roi")][0])).read()
        assert roi_txt.split() == ["1", "0.200000", "0.300000", "0.200000", "0.400000"], roi_txt
        assert open(os.path.join(kok, "labels", [e for e in etiketler if e.startswith("kayip")][0])).read() == ""
    finally:
        ZOR_ORNEK_DIZIN = _eski_dizin
        _zor.update(son_t=0.0, son_bakis=0.0, sayi=0, oturum=None)
        takip_sifirla()

    # --- Kilit geri alma: hareket eden hedef, kutuyla olcekli yaricapta YENIDEN bulunur ---
    son = (100, 100, 200, 200)                              # 100 px'lik kutu
    assert _ayni_nesne_olabilir((180, 100, 280, 200), son), "80 px kayan hedef kabul edilmeli"
    assert _ortusme((180, 100, 280, 200), son) < 0.3, "bu durum eskiden REDDEDILIYORDU"
    assert not _ayni_nesne_olabilir((400, 100, 500, 200), son), "300 px otedeki nesneye ATLAMAMALI"
    kucuk = (100, 100, 120, 120)                            # uzak (kucuk) hedef: yaricap da kucuk
    assert not _ayni_nesne_olabilir((160, 100, 180, 120), kucuk), "kucuk hedefte 60 px cok uzak"

    # Yakinlik tek basina yetmez: cok buyuk bir kol/insan kutusu eski hedef kilidini
    # calamaz; A3'te dost ile dusman arasinda da yeniden kilit aktarimi yapilmaz.
    eski = {"box": son, "tip": "Düşman", "renk_tip": "Düşman"}
    uyumlu = {"box": (170, 100, 270, 200), "tip": "Belirsiz", "renk_tip": "Düşman"}
    dev = {"box": (80, 50, 380, 350), "tip": "Belirsiz", "renk_tip": "Düşman"}
    dost = {"box": (170, 100, 270, 200), "tip": "Belirsiz", "renk_tip": "Dost"}
    assert _yeniden_kilit_uyumlu(uyumlu, eski)
    assert not _yeniden_kilit_uyumlu(dev, eski), "dev yakin kutu kilidi caldi"
    assert not _yeniden_kilit_uyumlu(dost, eski), "dusman kilidi dosta aktarildi"
    # KAMERA HAREKETI TELAFISI: ByteTrack izleri ve kilit hafizasi birlikte kayar
    class _Iz:
        def __init__(self, x, y):
            self.mean = [x, y, 1.0, 50.0]

    class _Tr:
        def __init__(self):
            self.tracked_stracks, self.lost_stracks = [_Iz(100.0, 200.0)], [_Iz(10.0, 20.0)]

    class _Pred:
        trackers = [_Tr()]

    class _Mod:
        predictor = _Pred()

    _takip_durumlari[991] = {"son_det": {"box": (0.0, 0.0, 10.0, 10.0)}}
    kamera_kaymasi_bildir(-30.0, 12.0)
    kamera_kaymasi_bildir(-10.0, 0.0)
    assert _kaymayi_uygula(_Mod) == (-40.0, 12.0)
    tr = _Pred.trackers[0]
    assert tr.tracked_stracks[0].mean[:2] == [60.0, 212.0] and tr.lost_stracks[0].mean[:2] == [-30.0, 32.0]
    assert _takip_durumlari[991]["son_det"]["box"] == (-40.0, 12.0, -30.0, 22.0)
    assert _kaymayi_uygula(_Mod) == (0.0, 0.0)           # tuketildi, ikinci kez uygulanmaz
    del _takip_durumlari[991]

    assert _takip_cozunurlugu(640, None, True, 1) == 1024
    assert _takip_cozunurlugu(640, 640, True, 1) == 640  # sabit model degismez
    assert _takip_cozunurlugu(640, None, True, 2) == 640 # her kayip karesinde yavaslatma yok
    assert _takip_cozunurlugu(640, None, False, 0, ARAMA_YUKSEK_PERIYOT) == 1024
    assert _takip_cozunurlugu(640, None, False, 0, 0, 1280) == 640
    assert _takip_cozunurlugu(640, None, False, 0, ARAMA_YUKSEK_PERIYOT, 1280) == 1280
    assert _ana_taramada_guclu_aday([{"id": 1, "conf": 80}], {"onay_esigi": 0.7})
    assert not _ana_taramada_guclu_aday([{"id": 1, "conf": 50}], {"onay_esigi": 0.7})
    assert not _ana_taramada_guclu_aday([{"id": 1, "conf": 90, "anlik_kirmizi": False}],
                                         {"onay_esigi": 0.7}, 2)

    # ARANAN HEDEF TIPI (operator arayuzden secer)
    assert hedef_tipleri() is None and _tip_uygun("fuze") and _tip_uygun("drone")
    assert hedef_tipleri_ayarla(["Füze", "F-16"]) == {"fuze", "f16"}
    assert _tip_uygun("fuze") and _tip_uygun("f16") and not _tip_uygun("drone")
    assert hedef_tipleri_ayarla([]) is None, "bos secim = hepsi"
    assert _tip_uygun("drone")
    # Aranan tipten OLMAYAN guclu kutu uzak taramayi durdurmamali
    hepsi_ay = {"onay_esigi": 0.7}
    assert _ana_taramada_guclu_aday([{"id": 1, "conf": 90, "cls": "drone"}], hepsi_ay)
    hedef_tipleri_ayarla(["fuze"])
    assert not _ana_taramada_guclu_aday([{"id": 1, "conf": 90, "cls": "drone"}], hepsi_ay)
    assert _ana_taramada_guclu_aday([{"id": 1, "conf": 90, "cls": "fuze"}], hepsi_ay)
    # Tip degisince uygun olmayan kilit BIRAKILIR
    _kilitli_track_id = 77
    _takip_durumlari[77] = {"son_det": {"cls": "drone", "box": (0, 0, 10, 10)}}
    hedef_tipleri_ayarla(["helikopter"])
    assert _kilitli_track_id is None, "tip degisti, drone kilidi birakilmaliydi"
    _kilitli_track_id = 77
    hedef_tipleri_ayarla(["drone"])
    assert _kilitli_track_id == 77, "uygun tipte kilit korunmali"
    # Elle tiklama da secili tip kapisini asamaz.
    _kilitli_track_id = None
    assert hedef_sec(77) is True and _kilitli_track_id == 77
    hedef_tipleri_ayarla(["fuze"])
    assert _kilitli_track_id is None and hedef_sec(77) is False
    # Tip degisince onceki tipten yarim kalmis uzak aday silinir.
    _uzak.update(aday={"cls": "drone", "box": (0, 0, 10, 10)}, iyi=2, kotu=0, sayac=3)
    hedef_tipleri_ayarla(["helikopter"])
    assert _uzak["aday"] is None and _uzak["iyi"] == 0 and _uzak["sayac"] == 0
    del _takip_durumlari[77]
    _kilitli_track_id = None
    hedef_tipleri_ayarla(None)

    # KIRMIZI ONERI (uzak tarama nereye baksin) + "model kacirdi" kare kaydi
    kare = _np.full((720, 1280, 3), 60, _np.uint8)
    kare[300:312, 500:521] = (30, 30, 210)            # 21x12 px kirmizi leke = ~15 m hedef
    kare[100:400, 900:1200] = (40, 40, 200)           # buyuk kirmizi yuzey (tisort/kutu)
    oneriler = kirmizi_oneri(kare)
    assert oneriler, "kirmizi leke bulunamadi"
    ilk = oneriler[0]
    assert 495 <= ilk[0] <= 505 and 295 <= ilk[1] <= 305, ("kucuk leke one cikmali", ilk)
    assert all(max(b[2] - b[0], b[3] - b[1]) <= 240 for b in oneriler), "dev yuzey aday oldu"
    p = _oneri_penceresi(kare, ilk)
    assert p[2] - p[0] == p[3] - p[1] == KIRMIZI_ONERI_PENCERE, p
    assert p[0] <= ilk[0] and p[2] >= ilk[2] and p[1] <= ilk[1] and p[3] >= ilk[3], "leke pencere disinda"
    # Pencere kare icinde kalmali (leke kenardayken de)
    kenar = _oneri_penceresi(kare, (2, 2, 8, 8))
    assert kenar[0] >= 0 and kenar[1] >= 0 and kenar[2] <= 1280 and kenar[3] <= 720, kenar
    # Renk kapatilinca eski esit karo taramasina donulur
    assert _uzak_pencereler(kare, {"uzak_kirmizi": 1})[1]
    assert not _uzak_pencereler(kare, {"uzak_kirmizi": 0})[1]
    # KACIRMA: leke var, onu kapsayan tespit yok -> isaret. Kapsayan tespit varsa yok.
    assert _kacirma_mi(kare, [], {}) is not None
    assert _kacirma_mi(kare, [{"box": (500, 300, 521, 312)}], {}) is None
    _zor.update(son_t=0.0, son_bakis=0.0, sayi=0, oturum=None)
    _eski_dizin, ZOR_ORNEK_DIZIN = ZOR_ORNEK_DIZIN, tempfile.mkdtemp()
    try:
        # Kilit YOKKEN de kaydedilmeli — "ben goruyorum, model gormuyor" ani budur.
        assert _kilitli_track_id is None
        assert _zor_ornek(kare, [], -1, {}, {"zor_ornek": 1}, simdi=1000.0) == "kacirma"
        kok = os.path.join(ZOR_ORNEK_DIZIN, _zor["oturum"])
        etiket = os.path.join(kok, "labels", "kacirma_1000000.txt")
        assert os.path.exists(os.path.join(kok, "images", "kacirma_1000000.jpg"))
        assert open(etiket).read() == "", "kacirma karesi ETIKETSIZ kaydedilmeli"
        # Hizi sinirli: ayni saniyede ikincisi yazilmaz
        assert _zor_ornek(kare, [], -1, {}, {"zor_ornek": 1}, simdi=1000.2) is None
    finally:
        ZOR_ORNEK_DIZIN = _eski_dizin
        _zor.update(son_t=0.0, son_bakis=0.0, sayi=0, oturum=None)

    # ---- EK BALON MODELI: DUSMANIN balonu bulunur, DOST'unki ARANMAZ ----
    # Nisan noktasi BALONDUR (imha kaniti balonun patlamasi). Ek model yalniz
    # taninmis hedefin ALT PENCERESINDE kosar; dost hedefe hic ates edilmedigi
    # icin onun penceresi hic taranmaz.
    class _BalonModel:
        """Kirpinti basina sabit bir balon kutusu dondurur (kirpinti koordinatinda)."""
        names = {0: "balloon"}
        def __init__(self, kutular):
            self.kutular, self.cagri = kutular, 0
        def predict(self, girdiler, **kw):
            self.cagri += 1
            return [_SahteSonuc([_SahteKutu(0, 0.9, k, None) for k in self.kutular],
                                self.names) for _ in girdiler]

    kare_b = _np.zeros((480, 640, 3), _np.uint8)
    hedef_kutu = (200, 150, 300, 230)                 # kw=100, kh=80
    pencere = _balon_arama_penceresi(hedef_kutu, kare_b.shape)
    assert pencere == (155, 170, 345, 370), pencere
    ox, oy = pencere[0], pencere[1]
    # Kirpinti koordinati -> kare koordinati: yakin balon (262,265), uzak (255,345)
    yakin_kare, uzak_kare = (247, 250, 277, 280), (240, 330, 270, 360)
    kirp = lambda k: (k[0] - ox, k[1] - oy, k[2] - ox, k[3] - oy)

    bmodel = _BalonModel([kirp(uzak_kare), kirp(yakin_kare)])
    dusman = [{"cls": "f16", "box": hedef_kutu, "tip": "Düşman"}]
    ek = ek_balonlari_tespit_et([bmodel], kare_b, dusman)
    assert len(ek) == 2 and yakin_kare in ek and uzak_kare in ek, ek

    # Nisan noktasi: EN YAKIN balonun MERKEZI. Iki sey birden korunur —
    # (a) listede ONCE gelen degil, asilma noktasina en yakin olan secilir;
    # (b) nisan balonun kendi merkezine gider, hedef kutusunun orta eksenine DEGIL
    #     (lazer balonun yanina giderse balon patlamaz, imha sayilmaz).
    assert nisan_noktasi(hedef_kutu, [uzak_kare, yakin_kare]) == (262.0, 265.0), \
        nisan_noktasi(hedef_kutu, [uzak_kare, yakin_kare])
    # Balon hic bulunamazsa geometrik kestirime duser (kutunun altina balon_ofset).
    assert nisan_noktasi(hedef_kutu, []) != (262.0, 265.0)

    dost = [{"cls": "f16", "box": hedef_kutu, "tip": "Dost"}]
    bmodel.cagri = 0
    assert ek_balonlari_tespit_et([bmodel], kare_b, dost) == [], "dostun balonu arandi"
    assert bmodel.cagri == 0, "dost hedef icin ek balon modeli bosuna kosturuldu"

    # Hayalet hedefin (tespit edilemeyen kare) altinda da aranmaz: kutu donmustur.
    hayalet_h = [{"cls": "f16", "box": hedef_kutu, "tip": "Düşman", "hayalet": True}]
    assert ek_balonlari_tespit_et([bmodel], kare_b, hayalet_h) == []

    print("algi testleri OK — sinif adi, ayar kirpma, tracker yaml, A3 taraf guveni, "
          "kesin tanima (histerezis/coklu hedef/onay bozulma), cakisan kutu temizligi, "
          "hayalet/dost kilidi korumasi + yuksek-cozunurluk yeniden bulma, "
          "kirmizi oneri (uzak tarama penceresi), kacirilan kare kaydi, "
          "dusmanin balonu (dost aranmaz, en yakin balon nisan noktasi)")
