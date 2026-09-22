import csv,glob,sys,statistics as st
sys.path.insert(0,'.')
import numpy as np, hedef_kestirici as HK, algi
F=lambda v: float(v) if v else None
PPD=18.7; GEC=0.03
def analiz(f, kw, etiket):
    r=[x for x in csv.DictReader(open(f,encoding='utf-8')) if x['pan']]
    t=np.array([float(x['t']) for x in r]); pan=np.array([F(x['pan']) for x in r])
    olc=[(float(x['t']),F(x['hata_x'])) for x in r if x['hata_x']]
    # hedefin dunya acisi (kare cekildigi an): pan(t-gec) + hata/ppd
    z_t=np.array([a for a,_ in olc])-GEC; z=np.interp(z_t,t,pan)+np.array([h for _,h in olc])/PPD
    # "gercek" hedef: z'nin merkezi hareketli ortalamasi (gecikmesiz, 5 ornek)
    zg=np.convolve(z,np.ones(5)/5,mode='same')
    eks=HK.EksenTakip(isaret=1.0,**kw)
    tahmin=[]
    for tk,zk in zip(z_t,z):
        eks.kestirici.guncelle(tk, zk) if False else None
    # EksenTakip'in kestiricisini yorunge kipi ayariyla kos
    eks._kip_ayari(True)
    for tk,zk in zip(z_t,z):
        eks.kestirici.guncelle(tk,zk); tahmin.append(eks.kestirici.tahmin(tk+GEC))
    tahmin=np.array(tahmin); hedef_simdi=np.interp(z_t+GEC, z_t, zg)
    pan_simdi=np.interp(z_t+GEC,t,pan)
    v=np.gradient(zg,z_t)
    m=(np.abs(v)>=10)&(z_t>3)
    tah_gec=np.mean(np.sign(v[m])*(hedef_simdi[m]-tahmin[m]))*PPD
    mot_gec=np.mean(np.sign(v[m])*(tahmin[m]-pan_simdi[m]))*PPD
    top=np.mean(np.sign(v[m])*(hedef_simdi[m]-pan_simdi[m]))*PPD
    print(f"{etiket:28s} hedef>=10der/s ({m.sum()} olcum): TOPLAM geride {top:5.1f}px = tahmin gecikmesi {tah_gec:5.1f}px + motor/zincir {mot_gec:5.1f}px")
for b in ("BOLUM2_yavas","BOLUM3_normal"):
    f=sorted(glob.glob(f'loglar/*_{b}.csv'))[-1]
    for ad,kw in (("adaptive 60..800 (su an)",{}),("sabit q=300 (eski)",dict(yor_q=300,yor_q_min=None)),("sabit q=1500",dict(yor_q=1500,yor_q_min=None)),("adaptive 300..3000",dict(yor_q=3000,yor_q_min=300))):
        analiz(f,kw,f"{b[7:]}: {ad}")
