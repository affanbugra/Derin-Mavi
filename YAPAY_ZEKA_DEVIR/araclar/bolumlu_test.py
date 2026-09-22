import subprocess, sys, time, winsound, os, glob, shutil
bolumler=[("1_sabit",20),("2_yavas",30),("3_normal",30)]
time.sleep(30)
for ad,sure in bolumler:
    p=subprocess.Popen([sys.executable,"tilt_canli_takip.py","--mod","yorunge","--sure",str(sure),"--bas","5",
                        "--pan_sinir","60","--kilit_bekle","120"],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding="utf-8",errors="ignore")
    cikti=[]
    for satir in p.stdout:
        cikti.append(satir)
        if "sure basladi" in satir: winsound.Beep(1500,250)
    p.wait(); winsound.Beep(500,900)
    son=sorted(glob.glob("loglar/*_yorunge.csv"))[-1]
    hedef=son.replace("_yorunge.csv",f"_BOLUM{ad}.csv"); shutil.copy(son,hedef)
    print(f"===== BOLUM {ad} =====")
    print("".join(l for l in cikti if any(k in l for k in ("hata|","DALGALANMA","gorulen","YATAY","kilitlendi"))))
    time.sleep(1.0)
