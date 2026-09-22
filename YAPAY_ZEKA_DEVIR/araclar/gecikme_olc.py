import sys, time, threading, serial, cv2, numpy as np
sys.path.insert(0,'.')
import algi, tilt_takip_testi as tt
tt.kayitli_ayarlari_yukle(); algi.ayar_guncelle(kamera_fps=60)
cap = algi.open_camera()
ser = serial.Serial('COM3',115200,timeout=0.005,write_timeout=1); yk=threading.Lock()
def yaz(b):
    with yk: ser.write(b)
aci={'T':[], 'P':[]}; kareler=[]; calis=[True]
def kart():
    buf=b''
    while calis[0]:
        buf+=ser.read(4096); t=time.time()
        while b'\n' in buf:
            l,buf=buf.split(b'\n',1); l=l.decode(errors='ignore').strip()
            if l.startswith('STATE3,'): aci['T'].append((t,float(l.split(',')[8])))
            elif l.startswith('PAN1,'): aci['P'].append((t,float(l.split(',')[4])))
def nabiz():
    while calis[0]: yaz(b'H\n'); time.sleep(0.08)
def kamera():
    while calis[0]:
        ok,k=cap.read(); t=time.time()
        if ok and kaydet[0]: kareler.append((t, cv2.cvtColor(cv2.resize(k,(640,360)),cv2.COLOR_BGR2GRAY).astype(np.float32)))
kaydet=[False]
for f in (kart,nabiz,kamera): threading.Thread(target=f,daemon=True).start()
time.sleep(1.2); yaz(b'E\n'); time.sleep(0.3)
def dizi(eksen, komutlar, bas):
    yaz(bas); time.sleep(2.0)
    kareler.clear(); n0=len(aci[eksen]); kaydet[0]=True; time.sleep(0.5)
    for c in komutlar: yaz(c); time.sleep(1.2)
    kaydet[0]=False
    return list(kareler), aci[eksen][n0:]
sonuc={}
sonuc['T']=dizi('T',[b'G14\n',b'G10\n',b'G14\n',b'G10\n'], b'G10\n')
sonuc['P']=dizi('P',[b'P4\n',b'P0\n',b'P4\n',b'P0\n'], b'P0\n')
yaz(b'G0\nP0\n'); time.sleep(2.5); calis[0]=False; yaz(b'X\nD\n'); time.sleep(0.1)
def bosluk(a, b):
    n=[]; x=a[0]
    for v in a:
        if v-x>b/2: x=v-b/2
        if x-v>b/2: x=v+b/2
        n.append(x)
    return np.array(n)
for eksen,(kr,an) in sonuc.items():
    ref=kr[0][1]; w=cv2.createHanningWindow(ref.shape[::-1],cv2.CV_32F)
    # ardisik kayma toplami (buyuk kaymada tek referans guvensiz)
    toplam=0.0; seri=[]; onceki=ref
    for t,f in kr:
        (dx,dy),g=cv2.phaseCorrelate(onceki,f,w); toplam+= (dy if eksen=='T' else dx); seri.append((t,toplam)); onceki=f
    tk=np.array([s[0] for s in seri]); ik=np.array([s[1] for s in seri])*2.0   # 640->1280 px
    ta=np.array([a[0] for a in an]); aa=np.array([a[1] for a in an])
    en=None
    for L in np.arange(0,0.201,0.005):
        for b in np.arange(0,3.01,0.1):
            nam=bosluk(np.interp(tk-L,ta,aa), b)
            A=np.vstack([nam,np.ones_like(nam)]).T; coef,res,*_=np.linalg.lstsq(A,ik,rcond=None)
            r=np.sqrt(np.mean((A@coef-ik)**2))
            if en is None or r<en[0]: en=(r,L,b,coef[0])
    r,L,b,ppd=en
    print(f"{'TILT' if eksen=='T' else 'PAN '}: gecikme {L*1000:3.0f} ms | bosluk {b:.1f} der | ppd {abs(ppd)*1:.1f} px/der (isaret {'+' if ppd>0 else '-'}) | artik {r:.1f} px | {len(kr)} kare")
