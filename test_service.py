#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test end-to-end del servicio WebSocket chip-assigner.

Requiere que main.py este corriendo en otra terminal.
Simula exactamente lo que hara el frontend STEH:
conectar, listar puertos, conectar al YR9011, escanear, recibir chip.

Uso:
    # Terminal 1:
    python main.py

    # Terminal 2:
    python test_service.py
    python test_service.py --port COM3   # Salta seleccion de puerto
"""

import argparse
import asyncio
import json
import sys
import websockets

WS_URL = "ws://localhost:8765"


async def send_recv(ws, action: dict) -> dict:
    """Envia un mensaje y espera la primera respuesta."""
    await ws.send(json.dumps(action))
    return json.loads(await ws.recv())


def show(label: str, msg: dict) -> None:
    ok = "OK" if msg.get("type") != "error" else "ERROR"
    print(f"  [{ok}] {label}: {json.dumps(msg, ensure_ascii=False)}")


async def run(serial_port: str | None) -> None:
    print(f"\nConectando a {WS_URL}...")
    try:
        async with websockets.connect(WS_URL) as ws:
            print("Conectado al servicio.\n")

            # Status inicial (el server lo envia automaticamente)
            status = json.loads(await ws.recv())
            show("Status inicial", status)

            # Listar puertos
            ports_msg = await send_recv(ws, {"action": "list_ports"})
            show("Puertos disponibles", ports_msg)
            ports = ports_msg.get("ports", [])

            if not ports:
                print("\nNo se encontraron puertos COM.")
                print("Conecta el YR9011 y vuelve a intentar.")
                return

            # Elegir puerto
            if serial_port:
                port = serial_port
            else:
                print("\nPuertos encontrados:")
                for i, p in enumerate(ports):
                    print(f"  [{i}] {p['port']} - {p['description']}")
                idx = input("\nNumero de puerto (Enter para el primero): ").strip()
                port = ports[int(idx)]["port"] if idx else ports[0]["port"]

            # Conectar al YR9011
            print(f"\nConectando al YR9011 en {port}...")
            conn_msg = await send_recv(ws, {"action": "connect", "port": port})
            show("Conexion", conn_msg)

            if conn_msg.get("type") == "error":
                print("\nNo se pudo conectar. Verifica el puerto y que el lector este encendido.")
                return

            # Iniciar escaneo
            input("\nPresiona Enter y acerca un chip al lector...")
            scan_msg = await send_recv(ws, {"action": "scan"})
            show("Escaneo", scan_msg)

            print("\nEsperando chip (30 segundos, Ctrl+C para cancelar)...")

            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=30)
                msg = json.loads(msg)
                show("Resultado", msg)

                if msg.get("type") == "chip_detected":
                    print(f"\n*** CHIP ID: {msg['chip_id']} ***")
                    print("\nTest exitoso. Anota este ID para validar contra el YR8900.")
            except asyncio.TimeoutError:
                print("\nTimeout: no se detecto ningun chip en 30 segundos.")
                print("Verifica que el chip este dentro del rango del lector (~5-10 cm).")

            # Detener escaneo
            stop_msg = await send_recv(ws, {"action": "stop"})
            show("Stop", stop_msg)

    except ConnectionRefusedError:
        print(f"Error: no se puede conectar a {WS_URL}")
        print("Asegurate de que 'python main.py' este corriendo en otra terminal.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Test servicio chip-assigner")
    parser.add_argument("--port", help="Puerto COM (ej. COM3). Omitir para seleccionar.")
    args = parser.parse_args()
    asyncio.run(run(args.port))


if __name__ == "__main__":
    main()
