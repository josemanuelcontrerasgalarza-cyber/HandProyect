@echo off
rem ==========================================================================
rem  Crea ManoBionica.exe en este PC con Windows.
rem  Requisito: Python 3.10 o superior instalado (python.org, marcando
rem  "Add Python to PATH"). Doble clic en este archivo y espera.
rem  Resultado: dist\ManoBionica\ManoBionica.exe
rem ==========================================================================
setlocal
cd /d "%~dp0"
echo.
echo === Mano Bionica: crear ManoBionica.exe ===
echo.

rem --- Buscar Python (lanzador "py" o "python") ---
set "PY="
py -3 --version >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    python --version >nul 2>nul
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo [ERROR] No se encuentra Python.
    echo Instalalo desde https://www.python.org/downloads/ marcando "Add Python to PATH".
    goto fin_error
)
%PY% --version

rem --- Entorno virtual solo para compilar (no toca tu Python) ---
if not exist ".venv-exe\Scripts\python.exe" (
    echo [1/5] Creando entorno virtual .venv-exe ...
    %PY% -m venv .venv-exe || goto error
)
set "VPY=.venv-exe\Scripts\python.exe"

echo [2/5] Instalando dependencias (la primera vez tarda unos minutos) ...
"%VPY%" -m pip install --upgrade pip >nul || goto error
"%VPY%" -m pip install -r requirements.txt pyinstaller || goto error

echo [3/5] Descargando el modelo de MediaPipe si hace falta ...
"%VPY%" -c "from mano.vision import asegurar_modelo; asegurar_modelo()" || goto error

echo [4/5] Creando el ejecutable con PyInstaller ...
"%VPY%" -m PyInstaller --noconfirm mano_app.spec || goto error
copy /y LEEME_WINDOWS.txt dist\ManoBionica\LEEME.txt >nul

echo [5/5] Comprobando que el .exe arranca ...
start "" /wait "dist\ManoBionica\ManoBionica.exe" --autoprueba
if errorlevel 1 (
    echo [ERROR] El .exe se ha creado pero la autoprueba ha fallado:
    type "dist\ManoBionica\autoprueba.log"
    goto fin_error
)
del "dist\ManoBionica\autoprueba.log" >nul 2>nul

echo.
echo === LISTO ===
echo Ejecutable: %CD%\dist\ManoBionica\ManoBionica.exe
echo Copia la carpeta dist\ManoBionica completa a donde quieras.
explorer "dist\ManoBionica"
pause
exit /b 0

:error
echo.
echo [ERROR] Algo ha fallado. Revisa los mensajes de arriba.
:fin_error
pause
exit /b 1
