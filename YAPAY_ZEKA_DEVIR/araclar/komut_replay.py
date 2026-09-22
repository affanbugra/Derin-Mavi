import csv,glob,sys
sys.path.insert(0,'.')
import numpy as np, hedef_kestirici as HK
F=lambda v: float(v) if v else None
PPD=18.7; GEC=0.03
def replay(f, degistir=None):
    r=[x for x in csv.DictReader(open(f,encoding='utf-8')) if x['pan']]
    t=np.array([float(x['t']) for x in r]); pan=np.array([F(x['pan']) for x in r])
    eks=HK.EksenTakip(isaret=1.0)
    if degistir: degistir(eks)
    kayit=[]
    for x in r:
        tt=float(x['t']); p=F(x['pan']); hx=F(x['hata_x'])
        if hx is not None:
            eks.olcum(tt-GEC, float(np.interp(tt-GEC,t,pan)), hx, PPD)
        out=eks.yorunge_komut(tt, p, -60, 60, hata_px=hx, olu_px=(0.12*150 if hx is not None else None))
        if out is not None:
            kayit.append((tt, out[0], out[1], eks._duragan, eks.kestirici.tahmin(tt), p))
    k=np.array([(a,b,c,d,e,g) for a,b,c,d,e,g in kayit if e is not None])
    zt=[(float(x['t']),float(np.interp(float(x['t'])-GEC,t,pan))+F(x['hata_x'])/PPD) for x in r if x['hata_x']]
    zt=np.array(zt); zg=np.convolve(zt[:,1],np.ones(5)/5,mode='same'); v=np.gradient(zg,zt[:,0])
    vk=np.interp(k[:,0],zt[:,0],v); m=(np.abs(vk)>=10)&(k[:,0]>3)
    duragan_orani=100*np.mean(k[m,3])
    komut_gecik=np.mean(np.sign(vk[m])*(k[m,4]-k[m,1]))*PPD
    return duragan_orani, komut_gecik, m.sum()
for b in ("BOLUM2_yavas","BOLUM3_normal"):
    f=sorted(glob.glob(f'loglar/*_{b}.csv'))[-1]
    d,g,n=replay(f)
    print(f"{b[7:]:7s} SU ANKI mantik  : hedef >=10 der/s iken 'durdu' kipinde %{d:3.0f} | komut tahminin {g:5.1f}px gerisinde ({n} komut)")
    def kapat(e): e._duragan=False; e._yavas_t=None; e.__class__=type('X',(HK.EksenTakip,),{})
    d,g,n=replay(f, lambda e: setattr(e,'_durgun_kapali',True))
