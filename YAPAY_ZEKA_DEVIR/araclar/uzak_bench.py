import glob, os, random, time, cv2, numpy as np
from ultralytics import YOLO
m = YOLO('../models/best.pt', task='detect')
kareler = []
for f in sorted(glob.glob('veri_toplama/*/images/*.jpg')):
    k = cv2.imdecode(np.fromfile(f, np.uint8), 1)
    if k is not None and k.shape[1] == 1280: kareler.append(k)
print("kare:", len(kareler))
# 1) kaynak drone kirpiklari: modelin guvenle buldugu buyuk drone'lar
kaynak = []
for k in kareler:
    r = m.predict(k, conf=0.6, imgsz=1280, verbose=False)[0]
    for b in r.boxes:
        if r.names[int(b.cls)].lower().startswith('drone'):
            x1, y1, x2, y2 = map(int, b.xyxy[0].tolist())
            if x2 - x1 >= 60:
                p = int(0.06 * (x2 - x1))
                kaynak.append((k[max(0,y1-p):y2+p, max(0,x1-p):x2+p].copy(), (x1,y1,x2,y2)))
print("kaynak drone kirpigi:", len(kaynak))
rng = random.Random(3)
def ornek(gen):
    k_idx = rng.randrange(len(kareler)); bg = kareler[k_idx].copy()
    crop, _ = rng.choice(kaynak)
    s = gen / crop.shape[1]; h = max(4, int(round(crop.shape[0] * s)))
    kucuk = cv2.resize(crop, (gen, h), interpolation=cv2.INTER_AREA)
    x = rng.randrange(20, 1280 - gen - 20); y = rng.randrange(20, 720 - h - 20)
    bg[y:y+h, x:x+gen] = kucuk
    return bg, (x, y, x+gen, y+h)
def isabet(boxes, hedef):
    tx1, ty1, tx2, ty2 = hedef; cx, cy = (tx1+tx2)/2, (ty1+ty2)/2
    for (x1,y1,x2,y2) in boxes:
        if x1-4 <= cx <= x2+4 and y1-4 <= cy <= y2+4 and (x2-x1) < 3*(tx2-tx1)+20: return True
    return False
def kutular(r, ox=0, oy=0, esik=0.25):
    return [tuple(v + o for v, o in zip(b.xyxy[0].tolist(), (ox,oy,ox,oy))) for b in r.boxes if float(b.conf) >= esik]
def A(k, h): return kutular(m.predict(k, conf=0.25, imgsz=640, verbose=False)[0])
def B(k, h): return kutular(m.predict(k, conf=0.25, imgsz=1280, verbose=False)[0])
KARO = [(x, y) for y in (0, 80) for x in (0, 320, 640)]          # 640x640 karolar, ortusmeli
def C(k, h):
    parca = [k[y:y+640, x:x+640] for x, y in KARO]
    rs = m.predict(parca, conf=0.25, imgsz=640, verbose=False)
    out = []
    for (x, y), r in zip(KARO, rs): out += kutular(r, x, y)
    return out
def D(k, h):                                                        # kilit penceresi: gercek konum biliniyor
    cx, cy = (h[0]+h[2])//2, (h[1]+h[3])//2; S = 320
    ox = min(max(0, cx - S//2), 1280 - S); oy = min(max(0, cy - S//2), 720 - S)
    return kutular(m.predict(k[oy:oy+S, ox:ox+S], conf=0.25, imgsz=640, verbose=False)[0], ox, oy)
yontem = {'A tam kare 640 (su an)': A, 'B tam kare 1280': B, 'C 6 karo (tiling)': C, 'D kilit penceresi (ROI)': D}
for f in yontem.values(): f(kareler[0], (0,0,50,50))     # isinma
N = 60; boylar = [80, 50, 35, 25, 18, 12]
ornekler = {g: [ornek(g) for _ in range(N)] for g in boylar}
print(f"{'':26s}" + "".join(f"{g:>7d}px" for g in boylar) + "    sure/kare")
for ad, f in yontem.items():
    oran = []; t0 = time.time(); n = 0
    for g in boylar:
        say = sum(isabet(f(k, h), h) for k, h in ornekler[g]); n += N
        oran.append(100 * say / N)
    sure = (time.time() - t0) / n * 1000
    print(f"{ad:26s}" + "".join(f"{o:8.0f}%" for o in oran) + f"   {sure:6.1f} ms")
