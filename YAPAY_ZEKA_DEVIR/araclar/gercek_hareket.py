import sys, os, csv, glob, math, random, statistics as st
sys.argv=['x']
exec(open(os.path.join(os.environ['TEMP'],'yor_benzet.py')).read().split("sen={")[0])
import numpy as np, hedef_kestirici as HK
F=lambda v: float(v) if v else None
# gercek el hareketi: loglardan hedefin dunya acisi (pan ekseni), puruzsuzlestirilmis
izler=[]
for f in sorted(glob.glob('loglar/*BOLUM2*.csv'))[-2:]+sorted(glob.glob('loglar/*BOLUM3*.csv'))[-2:]:
    r=[x for x in csv.DictReader(open(f,encoding='utf-8')) if x['pan']]
    t=np.array([float(x['t']) for x in r]); pan=np.array([F(x['pan']) for x in r])
    z=np.array([(float(x['t']),np.interp(float(x['t'])-0.04,t,pan)+F(x['hata_x'])/18.7) for x in r if x['hata_x'] and float(x['t'])>3])
    zs=np.convolve(z[:,1],np.ones(5)/5,'same')
    izler.append((z[:,0]-z[0,0], zs))
print("gercek hareket izi:",len(izler),"| ornek hiz tepe (der/s):",[round(float(np.percentile(np.abs(np.gradient(s,tt)),95)),1) for tt,s in izler])
def kos_iz(tt, zs, kw, gec=0.04, gec_model=0.04, seed=1, nis=None):
    f=lambda t: float(np.interp(t, tt, zs))
    rng=random.Random(seed); dt=0.001; m=YorMotor(b=0.4); eks=HK.EksenTakip(isaret=1.0,bosluk=0.8,**kw)
    if nis: eks.kestirici.nis_yukselis,eks.kestirici.nis_inis,eks.kestirici.nis_alt,eks.kestirici.nis_ust=nis
    m.x=m.namlu=zs[0]; g=[]; hat=[]; hz=[]; sk=0; sure=float(tt[-1])-0.2
    for i in range(int(sure/dt)):
        t=i*dt; m.adim(dt); g.append((t,m.x,m.namlu))
        if t-sk>=1/19-1e-9:                       # sahadaki ~19 Hz komut/kare
            sk=t; j=max(0,len(g)-1-int(gec/dt)); tk,xk,nk=g[j]
            hata=(f(tk)-nk)*18.7+rng.gauss(0,1.5)
            # kontrolcu karenin yasini gec_model saniye saniyor
            tm=t-gec_model; xm=float(np.interp(tm,[a for a,_,_ in g[-200:]],[b for _,b,_ in g[-200:]]))
            eks.olcum(tm,xm,hata,18.7); rr=eks.yorunge_komut(t,m.x,-60,60,hata_px=hata,olu_px=18)
            if rr: m.komut(*rr)
            if t>1: hat.append(abs(f(t)-m.namlu)*18.7)
        if t>1 and i%10==0: hz.append(m.v)
    iv=st.mean(abs(b-a)/0.01 for a,b in zip(hz,hz[1:]))
    hat.sort(); return hat[len(hat)//2], hat[int(.95*len(hat))], iv
def degerlendir(ad, kw, **k):
    r=[kos_iz(tt,zs,kw,**k) for tt,zs in izler]
    print(f"{ad:44s} medyan {st.mean(x[0] for x in r):5.1f}px | %95 {st.mean(x[1] for x in r):6.1f}px | sarsinti {st.mean(x[2] for x in r):5.0f}")
degerlendir("SU AN (adaptive 60..800, gecikme 30ms sanilir)", {}, gec_model=0.03)
degerlendir("gecikme dogru (40ms)", {}, gec_model=0.04)
degerlendir("sabit q=300", dict(yor_q=300,yor_q_min=None), gec_model=0.04)
degerlendir("sabit q=1500", dict(yor_q=1500,yor_q_min=None), gec_model=0.04)
degerlendir("adaptive 60..3000", dict(yor_q=3000,yor_q_min=60), gec_model=0.04)
degerlendir("adaptive 60..3000 hizli algilama", dict(yor_q=3000,yor_q_min=60), gec_model=0.04, nis=(0.8,0.1,1.2,3.0))
degerlendir("adaptive 150..5000 hizli algilama", dict(yor_q=5000,yor_q_min=150), gec_model=0.04, nis=(0.8,0.1,1.2,3.0))

print("--- kart ici konum kazanci K ---")
for K in (8, 15, 25, 40):
    YorMotor.K=K
    degerlendir(f"K={K:2d}, adaptive 60..800 (su an)", {}, gec_model=0.04)
    degerlendir(f"K={K:2d}, adaptive 150..5000 hizli algilama", dict(yor_q=5000,yor_q_min=150), gec_model=0.04, nis=(0.8,0.1,1.2,3.0))
YorMotor.K=8
