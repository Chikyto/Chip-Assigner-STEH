#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Servidor WebSocket local para el chip-assigner.

Escucha en ws://localhost:8765 y permite al frontend STEH:
  1. Conectar/desconectar el lector YR9011 USB
  2. Iniciar/detener un escaneo de chip
  3. Consultar estado y listar puertos disponibles

Protocolo (Frontend → Servicio):
    {"action": "status"}
    {"action": "list_ports"}
    {"action": "connect",    "port": "COM3"}
    {"action": "disconnect"}
    {"action": "scan"}
    {"action": "stop"}

Protocolo (Servicio → Frontend):
    {"type": "status",          "connected": bool, "scanning": bool, "port": str|null}
    {"type": "ports",           "ports": [...]}
    {"type": "connected",       "port": str}
    {"type": "disconnected"}
    {"type": "scanning_started"}
    {"type": "scanning_stopped"}
    {"type": "chip_detected",   "chip_id": str}
    {"type": "error",           "message": str}
"""

import asyncio
import json
import logging
from typing import Optional, Set

import websockets
from websockets.server import WebSocketServerProtocol

from hardware.yr9011_driver import YR9011Driver, list_available_ports

logger = logging.getLogger(__name__)


class ChipAssignerServer:
    """
    Servidor WebSocket que expone el YR9011 al frontend.

    El driver serial corre en un hilo daemon; las detecciones se pasan
    al loop asyncio mediante run_coroutine_threadsafe para evitar race
    conditions entre el hilo serial y los handlers async.
    """

    def __init__(self) -> None:
        self._driver: Optional[YR9011Driver] = None
        self._clients: Set[WebSocketServerProtocol] = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._detection_queue: Optional[asyncio.Queue] = None
        self._dispatcher_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------ #
    # Arranque                                                             #
    # ------------------------------------------------------------------ #

    async def start(self, host: str, port: int) -> None:
        """Arranca el servidor y bloquea hasta recibir señal de cierre."""
        self._loop = asyncio.get_running_loop()
        self._detection_queue = asyncio.Queue()
        self._dispatcher_task = asyncio.create_task(self._dispatch_detections())

        logger.info(f"Chip-Assigner escuchando en ws://{host}:{port}")
        async with websockets.serve(self._handle_client, host, port):
            await asyncio.Future()  # Corre indefinidamente

    # ------------------------------------------------------------------ #
    # Manejo de clientes                                                   #
    # ------------------------------------------------------------------ #

    async def _handle_client(self, ws: WebSocketServerProtocol) -> None:
        self._clients.add(ws)
        logger.info(f"Cliente conectado ({len(self._clients)} total)")
        try:
            await self._send(ws, self._status_msg())
            async for raw in ws:
                await self._dispatch_action(ws, raw)
        except websockets.exceptions.ConnectionClosedOK:
            pass
        except Exception as e:
            logger.error(f"Error en cliente: {e}")
        finally:
            self._clients.discard(ws)
            logger.info(f"Cliente desconectado ({len(self._clients)} restantes)")

    async def _dispatch_action(self, ws: WebSocketServerProtocol, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            await self._send(ws, {"type": "error", "message": "JSON inválido"})
            return

        action = msg.get("action")

        if action == "status":
            await self._send(ws, self._status_msg())

        elif action == "list_ports":
            ports = list_available_ports()
            await self._send(ws, {"type": "ports", "ports": ports})

        elif action == "connect":
            await self._action_connect(ws, msg.get("port"))

        elif action == "disconnect":
            await self._action_disconnect()

        elif action == "scan":
            await self._action_scan(ws)

        elif action == "stop":
            await self._action_stop()

        else:
            await self._send(ws, {"type": "error", "message": f"Acción desconocida: {action}"})

    # ------------------------------------------------------------------ #
    # Acciones del driver                                                  #
    # ------------------------------------------------------------------ #

    async def _action_connect(self, ws: WebSocketServerProtocol, port: Optional[str]) -> None:
        if not port:
            await self._send(ws, {"type": "error", "message": "Se requiere 'port'"})
            return
        if self._driver and self._driver.connected:
            self._driver.disconnect()

        self._driver = YR9011Driver(
            port=port,
            on_tag_detected=self._on_tag_detected_from_thread,
            on_error=self._on_error_from_thread,
        )
        if self._driver.connect():
            await self._broadcast({"type": "connected", "port": port})
        else:
            await self._broadcast({"type": "error", "message": f"No se pudo conectar a {port}"})
            self._driver = None

    async def _action_disconnect(self) -> None:
        if self._driver:
            self._driver.disconnect()
            self._driver = None
        await self._broadcast({"type": "disconnected"})

    async def _action_scan(self, ws: WebSocketServerProtocol) -> None:
        if not self._driver or not self._driver.connected:
            await self._send(ws, {"type": "error", "message": "Lector no conectado"})
            return
        self._driver.start_scanning()
        await self._broadcast({"type": "scanning_started"})

    async def _action_stop(self) -> None:
        if self._driver and self._driver.scanning:
            self._driver.stop_scanning()
        await self._broadcast({"type": "scanning_stopped"})

    # ------------------------------------------------------------------ #
    # Bridge hilo-serial → asyncio                                        #
    # ------------------------------------------------------------------ #

    def _on_tag_detected_from_thread(self, chip_id: str) -> None:
        """Llamado desde el hilo serial; encola la detección en el loop async."""
        if self._loop and self._detection_queue:
            asyncio.run_coroutine_threadsafe(
                self._detection_queue.put(chip_id),
                self._loop,
            )

    def _on_error_from_thread(self, message: str) -> None:
        """Llamado desde el hilo serial; difunde el error a los clientes."""
        if self._loop:
            asyncio.run_coroutine_threadsafe(
                self._broadcast({"type": "error", "message": message}),
                self._loop,
            )

    async def _dispatch_detections(self) -> None:
        """Tarea asyncio que lee la cola y difunde chip_detected a todos los clientes."""
        while True:
            chip_id = await self._detection_queue.get()
            await self._broadcast({"type": "chip_detected", "chip_id": chip_id})

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _status_msg(self) -> dict:
        return {
            "type": "status",
            "connected": bool(self._driver and self._driver.connected),
            "scanning": bool(self._driver and self._driver.scanning),
            "port": self._driver.port if self._driver else None,
        }

    async def _send(self, ws: WebSocketServerProtocol, data: dict) -> None:
        try:
            await ws.send(json.dumps(data))
        except Exception:
            pass

    async def _broadcast(self, data: dict) -> None:
        """Envía un mensaje a todos los clientes conectados."""
        if not self._clients:
            return
        payload = json.dumps(data)
        await asyncio.gather(
            *(ws.send(payload) for ws in list(self._clients)),
            return_exceptions=True,
        )
