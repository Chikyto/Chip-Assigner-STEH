#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chip-Assigner — Servicio local de asignación de chips RFID para STEH.

Inicia un servidor WebSocket en localhost:8765 al que se conecta el
frontend STEH para leer chips del lector YR9011 USB y asignarlos a equipos.

Uso:
    python main.py                    # Usa config.json
    python main.py --port COM4        # Puerto COM específico (autoconecta)
    python main.py --ws-port 9000     # Puerto WebSocket distinto al default

El servicio no requiere privilegios de administrador. Dejar corriendo
en background mientras se realizan asignaciones desde el navegador.
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from server.ws_server import ChipAssignerServer

CONFIG_FILE = Path(__file__).parent / "config.json"
DEFAULT_WS_HOST = "localhost"
DEFAULT_WS_PORT = 8765


def load_config() -> dict:
    """Carga config.json si existe; retorna defaults si no."""
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
    p.add_argument("--port",    help="Puerto COM del YR9011 (ej. COM3). Autoconecta al arrancar.")
    p.add_argument("--ws-port", type=int, help=f"Puerto WebSocket (default: {DEFAULT_WS_PORT})")
    return p.parse_args()


async def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)

    config = load_config()
    args   = parse_args()

    ws_host = config.get("ws_host", DEFAULT_WS_HOST)
    ws_port = args.ws_port or config.get("ws_port", DEFAULT_WS_PORT)

    server = ChipAssignerServer()

    # Si se pasó --port, conectar el YR9011 al arrancar sin esperar al frontend
    serial_port = args.port or config.get("serial_port")
    if serial_port:
        logger.info(f"Autoconectando YR9011 en {serial_port}...")
        from hardware.yr9011_driver import YR9011Driver
        driver = YR9011Driver(
            port=serial_port,
            on_tag_detected=lambda c: None,  # Se sobreescribe al primer cliente
            on_error=lambda m: logger.error(f"YR9011 error: {m}"),
        )
        if driver.connect():
            server._driver = driver
            logger.info(f"YR9011 listo en {serial_port}")
        else:
            logger.warning(f"No se pudo conectar a {serial_port}. Esperando conexión manual.")

    logger.info("=" * 55)
    logger.info("  STEH Chip-Assigner")
    logger.info(f"  WebSocket: ws://{ws_host}:{ws_port}")
    logger.info("  Conectar el frontend al servicio para asignar chips")
    logger.info("  Ctrl+C para detener")
    logger.info("=" * 55)

    await server.start(ws_host, ws_port)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServicio detenido.")
