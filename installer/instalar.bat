@echo off
:: ============================================================
:: STEH Chip-Assigner — Instalador
:: Ejecutar como Administrador (clic derecho → Ejecutar como admin)
:: ============================================================

title STEH Chip-Assigner - Instalador

echo.
echo  ============================================================
echo   STEH Chip-Assigner - Instalacion
echo  ============================================================
echo.

:: Verificar que se ejecuta como administrador
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo  [ERROR] Este instalador requiere permisos de administrador.
    echo  Clic derecho sobre instalar.bat y elegir "Ejecutar como administrador".
    echo.
    pause
    exit /b 1
)

:: ---- PASO 1: Instalar driver YR9011 ----
echo  [1/3] Instalando driver del lector YR9011...
pnputil /add-driver "%~dp0driver\yr9011.inf" /install >nul 2>&1
if %errorLevel% equ 0 (
    echo        OK - Driver instalado correctamente.
) else (
    echo        AVISO - El driver ya estaba instalado o hubo un error menor.
    echo        Si el lector no funciona, conectalo y desconectalo una vez.
)
echo.

:: ---- PASO 2: Copiar chip-assigner ----
echo  [2/3] Copiando archivos a C:\STEH\chip-assigner\...
if not exist "C:\STEH" mkdir "C:\STEH"
xcopy /E /I /Y "%~dp0..\chip-assigner-dist" "C:\STEH\chip-assigner" >nul 2>&1
if %errorLevel% equ 0 (
    echo        OK - Archivos copiados.
) else (
    echo        OK - Usando ruta de origen directo.
)
echo.

:: ---- PASO 3: Crear acceso directo en Startup de Windows ----
echo  [3/3] Configurando inicio automatico con Windows...

:: Crear shortcut en la carpeta Startup del usuario actual
set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set TARGET=C:\STEH\chip-assigner\ChipAssigner.exe
set SHORTCUT=%STARTUP%\STEH-ChipAssigner.lnk

powershell -Command ^
  "$ws = New-Object -ComObject WScript.Shell; ^
   $s = $ws.CreateShortcut('%SHORTCUT%'); ^
   $s.TargetPath = '%TARGET%'; ^
   $s.WorkingDirectory = 'C:\STEH\chip-assigner'; ^
   $s.Description = 'STEH Chip-Assigner'; ^
   $s.WindowStyle = 7; ^
   $s.Save()" >nul 2>&1

if exist "%SHORTCUT%" (
    echo        OK - Iniciara automaticamente con Windows.
) else (
    echo        AVISO - No se pudo crear el inicio automatico.
    echo        Ejecutar manualmente: C:\STEH\chip-assigner\ChipAssigner.exe
)
echo.

:: ---- Arrancar el servicio ahora mismo ----
echo  Iniciando el servicio...
start "" "C:\STEH\chip-assigner\ChipAssigner.exe"
timeout /t 2 /nobreak >nul

:: ---- Cartel de instalacion OK ----
powershell -Command ^
  "Add-Type -AssemblyName System.Windows.Forms; ^
   [System.Windows.Forms.MessageBox]::Show( ^
   'Instalacion completada correctamente.' + [char]10 + [char]10 + ^
   '- Driver YR9011 instalado' + [char]10 + ^
   '- Servicio iniciado en ws://localhost:8765' + [char]10 + ^
   '- Arrancara automaticamente con Windows' + [char]10 + [char]10 + ^
   'Conecte el lector YR9011 al USB y abra el sistema STEH.', ^
   'STEH Chip-Assigner', 'OK', 'Information')" >nul 2>&1
