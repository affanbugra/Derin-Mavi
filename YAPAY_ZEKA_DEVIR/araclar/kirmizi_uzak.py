import sys, glob, random, cv2, numpy as np
sys.path.insert(0,'.')
import algi
from ultralytics import YOLO
m=YOLO('../models/best.pt', task='detect')
kareler=[cv2.imdecode(np.fromfile(f,np.uint8),1) for f in sorted(glob.glob('veri_toplama/*/images/*.jpg'))]
kareler=[k for k in kareler if k is not None and k.shape[1]==1280]
kaynak=[]
for k in kareler:
    r=m.predict(k,conf=0.6,imgsz=1280,verbose=False)[0]
    for b in r.boxes:
        if r.names[int(b.cls)].lower().startswith('drone'):
            x1,y1,x2,y2=map(int,b.xyxy[0].tolist())
            if x2-x1>=60:
                p=int(0.06*(x2-x1)); kaynak.append((k[max(0,y1-p):y2+p,max(0,x1-p):x2+p].copy()))
print("kaynak:",len(kaynak))
print("buyuk (orijinal) kutularda kirmizi kaniti: %{:.0f}".format(100*np.mean([algi.anlik_kirmizi_kaniti(c,(0,0,c.shape[1],c.shape[0])) for c in kaynak])))
rng=random.Random(4)
for gen in (50,35,25,18,12):
    ok=0; n=60
    for _ in range(n):
        bg=rng.choice(kareler).copy(); c=rng.choice(kaynak)
        h=max(4,int(round(c.shape[0]*gen/c.shape[1]))); kuc=cv2.resize(c,(gen,h),interpolation=cv2.INTER_AREA)
        x=rng.randrange(20,1200); y=rng.randrange(20,650); bg[y:y+h,x:x+gen]=kuc
        ok+=algi.anlik_kirmizi_kaniti(bg,(x,y,x+gen,y+h))
    print(f"{gen:3d} px drone: kirmizi kaniti %{100*ok/n:.0f}")
