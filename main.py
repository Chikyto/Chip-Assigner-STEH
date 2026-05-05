#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chip-Assigner — Servicio local de asignación de chips RFID para STEH.

Inicia un servidor WebSocket en localhost:8765 al que se conecta el
frontend STEH para leer chips del lector YR9011 USB y asignarlos a equipos.

Comportamiento:
- Si el YR9011 está conectado al arrancar: se conecta automáticamente.
- Si no está conectado: espera y reintenta cada 5 segundos en background.
- El frontend siempre puede conectarse al WebSocket; recibirá el estado real.

Uso:
    python main.py                    # Auto-detecta el YR9011
    python main.py --port COM5        # Fuerza un puerto específico
    python main.py --ws-port 9000     # Puerto WebSocket distinto al default
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from hardware.yr9011_driver import YR9011Driver, find_yr9011_port
from server.ws_server import ChipAssignerServer

CONFIG_FILE = Path(__file__).parent / "config.json"
DEFAULT_WS_HOST = "localhost"
DEFAULT_WS_PORT = 8765
RETRY_INTERVAL = 5  # segundos entre reintentos de conexión al YR9011


def load_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="STEH Chip-Assigner WebSocket service")
    p.add_argument("--port",    help="Puerto COM del YR9011 (ej. COM5). Omitir para auto-detectar.")
    p.add_argument("--ws-port", type=int, help=f"Puerto WebSocket (default: {DEFAULT_WS_PORT})")
    return p.parse_args()


async def connect_reader(server: ChipAssignerServer, forced_port: str | None) -> None:
    """
    Intenta conectar el YR9011 al arrancar.
    Si no lo encuentra, reintenta en background cada RETRY_INTERVAL segundos.
    """
    logger = logging.getLogger(__name__)

    while True:
        port = forced_port or find_yr9011_port()

        if not port:
            logger.warning(f"YR9011 no encontrado. Reintentando en {RETRY_INTERVAL}s...")
            await asyncio.sleep(RETRY_INTERVAL)
            continue

        # Si ya hay un driver conectado, no reconectar
        if server._driver and server._driver.connected:
            return

        driver = YR9011Driver(
            port=port,
            on_tag_detected=server._on_tag_detected_from_thread,
            on_error=lambda m: logging.getLogger(__name__).error(f"YR9011: {m}"),
        )

        if driver.connect():
            server._driver = driver
            logger.info(f"YR9011 listo en {port}")
            # Notificar a clientes conectados que el lector está disponible
            await server._broadcast({"type": "status", "connected": True, "scanning": False, "port": port})
            return
        else:
            logger.warning(f"No se pudo conectar a {port}. Reintentando en {RETRY_INTERVAL}s...")
            await asyncio.sleep(RETRY_INTERVAL)


async def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)

    config = load_config()
    args   = parse_args()

    ws_host = config.get("ws_host", DEFAULT_WS_HOST)
    ws_port = args.ws_port or config.get("ws_port", DEFAULT_WS_PORT)
    forced_port = args.port or config.get("serial_port") or None

    server = ChipAssignerServer()

    logger.info("=" * 55)
    logger.info("  STEH Chip-Assigner")
    logger.info(f"  WebSocket: ws://{ws_host}:{ws_port}")
    logger.info("  Ctrl+C para detener")
    logger.info("=" * 55)

    # Conectar el YR9011 en background (no bloquea el arranque del WS server)
    asyncio.ensure_future(connect_reader(server, forced_port))

    await server.start(ws_host, ws_port)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServicio detenido.")
