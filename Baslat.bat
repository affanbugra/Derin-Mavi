@echo off
chcp 65001 >nul
title DERIN MAVI - Görev Kontrol İstasyonu

echo ===================================================
echo   DERIN MAVI - GOREV KONTROL ISTASYONU
echo ===================================================
echo.
echo Bağımlılıklar kontrol ediliyor...

cd /d "%~dp0"

REM Sanal ortam VARSA onu kullan, YOKSA sistem Python'u. Yol sabitlenmez:
REM ".venv" herkeste bulunmaz, sabit yazılırsa dosya sadece bir makinede çalışır.
if exist ".venv\Scripts\python.exe" (
    set "PY=%~dp0.venv\Scripts\python.exe"
    echo Sanal ortam bulundu: .venv
) else (
    set "PY=python"
    echo Sanal ortam yok, sistem Python'u kullanılıyor.
)

"%PY%" -c "import PySide6, ultralytics, cv2, numpy" 2>nul
if errorlevel 1 (
    echo [BİLGİ] Gerekli paketler eksik veya yetersiz. Otomatik kurulum başlatılıyor...
    echo.
    "%PY%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [HATA] Paket kurulumunda sorun oluştu!
        pause
        exit /b 1
    )
    echo [BAŞARILI] Bağımlılıklar tamamlandı.
    echo.
)

echo ===================================================
echo   ESP32 BAĞLANTISI
echo ===================================================
echo Bağlı seri portlar:
powershell -NoProfile -Command "Get-CimInstance Win32_PnPEntity | Where-Object { $_.Name -match '\(COM\d+\)' } | ForEach-Object { '   ' + $_.Name }" 2>nul
echo.
echo [1/2] Ayrı PAN kartı ^(yalnız eski iki-kart düzeninde^)
echo   Port adı yazın (örn. COM7)  -^> gerçek karta bağlanır, MOTORLAR DÖNER
echo   Yeni ESP32-S3 iki ekseni de sürüyorsa BOŞ bırakın ^(pan bu karta gider^)
echo.
set "DERINMAVI_ESP="
set /p DERINMAVI_ESP="Pan portu: "
if "%DERINMAVI_ESP%"=="" set "DERINMAVI_ESP=mock"
echo.
echo [2/2] ESP32-S3 PAN/TILT kartı - STATE3/PAN1 geri bildirim, G/Y/PY
echo   Boş bırakıp Enter  -^> OTOMATIK BUL ^(önerilen^)
echo   off                -^> kapalı ^(dikey eksen pan kartında kalır^)
echo   COM3 / COM4        -^> elle port
echo.
echo   NOT: Kartın İKİ USB yolu var, kabloyu hangi sokete taktığınıza göre
echo        COM numarası değişir ^(CH343 ve native USB^). Otomatik bulma
echo        STATE3 yayınına bakar, numara ezberlemeniz gerekmez.
echo.
set "DERINMAVI_TILT="
set /p DERINMAVI_TILT="Tilt portu [otomatik]: "
if "%DERINMAVI_TILT%"=="" set "DERINMAVI_TILT=auto"

REM Iki eksen ayni porta yazilirsa pyserial ikinci acisi hata verir ve eski
REM protokol yeni firmware'e "T12.50" yollar - o firmware bu komutu TANIMAZ,
REM ERR,DISARMED der ve motor HIC DONMEZ. Sessizce olmasin diye burada durdurulur.
REM (auto/mock/off gercek port adi degildir, karsilastirmaya girmezler.)
if /i not "%DERINMAVI_ESP%"=="mock" if /i not "%DERINMAVI_TILT%"=="auto" (
    if /i "%DERINMAVI_ESP%"=="%DERINMAVI_TILT%" (
        echo.
        echo [HATA] Pan ve tilt portu AYNI yazıldı: %DERINMAVI_ESP%
        echo        Yalnız tilt kartı bağlıysa pan portunu BOŞ bırakın ^(mock^).
        pause
        exit /b 1
    )
)
echo.
echo Pan kaynağı : %DERINMAVI_ESP%
echo Tilt kaynağı: %DERINMAVI_TILT%
echo.

echo Arayüz başlatılıyor...
cd /d "%~dp0app"
"%PY%" arayuz_qt.py
if errorlevel 1 (
    echo.
    echo [HATA] Arayüz çalıştırılırken bir sorun oluştu.
    pause
)
