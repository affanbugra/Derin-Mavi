import sys, time, math, threading
sys.path.insert(0,'.')
import numpy as np, cv2, algi, tilt_surucu as T
from ultralytics import YOLO
model=YOLO('../models/best.pt',task='detect'); algi.ayar_guncelle(kamera_fps=60, zor_ornek=0)
s=T.TiltSurucu("COM3"); kilit=threading.RLock(); dur=threading.Event()
def nabiz():
    while not dur.is_set():
        with kilit: s.yokla()
        dur.wait(0.01)
threading.Thread(target=nabiz,daemon=True).start()
cap=algi.open_camera(); algi.analiz_et(model, cap.read()[1])
time.sleep(1.0)
def pan_sur(stop):
    t0=time.time()
    while not stop.is_set():
        t=time.time()-t0; p=5*math.sin(2*math.pi*t/2); v=5*math.pi*math.cos(2*math.pi*t/2)
        with kilit: s.pan_yorunge(p,v)
        time.sleep(0.04)
def olc(okuyucu_kullan, sure=6.0):
    stop=threading.Event(); th=threading.Thread(target=pan_sur,args=(stop,),daemon=True); th.start()
    oku=algi.KameraOkuyucu(cap) if okuyucu_kullan else None
    time.sleep(0.8)
    kay=[]; ref=None; w=None; t0=time.time(); son=None
    while time.time()-t0<sure:
        if oku:
            k,sira=oku.oku(son)
            if k is None: time.sleep(0.002); continue
            son=sira; tk=oku.son_kare_zamani()
        else:
            ok,k=cap.read(); tk=time.time()
        algi.analiz_et(model,k)                       # takipteki gibi yuk
        g=cv2.cvtColor(cv2.resize(k[:420],(640,210)),cv2.COLOR_BGR2GRAY).astype(np.float32)
        if ref is None: ref=g; w=cv2.createHanningWindow(g.shape[::-1],cv2.CV_32F)
        (dx,_),_q=cv2.phaseCorrelate(ref,g,w); kay.append((tk,-2*dx/18.7))
    stop.set(); th.join()
    if oku: oku._calis=False; oku._th.join(timeout=1)
    with kilit: gec=list(s._pan_gecmisi)
    ta=np.array([a for a,_ in gec]); pa=np.array([b for _,b in gec]); kk=np.array(kay)
    en=min(((np.mean((kk[:,1]-kk[:,1].mean()-(np.interp(kk[:,0]-L,ta,pa)-np.interp(kk[:,0]-L,ta,pa).mean()))**2),L) for L in np.arange(0,0.4,0.005)))
    fps=len(kay)/sure
    print(f"{'ayri okuyucu (arayuz gibi)' if okuyucu_kullan else 'dogrudan cap.read (test araci)':32s}: islenen {fps:4.1f} kare/s | GERCEK kamera gecikmesi {en[1]*1000:4.0f} ms")
olc(False); time.sleep(1); olc(True)
with kilit: s.pan_git(0.0)
time.sleep(1.2); dur.set()
with kilit: s.dur(); s.kapat(kalici=True)
cap.release()
