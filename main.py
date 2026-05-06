#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chip-Assigner — Servicio local de asignación de chips RFID para STEH.

Corre en background con un ícono en la bandeja del sistema:
  🟠 Naranja — esperando que se conecte el lector YR9011
  🟢 Verde   — lector conectado, listo para escanear
  🔴 Rojo    — error de conexión

Clic derecho en el ícono → Salir para detener el servicio.
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from hardware.yr9011_driver import YR9011Driver, find_yr9011_port
from server.ws_server import ChipAssignerServer

CONFIG_FILE    = Path(__file__).parent / "config.json"
DEFAULT_WS_HOST = "localhost"
DEFAULT_WS_PORT = 8765
RETRY_INTERVAL  = 5


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
    p = argparse.ArgumentParser(description="STEH Chip-Assigner")
    p.add_argument("--port",    help="Puerto COM del YR9011 (ej. COM5)")
    p.add_argument("--ws-port", type=int, help=f"Puerto WebSocket (default: {DEFAULT_WS_PORT})")
    p.add_argument("--no-tray", action="store_true", help="Desactivar ícono de bandeja")
    return p.parse_args()


async def connect_reader(server: ChipAssignerServer, forced_port, tray=None) -> None:
    """Auto-detecta y conecta el YR9011. Reintenta si no lo encuentra."""
    logger = logging.getLogger(__name__)

    while True:
        if server._driver and server._driver.connected:
            return

        port = forced_port or find_yr9011_port()

        if not port:
            logger.warning(f"YR9011 no encontrado. Reintentando en {RETRY_INTERVAL}s...")
            if tray:
                tray.set_waiting()
            await asyncio.sleep(RETRY_INTERVAL)
            continue

        driver = YR9011Driver(
            port=port,
            on_tag_detected=server._on_tag_detected_from_thread,
            on_error=lambda m: logging.getLogger(__name__).error(f"YR9011: {m}"),
        )

        if driver.connect():
            server._driver = driver
            logger.info(f"YR9011 listo en {port}")
            if tray:
                tray.set_ready(port)
            await server._broadcast({
                "type": "status", "connected": True, "scanning": False, "port": port
            })
            return
        else:
            logger.warning(f"No se pudo conectar a {port}. Reintentando en {RETRY_INTERVAL}s...")
            if tray:
                tray.set_error(f"no se pudo conectar a {port}")
            await asyncio.sleep(RETRY_INTERVAL)


async def watch_disconnection(server: ChipAssignerServer, forced_port, tray) -> None:
    """
    Watchdog: detecta desconexión física del YR9011 y reconecta automáticamente.
    Revisa cada 2 segundos si el driver sigue conectado.
    """
    logger = logging.getLogger(__name__)
    while True:
        await asyncio.sleep(2)
        if server._driver and not server._driver.connected:
            logger.warning("YR9011 desconectado. Buscando reconexion...")
            if tray:
                tray.set_waiting()
            server._driver = None
            await server._broadcast({
                "type": "status", "connected": False, "scanning": False, "port": None
            })
            await connect_reader(server, forced_port, tray)


async def run_server(ws_host, ws_port, forced_port, tray=None) -> None:
    server = ChipAssignerServer()
    asyncio.ensure_future(connect_reader(server, forced_port, tray))
    asyncio.ensure_future(watch_disconnection(server, forced_port, tray))
    await server.start(ws_host, ws_port)


def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)

    config = load_config()
    args   = parse_args()

    ws_host     = config.get("ws_host", DEFAULT_WS_HOST)
    ws_port     = args.ws_port or config.get("ws_port", DEFAULT_WS_PORT)
    forced_port = args.port or config.get("serial_port") or None

    logger.info("=" * 50)
    logger.info("  STEH Chip-Assigner")
    logger.info(f"  WebSocket: ws://{ws_host}:{ws_port}")
    logger.info("  Ctrl+C para detener")
    logger.info("=" * 50)

    # Intentar usar el tray (requiere pystray + pillow)
    tray = None
    if not args.no_tray:
        try:
            from tray import TrayIcon

            stop_event = asyncio.Event()

            def on_quit():
                logger.info("Cerrando desde el tray...")
                loop = asyncio.get_event_loop()
                loop.call_soon_threadsafe(stop_event.set)

            tray = TrayIcon(on_quit=on_quit)
            tray.start()
            logger.info("Ícono de bandeja activo. Clic derecho → Salir para detener.")
        except ImportError:
            logger.info("pystray no disponible, corriendo sin ícono de bandeja.")

    try:
        asyncio.run(run_server(ws_host, ws_port, forced_port, tray))
    except KeyboardInterrupt:
        pass
    finally:
        if tray:
            tray.stop()
        logger.info("Servicio detenido.")


if __name__ == "__main__":
    main()
