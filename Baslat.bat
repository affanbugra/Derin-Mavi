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
echo   Port adı yazın (örn. COM7)  -^> gerçek karta bağlanır, MOTORLAR DÖNER
echo   Boş bırakıp Enter           -^> mock simülasyon (motor dönmez)
echo.
set "DERINMAVI_ESP="
set /p DERINMAVI_ESP="Port: "
if "%DERINMAVI_ESP%"=="" set "DERINMAVI_ESP=mock"
echo.
echo Kontrol kaynağı: %DERINMAVI_ESP%
echo.

echo Arayüz başlatılıyor...
cd /d "%~dp0app"
"%PY%" arayuz_qt.py
if errorlevel 1 (
    echo.
    echo [HATA] Arayüz çalıştırılırken bir sorun oluştu.
    pause
)
