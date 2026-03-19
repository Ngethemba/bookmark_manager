@echo off
setlocal
cd /d "%~dp0"

echo ================================================
echo Bookmark Manager baslatiliyor...
echo ================================================

if not exist ".venv\Scripts\python.exe" (
    echo Sanal ortam bulunamadi. Olusturuluyor...
    py -3 -m venv .venv
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
    echo HATA: Sanal ortam aktif edilemedi.
    pause
    exit /b 1
)

echo Gerekli paketler kontrol ediliyor...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo HATA: requirements kurulumu basarisiz.
    pause
    exit /b 1
)

python -c "import playwright" >nul 2>&1
if errorlevel 1 (
    echo Playwright kuruluyor...
    python -m pip install playwright
)

echo Chromium kontrol ediliyor...
python -m playwright install chromium

echo Uygulama aciliyor: http://127.0.0.1:5000
start "" cmd /c "timeout /t 2 >nul && start http://127.0.0.1:5000"
python app.py

echo.
echo Uygulama kapandi.
pause
