#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Driver puro para el lector INVELION YR9011 USB — sin dependencias de GUI.

Protocolo: YR9010 UHF RFID Serial Interface Protocol V2.38
Frame:     [Head=0xA0][Len][Address][Cmd][Data...][Checksum]
Baudrate:  115200 bps
Checksum:  (sum(bytes_desde_Len) + 0x42) & 0xFF

Uso:
    driver = YR9011Driver(
        port="COM3",
        on_tag_detected=lambda chip_id: print(chip_id),
        on_error=lambda msg: print(f"Error: {msg}"),
    )
    driver.connect()
    driver.start_scanning()
    # ... esperar detecciones ...
    driver.stop_scanning()
    driver.disconnect()
"""

import serial
import serial.tools.list_ports
import logging
import time
from datetime import datetime
from typing import Optional, List, Dict, Callable

logger = logging.getLogger(__name__)

BAUDRATE   = 115200
TIMEOUT    = 0.5
ADDRESS    = 0x01
DEBOUNCE_S = 2.0   # segundos entre re-detecciones del mismo chip
SCAN_INTERVAL = 0.2


def list_available_ports() -> List[Dict[str, str]]:
    """Retorna los puertos COM disponibles en el sistema."""
    return [
        {"port": p.device, "description": p.description, "hwid": p.hwid}
        for p in serial.tools.list_ports.comports()
    ]


def find_yr9011_port() -> Optional[str]:
    """
    Auto-detecta el puerto COM del YR9011 por su VID/PID USB (04E8:20E4).
    Retorna el nombre del puerto (ej. 'COM5') o None si no está conectado.
    """
    for p in serial.tools.list_ports.comports():
        if "04E8:20E4" in p.hwid or "VID_04E8" in p.hwid.upper():
            logger.info(f"YR9011 auto-detectado en {p.device} ({p.description})")
            return p.device
    return None


class YR9011Driver:
    """
    Driver del lector YR9011 sin dependencias de GUI.

    Los resultados se entregan por callbacks para que cualquier capa
    (WebSocket, cola asyncio, tests) pueda recibirlos sin acoplamiento.
    """

    def __init__(
        self,
        port: Optional[str] = None,
        on_tag_detected: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ):
        self.port = port
        self.on_tag_detected = on_tag_detected or (lambda chip_id: None)
        self.on_error = on_error or (lambda msg: None)

        self._serial: Optional[serial.Serial] = None
        self.last_error: Optional[Exception] = None
        self.connected = False
        self.scanning = False

    # ------------------------------------------------------------------ #
    # Conexión                                                             #
    # ------------------------------------------------------------------ #

    def connect(self) -> bool:
        """Abre el puerto serial e inicializa el lector."""
        if not self.port:
            self._emit_error("No se especificó puerto COM")
            return False
        try:
            logger.info(f"Conectando a {self.port} @ {BAUDRATE} bps...")
            self.last_error = None
            self._serial = serial.Serial(
                port=self.port,
                baudrate=BAUDRATE,
                timeout=TIMEOUT,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
            )
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
            time.sleep(1)
            self._initialize_reader()
            self.connected = True
            logger.info(f"Lector conectado en {self.port}")
            return True
        except Exception as e:
            self.last_error = e
            # Error de conexión inicial: solo loguear, no disparar on_error.
            # El caller (ws_server) es responsable de informar el fallo al frontend.
            logger.error(f"Error conectando a {self.port}: {e}")
            return False

    def disconnect(self) -> None:
        """Detiene el escaneo y cierra el puerto serial."""
        if self.scanning:
            self.stop_scanning()
        if self._serial and self._serial.is_open:
            self._serial.close()
        self.connected = False
        logger.info("Lector desconectado")

    def _initialize_reader(self) -> None:
        """
        Secuencia obligatoria de inicialización del YR9011.
        Sin el paso 0x75 (Host mode) el lector no responde comandos.
        """
        self._serial.write(self._build_cmd(0x70, b"\x00"))   # Reset
        time.sleep(1)
        self._serial.write(self._build_cmd(0x75, b"\x01"))   # Host mode
        time.sleep(0.3)
        self._serial.write(self._build_cmd(0x74, b"\x00"))   # RF on
        time.sleep(0.3)
        self._serial.write(self._build_cmd(0x7A, b"\x00"))   # Power default
        time.sleep(0.3)

    # ------------------------------------------------------------------ #
    # Escaneo                                                              #
    # ------------------------------------------------------------------ #

    def start_scanning(self) -> None:
        """Inicia lectura continua en un hilo daemon."""
        if not self.connected:
            self._emit_error("Lector no conectado")
            return
        if self.scanning:
            return
        self.scanning = True
        import threading
        t = threading.Thread(target=self._scan_loop, daemon=True)
        t.start()
        logger.info("Escaneo continuo iniciado")

    def stop_scanning(self) -> None:
        """Señaliza al hilo de escaneo que se detenga."""
        self.scanning = False
        logger.info("Escaneo continuo detenido")

    def _scan_loop(self) -> None:
        """
        Loop de lectura continua con debouncing.
        Extrae frames del buffer acumulativo para manejar respuestas parciales.
        """
        last_seen: Dict[str, float] = {}
        buffer = b""
        cmd = self._build_cmd(0x89, b"\x01")

        while self.scanning and self.connected:
            try:
                self._serial.write(cmd)
                time.sleep(SCAN_INTERVAL)

                if self._serial.in_waiting > 0:
                    buffer += self._serial.read(self._serial.in_waiting)
                    frames = self._extract_frames(buffer)

                    for frame in frames:
                        chip_id = self._parse_inventory_frame(frame)
                        if not chip_id:
                            continue
                        now = time.time()
                        if now - last_seen.get(chip_id, 0) < DEBOUNCE_S:
                            continue
                        last_seen[chip_id] = now
                        logger.info(f"Tag detectado: {chip_id}")
                        self.on_tag_detected(chip_id)

                    if frames:
                        last = frames[-1]
                        pos = buffer.rfind(last)
                        buffer = buffer[pos + len(last):]

                time.sleep(0.05)
            except Exception as e:
                # Detectar desconexión física del USB.
                # Se compara por código numérico (winerror/errno) para no depender
                # del idioma del SO (los mensajes varían en español/inglés).
                #   WinError 5   — ERROR_ACCESS_DENIED
                #   WinError 2   — ERROR_FILE_NOT_FOUND (puerto cerrado por SO)
                #   WinError 22  — ERROR_BAD_COMMAND
                #   WinError 31  — ERROR_GEN_FAILURE
                #   WinError 433 — ERROR_DEVICE_NOT_CONNECTED
                #   WinError 1167— ERROR_DEVICE_NOT_CONNECTED (variante)
                DISCONNECT_WINERRORS = {2, 5, 22, 31, 433, 1167}
                DISCONNECT_ERRNOS    = {2, 5, 22}
                DISCONNECT_KEYWORDS  = (
                    "device not connected", "access is denied", "file not found",
                    "device not found", "clearcommerror", "writefile failed",
                    "dispositivo no", "acceso denegado", "no puede encontrar",
                    "no se puede encontrar", "error de e/s",
                )
                winerr    = getattr(e, 'winerror', None)
                errno_val = getattr(e, 'errno',    None)
                error_str = str(e).lower()

                if (winerr in DISCONNECT_WINERRORS
                        or errno_val in DISCONNECT_ERRNOS
                        or any(k in error_str for k in DISCONNECT_KEYWORDS)):
                    logger.error(f"Lector desconectado fisicamente (winerr={winerr}): {e}")
                    self.connected = False
                    self.scanning  = False
                    self._emit_error("USB_DISCONNECTED")
                    return  # Salir del loop — main.py reconectara
                logger.error(f"Error en loop de escaneo: {e}")
                time.sleep(1)

    # ------------------------------------------------------------------ #
    # Protocolo YR9011                                                     #
    # ------------------------------------------------------------------ #

    def _checksum(self, data: bytes) -> int:
        return (sum(data) + 0x42) & 0xFF

    def _build_cmd(self, cmd: int, data: bytes = b"") -> bytes:
        """
        Construye un frame de comando. El comando 0x89 (inventory) usa
        length fijo = 0x04 según especificación INVELION.
        """
        if cmd == 0x89:
            body = bytes([0x04, ADDRESS, cmd]) + data
            return b"\xA0" + body + bytes([self._checksum(body + b"\x00")])
        length = 1 + 1 + len(data) + 1
        body = bytes([length, ADDRESS, cmd]) + data + b"\x00"
        return b"\xA0" + body + bytes([self._checksum(body)])

    def _extract_frames(self, buf: bytes) -> List[bytes]:
        """Extrae frames completos (0xA0 ... ) del buffer acumulativo."""
        frames, i = [], 0
        while i < len(buf):
            if buf[i] != 0xA0 or i + 2 >= len(buf):
                i += 1
                continue
            total = buf[i + 1] + 2
            if i + total > len(buf):
                break
            frames.append(buf[i:i + total])
            i += total
        return frames

    def _parse_inventory_frame(self, frame: bytes) -> Optional[str]:
        """
        Extrae el chip ID de una respuesta 0x89.

        Los últimos 2 bytes del payload (posiciones data[-3:-1]) contienen
        el UID del tag según el análisis del protocolo real del YR9011.
        El campo full_data_hex se loguea para facilitar ajustes si los IDs
        del hospital tienen un formato diferente al esperado.
        """
        if len(frame) < 4 or frame[3] != 0x89:
            return None
        data = frame[4:-1]
        if len(data) < 16:
            return None

        full_hex = data.hex().upper()
        logger.debug(f"YR9011 payload completo: {full_hex}")

        uid_bytes = data[-3:-1]
        if len(uid_bytes) < 2:
            return None

        chip_id = uid_bytes.hex().upper()
        return chip_id

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _emit_error(self, msg: str) -> None:
        logger.error(msg)
        self.on_error(msg)
