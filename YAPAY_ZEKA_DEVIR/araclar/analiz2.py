import csv,glob,sys,statistics as st
sys.path.insert(0,'.')
import tilt_surucu as TS
f=sorted(glob.glob(f'loglar/*_{sys.argv[1]}.csv'))[-1]; r=[x for x in csv.DictReader(open(f,encoding='utf-8')) if float(x['t'])>3]
F=lambda v: float(v) if v else None
kam=[TS.kamera_acisi(F(x['kol'])) for x in r]; pan=[F(x['pan']) for x in r]
def yd(v,esik):
    n=0; ref=v[0]; yon=0
    for a in v[1:]:
        if abs(a-ref)>=esik:
            d=1 if a>ref else -1
            if yon and d!=yon: n+=1
            yon=d; ref=a
    return n
hy=[abs(F(x['hata_px'])) for x in r if x['hata_px']]; hx=[abs(F(x['hata_x'])) for x in r if x['hata_x']]
print(f"{sys.argv[1]:8s}: dikey med {st.median(hy):4.1f} px | yatay med {st.median(hx):4.1f} px | "
      f"kamera tilt araligi {max(kam)-min(kam):.2f} der, pan araligi {max(pan)-min(pan):.2f} der | "
      f"yon degisimi (>0.1 der kamera): tilt {yd(kam,0.1)} pan {yd(pan,0.1)}")
