# Cómo generar el instalable para hospitales

## Requisitos (solo en la máquina de desarrollo)
```
pip install pyinstaller
```

## Generar el .exe
Desde C:\Ckt\STEH\chip-assigner\ ejecutar:

```bash
pyinstaller --onefile --noconsole --name ChipAssigner --add-data "config.json;." main.py
```

El ejecutable queda en: `dist\ChipAssigner.exe`

Flags usados:
- `--onefile`    → todo en un solo .exe, sin carpetas
- `--noconsole`  → no abre ventana de consola (corre en background)
- `--name`       → nombre del ejecutable
- `--add-data`   → incluye config.json dentro del .exe

## Armar la carpeta para el hospital

```
chip-assigner-entrega\
    ├── installer\
    │   ├── instalar.bat        ← el técnico ejecuta esto como admin
    │   └── driver\
    │       └── yr9011.inf      ← driver del YR9011
    └── chip-assigner-dist\
        └── ChipAssigner.exe    ← el servicio empaquetado
```

Copiar así:
```bash
mkdir chip-assigner-entrega\chip-assigner-dist
copy dist\ChipAssigner.exe chip-assigner-entrega\chip-assigner-dist\
xcopy /E installer chip-assigner-entrega\installer\
```

Comprimir en .zip y enviar al hospital.

## Lo que hace el técnico en el hospital

1. Descomprimir el .zip
2. Clic derecho en `installer\instalar.bat` → **Ejecutar como administrador**
3. Conectar el YR9011 USB (si no lo estaba)
4. Listo — el servicio arranca solo con Windows

## Notas

- El driver solo se instala una vez por computadora
- Si se cambia el puerto USB, Windows puede asignar un COM distinto
  pero el servicio lo auto-detecta por VID/PID (no depende del número de COM)
- Para desinstalar: eliminar C:\STEH\chip-assigner\ y el acceso directo
  en %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\
