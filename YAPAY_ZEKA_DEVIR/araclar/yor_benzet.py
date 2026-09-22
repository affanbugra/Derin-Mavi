import sys, math, random
sys.path.insert(0,'.')
import hedef_kestirici as HK

class KonumMotor:          # firmware konum kipi (retarget) yaklasigi
    def __init__(s,vmax=60,acc=500,b=0.6): s.x=s.v=s.hedef=s.namlu=0.0; s.vmax,s.acc,s.b=vmax,acc,b
    def adim(s,dt):
        e=s.hedef-s.x
        if abs(e)<1e-5 and abs(s.v)<1e-3: s.v=0; s.x=s.hedef
        else:
            vis=math.copysign(min(s.vmax,math.sqrt(2*s.acc*abs(e))),e)
            s.v+=max(-s.acc*dt,min(s.acc*dt,vis-s.v)); s.x+=s.v*dt
            if (e>0 and s.x>s.hedef) or (e<0 and s.x<s.hedef): s.x,s.v=s.hedef,0.0
        s._bos()
    def _bos(s):
        if s.x-s.namlu>s.b/2: s.namlu=s.x-s.b/2
        if s.namlu-s.x>s.b/2: s.namlu=s.x+s.b/2

class YorMotor(KonumMotor):  # yorunge_core.h'nin kopyasi (derece biriminde)
    K=8.0; ASIM=0.15
    def __init__(s,**k): super().__init__(**k); s.p0=s.v0=0; s.t0=-1; s.aktif=False; s.t=0
    def komut(s,p,v): s.p0,s.v0,s.t0,s.aktif=p,v,s.t,True
    def adim(s,dt):
        s.t+=dt
        if s.aktif:
            if s.t-s.t0>s.ASIM: vh=0.0
            else: vh=s.v0+s.K*((s.p0+s.v0*(s.t-s.t0))-s.x)
            vh=max(-s.vmax,min(s.vmax,vh))
            s.v+=max(-s.acc*dt,min(s.acc*dt,vh-s.v)); s.x+=s.v*dt
            if s.t-s.t0>s.ASIM and abs(s.v)<0.01: s.aktif=False; s.v=0
        s._bos()

def kos(kip, f, sure=14, ppd=18.7, b=0.6, gec=0.05, seed=5):
    rng=random.Random(seed); dt=0.001
    m=YorMotor(b=b) if kip=='yor' else KonumMotor(b=b)
    eks=HK.EksenTakip(isaret=1.0, bosluk=0.8)
    gecmis=[]; hat=[]; hizlar=[]; yon=0; on=0; dur_kalk=0; durdu=False; kare=1/60; sk=0
    for i in range(int(sure/dt)):
        t=i*dt; m.adim(dt); hd=f(t); gecmis.append((t,m.x,m.namlu))
        if t-sk>=kare-1e-9:
            sk=t
            j=max(0,len(gecmis)-1-int(gec/dt)); tk,xk,nk=gecmis[j]
            hata=(f(tk)-nk)*ppd+rng.gauss(0,1.5)
            eks.olcum(tk,xk,hata,ppd)
            if kip=='yor':
                r=eks.yorunge_komut(t,m.x,-400,400,hata_px=hata,olu_px=7.0)
                if r is not None: m.komut(*r)
            else:
                c=eks.komut(t,m.x,-400,400,hata_px=hata,olu_px=7.0)
                if c is not None: m.hedef=c
            if t>2: hat.append(abs(hd-m.namlu)*ppd)
        if t>2 and i%10==0:
            vh=(f(t+0.005)-f(t-0.005))/0.01
            if abs(vh)>1.5:                       # hedef hareketli
                if abs(m.v)<0.15*abs(vh) and not durdu: dur_kalk+=1; durdu=True
                elif abs(m.v)>0.5*abs(vh): durdu=False
            hizlar.append(m.v)
    ivme=[abs(b-a)/0.01 for a,b in zip(hizlar,hizlar[1:])]
    hat.sort(); return hat[len(hat)//2], hat[int(.95*len(hat))], dur_kalk, sum(ivme)/len(ivme)

sen={'duran hedef':lambda t:6.0,
     'yavas (2.6 der/sn tepe)':lambda t:5*math.sin(2*math.pi*t/12),
     'el hareketi':lambda t:4*math.sin(2*math.pi*t/5)+1.2*math.sin(2*math.pi*t/1.7),
     'orta sinus (10 der/sn)':lambda t:8*math.sin(2*math.pi*t/5),
     'hizli sinus (47 der/sn)':lambda t:15*math.sin(2*math.pi*t/2),
     'rayda sabit hiz 8 der/sn':lambda t:-20+8*t}
print(f"{'senaryo':26s}{'':3s}{'medyan':>8s}{'%95':>7s}{'dur-kalk':>9s}{'ort |ivme|':>11s}")
for ad,f in sen.items():
    for kip in ('konum','yor'):
        a=kos(kip,f); print(f"{ad:26s}{kip:>5s} {a[0]:7.1f}px{a[1]:6.1f}px{a[2]:8d}{a[3]:10.1f}")

if len(sys.argv)>1:
    import statistics as st
    f=sen['rayda sabit hiz 8 der/sn']
    for b in (0.0,0.6):
        rng=random.Random(5); dt=0.001; m=YorMotor(b=b); eks=HK.EksenTakip(isaret=1.0,bosluk=0.8)
        g=[]; e_n=[]; e_m=[]; e_k=[]; vk=[]; sk=0
        for i in range(int(12/dt)):
            t=i*dt; m.adim(dt); g.append((t,m.x,m.namlu))
            if t-sk>=1/60-1e-9:
                sk=t; j=max(0,len(g)-1-50); tk,xk,nk=g[j]; hata=(f(tk)-nk)*18.7+rng.gauss(0,1.5)
                eks.olcum(tk,xk,hata,18.7); r=eks.yorunge_komut(t,m.x,-400,400,hata_px=hata,olu_px=7.0)
                if r: m.komut(*r)
                if t>3: e_n.append(f(t)-m.namlu); e_m.append(f(t)-m.x); e_k.append(f(t)-eks.kestirici.tahmin(t)); vk.append(eks.kestirici.hiz)
        print(f"bosluk {b}: namlu gecikmesi {st.mean(e_n):+.3f} der | motor {st.mean(e_m):+.3f} | kestirim hatasi {st.mean(e_k):+.3f} | kestirilen hiz {st.mean(vk):.2f} (gercek 8) | ogrenilen bosluk {eks.bosluk_kest:.2f}")
