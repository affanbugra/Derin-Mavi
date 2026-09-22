import sys, time, math, threading
sys.path.insert(0,'.')
import numpy as np, tilt_surucu as T
s=T.TiltSurucu("COM3"); kilit=threading.RLock(); dur=threading.Event()
def nabiz():
    while not dur.is_set():
        with kilit: s.yokla()
        dur.wait(0.01)
threading.Thread(target=nabiz,daemon=True).start()
time.sleep(1.5)
with kilit: print("hazir", s.hazir, "yorunge", s.yorunge_destekli, "pan", s.pan_aci)
def kos(A, Tp, hz, sure=6.0):
    with kilit: s.pan_git(0.0)
    time.sleep(1.5)
    komutlar=[]; olc=[]; t0=time.time(); son=0
    while time.time()-t0<sure:
        t=time.time()-t0
        if t-son>=1/hz:
            p=A*math.sin(2*math.pi*t/Tp); v=A*2*math.pi/Tp*math.cos(2*math.pi*t/Tp)
            with kilit: s.pan_yorunge(p,v)
            son=t
        with kilit:
            if s.pan_son_t: olc.append((s.pan_son_t-t0, s.pan_aci))
        time.sleep(0.004)
    o=np.array(sorted(set(olc)))
    m=o[:,0]>1.5
    ref=A*np.sin(2*math.pi*o[m,0]/Tp)
    hata=o[m,1]-ref
    # gecikme: referansi kaydirarak en iyi uyum
    en=min(((np.mean((o[m,1]-A*np.sin(2*math.pi*(o[m,0]-L)/Tp))**2),L) for L in np.arange(0,0.4,0.005)))
    print(f"A={A} T={Tp}s komut {hz}Hz: ort |hata| {np.mean(np.abs(hata)):.2f} der ({np.mean(np.abs(hata))*18.7:.0f}px) | en iyi uyan gecikme {en[1]*1000:.0f} ms")
kos(10,2.0,25)
kos(10,2.0,15)
kos(5,1.2,25)
with kilit: s.pan_git(0.0)
time.sleep(1.5); dur.set()
with kilit: s.dur(); s.kapat(kalici=True)
