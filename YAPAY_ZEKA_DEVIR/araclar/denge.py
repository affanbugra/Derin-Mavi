import sys, os, math, statistics as st
exec(open(os.path.join(os.environ['TEMP'],'gercek_hareket.py')).read().split("def degerlendir")[0])
exec(open(os.path.join(os.environ['TEMP'],'adaptif.py')).read().split("titreme=")[0].split("exec(")[0] if False else "")
titrek=lambda t: 5.0+0.15*math.sin(2*math.pi*6*t)+0.1*math.sin(2*math.pi*9.3*t+1)
tt_t=np.arange(0,12,0.005); zs_t=np.array([titrek(x) for x in tt_t])
def dene(ad, kw, nis):
    r=[kos_iz(tt,zs,kw,gec_model=0.04,nis=nis) for tt,zs in izler]
    tr=[kos_iz(tt_t,zs_t,kw,gec_model=0.04,nis=nis,seed=s) for s in (1,2,3)]
    print(f"{ad:40s} EL: medyan {st.mean(x[0] for x in r):5.1f} %95 {st.mean(x[1] for x in r):5.1f} sarsinti {st.mean(x[2] for x in r):4.0f} | TITREYEN DURAN: hata {st.mean(x[0] for x in tr):4.1f} sarsinti {st.mean(x[2] for x in tr):4.0f}")
dene("eski: 60..800 yavas (1.5-4, 0.5)", dict(yor_q=800,yor_q_min=60), (0.5,0.1,1.5,4.0))
dene("hizli: 150..5000 (1.2-3, 0.8)", dict(yor_q=5000,yor_q_min=150), (0.8,0.1,1.2,3.0))
dene("60..5000 (1.5-4, 0.8)", dict(yor_q=5000,yor_q_min=60), (0.8,0.1,1.5,4.0))
dene("60..5000 (2-5, 0.8)", dict(yor_q=5000,yor_q_min=60), (0.8,0.1,2.0,5.0))
dene("40..3000 (2-5, 0.8)", dict(yor_q=3000,yor_q_min=40), (0.8,0.1,2.0,5.0))
dene("60..3000 (1.5-4, 0.6)", dict(yor_q=3000,yor_q_min=60), (0.6,0.1,1.5,4.0))
