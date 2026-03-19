@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo HATA: .venv bulunamadi. Once Launch_Bookmark_Manager.bat ile kurulumu tamamlayin.
    pause
    exit /b 1
)

set /p PROFILE=Profil adi (ornek: default veya deneme): 
if "%PROFILE%"=="" set PROFILE=default

set /p THREADS=Kac DM konusmasi taransin? (varsayilan 10): 
if "%THREADS%"=="" set THREADS=10

call ".venv\Scripts\activate.bat"
python instagram_bot.py --scan-dm %THREADS% --profile "%PROFILE%"

echo.
echo DM islemi tamamlandi veya durduruldu.
pause
