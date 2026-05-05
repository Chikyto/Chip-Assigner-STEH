## Instalacion de WebSocket

### Que se modifico

Se instalo la dependencia Python `websockets` en el entorno local del proyecto.
Tambien se corrigio el puente interno entre el driver serial y el servidor WebSocket:

- el autoconnect ahora enlaza correctamente los callbacks del lector al WebSocket
- la desconexion fisica del lector ahora actualiza el estado interno y notifica al frontend
- el arranque serial ahora prioriza auto-deteccion del lector por hardware
- `serial_port` en `config.json` queda como fallback opcional y no como dependencia fija

### Archivos afectados

- `requirements.txt`: ya declaraba `websockets>=12.0`, no requirio cambios.
- `docs/INSTALL_WEBSOCKET.md`: documentacion breve de la instalacion.

### Como probarlo

1. Verificar que la dependencia este instalada:
   `python -m pip show websockets`
2. Iniciar el servicio:
   `python main.py`
3. Confirmar en consola que expone:
   `ws://localhost:8765`
4. Confirmar en logs que detecta el lector automaticamente y muestra el `COM` real elegido.
5. Probar con un cliente WebSocket real, no con navegador o `fetch` HTTP.
6. Escanear un chip y verificar que el frontend reciba `chip_detected`.
7. Desconectar fisicamente el lector USB y verificar que el frontend reciba `disconnected` o un `status` con `connected: false`.
8. Opcional: definir `serial_port` en `config.json` con un `COM` invalido y verificar que el servicio igual recupere por auto-deteccion.

### Troubleshooting

- Si abris `http://localhost:8765` en el navegador, no va a funcionar.
- Ese puerto acepta solo WebSocket.
- La conexion correcta desde frontend es:
  `new WebSocket("ws://localhost:8765")`
- Si aparece `WinError 10048`, ya hay otra instancia escuchando en `127.0.0.1:8765`.
  En esta maquina se detecto `ChipAssigner.exe` usando ese puerto.
  Cerrar esa instancia o iniciar el script con otro puerto:
  `python main.py --ws-port 9000`
- Si `config.json` apunta a un puerto COM viejo, ahora se usa solo como fallback.
  El servicio primero intenta auto-detectar el lector por VID/PID USB.
- Si necesitas forzar manualmente un puerto puntual, usar:
  `python main.py --port COM3`

### Riesgos o supuestos

- La instalacion se hizo sobre el interprete resuelto por `python` en esta maquina.
- Si el proyecto usa otro entorno virtual, hay que repetir la instalacion en ese entorno.
- La prueba completa de deteccion real depende del hardware YR9011 conectado.
- La auto-deteccion depende de que el lector exponga un `VID/PID` compatible con la logica actual.

### Variables de entorno

No aplica.

### Endpoints

No aplica. Este cambio solo instala la libreria WebSocket del servicio local.
