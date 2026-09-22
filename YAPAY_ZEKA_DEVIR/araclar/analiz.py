import csv,glob,sys,statistics as st
f=sorted(glob.glob(f'loglar/*_{sys.argv[1]}.csv'))[-1]; r=[x for x in csv.DictReader(open(f,encoding='utf-8')) if float(x['t'])>2]
F=lambda v: float(v) if v else None
kol=[F(x['kol']) for x in r]; tavan=sum(1 for k in kol if k>=47.5)
def yd(v,esik):
    n=0; ref=v[0]; yon=0
    for a in v[1:]:
        if abs(a-ref)>=esik:
            d=1 if a>ref else -1
            if yon and d!=yon: n+=1
            yon=d; ref=a
    return n
ic=[x for x in r if F(x['kol'])<47.5]
hy=[abs(F(x['hata_px'])) for x in ic if x['hata_px']]; hx=[abs(F(x['hata_x'])) for x in r if x['hata_x']]
print(f"{f[-40:]}\n  tavanda gecen kare %{100*tavan/len(r):.0f} | tavan DISINDA dikey hata medyan {st.median(hy):.1f} px | yatay medyan {st.median(hx):.1f} px")
print(f"  yon degisimi (esik 0.3 der): tilt {yd(kol,0.3)} pan {yd([F(x['pan']) for x in r],0.3)} | (esik 1 der): tilt {yd(kol,1.0)} pan {yd([F(x['pan']) for x in r],1.0)}")
