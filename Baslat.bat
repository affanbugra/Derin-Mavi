@echo off
chcp 65001 >nul
title DERIN MAVI - Görev Kontrol İstasyonu

echo ===================================================
echo   DERIN MAVI - GOREV KONTROL ISTASYONU
echo ===================================================
echo.
echo Bağımlılıklar kontrol ediliyor...

cd /d "%~dp0"
python -c "import PySide6, ultralytics, cv2, numpy" 2>nul
if errorlevel 1 (
    echo [BİLGİ] Gerekli paketler eksik veya yetersiz. Otomatik kurulum başlatılıyor...
    echo.
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [HATA] Paket kurulumunda sorun oluştu!
        pause
        exit /b 1
    )
    echo [BAŞARILI] Bağımlılıklar tamamlandı.
    echo.
)

echo Arayüz başlatılıyor...
cd /d "%~dp0app"
python arayuz_qt.py
if errorlevel 1 (
    echo.
    echo [HATA] Arayüz çalıştırılırken bir sorun oluştu.
    pause
)
