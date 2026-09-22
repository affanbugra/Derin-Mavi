import sys, glob, random, time, cv2, numpy as np
sys.path.insert(0,'.')
import algi
from ultralytics import YOLO
algi.ZOR_ORNEK_DIZIN = __import__('tempfile').mkdtemp()
kareler=[cv2.imdecode(np.fromfile(f,np.uint8),1) for f in sorted(glob.glob('veri_toplama/*/images/*.jpg'))]
kareler=[k for k in kareler if k is not None and k.shape[1]==1280]
ana=YOLO('../models/best.pt', task='detect')
# kaynak drone kirpiklari
kaynak=[]
for k in kareler[:60]:
    r=ana.predict(k,conf=0.6,imgsz=1280,verbose=False)[0]
    for b in r.boxes:
        if r.names[int(b.cls)].lower().startswith('drone'):
            x1,y1,x2,y2=map(int,b.xyxy[0].tolist())
            if x2-x1>=60: p=int(0.06*(x2-x1)); kaynak.append(k[max(0,y1-p):y2+p,max(0,x1-p):x2+p].copy())
# arka plan: drone'suz bolge lazim; kareyi drone kutusunu bulaniklastirarak temizle
def temizle(k):
    k=k.copy(); r=ana.predict(k,conf=0.2,imgsz=1280,verbose=False)[0]
    for b in r.boxes:
        x1,y1,x2,y2=map(int,b.xyxy[0].tolist()); p=15
        y1,y2,x1,x2=max(0,y1-p),min(720,y2+p),max(0,x1-p),min(1280,x2+p)
        k[y1:y2,x1:x2]=cv2.GaussianBlur(k,(0,0),25)[y1:y2,x1:x2]
    return k
def senaryo(gen, seed):
    rng=random.Random(seed); bg=temizle(rng.choice(kareler)); crop=rng.choice(kaynak)
    h=max(4,int(round(crop.shape[0]*gen/crop.shape[1]))); kuc=cv2.resize(crop,(gen,h),interpolation=cv2.INTER_AREA)
    x0,y0=rng.randrange(150,1000),rng.randrange(100,550); vx=rng.choice((-1,1))*1.0
    seq=[]
    for i in range(150):
        x=int(x0+vx*i); f=bg.copy(); f[y0:y0+h,x:x+gen]=kuc; seq.append((f,(x,y0,x+gen,y0+h)))
    return seq
def kos(ayar, seq):
    algi.ayar_guncelle(**ayar); algi.takip_sifirla(); algi.roi_modeli_ayarla(None); algi._roi_model_denendi=False
    m=YOLO('../models/best.pt', task='detect')
    kilit=None; dogru=0; toplam=0; t=0
    for i,(f,h) in enumerate(seq):
        t0=time.time(); dets,_b,ai=algi.analiz_et(m,f,asama=1); t+=time.time()-t0
        ok=False
        if 0<=ai<len(dets) and not dets[ai].get("hayalet"):
            x1,y1,x2,y2=dets[ai]["box"]; cx,cy=(h[0]+h[2])/2,(h[1]+h[3])/2
            ok = x1-5<=cx<=x2+5 and y1-5<=cy<=y2+5
        if ok and kilit is None: kilit=i
        if kilit is not None: toplam+=1; dogru+=ok
    return kilit, (100*dogru/toplam if toplam else 0), 1000*t/len(seq)
yapilandirma={
 'ESKI (640, uzak yok)': dict(cozunurluk=640, arama_cozunurluk=640, uzak_tarama=0),
 'yalniz 1280 arama':    dict(cozunurluk=640, arama_cozunurluk=1280, uzak_tarama=0),
 'YENI tam sistem':      dict(cozunurluk=640, arama_cozunurluk=1280, uzak_tarama=1),
}
import sys as _s
eski_roi=algi.ROI_EN_KUCUK
for gen in (40,28,20,14):
    seqs=[senaryo(gen,s) for s in (1,2,3)]
    for ad,ay in yapilandirma.items():
        algi.ROI_EN_KUCUK = 320 if ad.startswith('ESKI') else eski_roi
        r=[kos(ay,sq) for sq in seqs]
        kil=[x[0] for x in r]
        print(f"{gen:3d}px {ad:22s}: kilit karesi {kil} | kilitten sonra dogru takip %{np.mean([x[1] for x in r]):3.0f} | {np.mean([x[2] for x in r]):5.1f} ms/kare")
