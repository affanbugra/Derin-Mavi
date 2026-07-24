@echo off
chcp 65001 >nul
cd /d "%~dp0app"
echo DERIN MAVI - Gorev Kontrol Istasyonu baslatiliyor...
python arayuz_qt.py
if errorlevel 1 (
  echo.
  echo Hata olustu. Kurulum icin: pip install -r requirements.txt
  pause
)
