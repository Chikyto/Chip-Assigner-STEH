#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test directo del lector YR9011 — sin WebSocket, sin servicios.

Conecta directamente al puerto COM y lee chips. Usar para verificar
que el hardware y el driver funcionan antes de probar el servicio completo.

Uso:
    python test_hardware.py           # Lista puertos y pregunta cuál usar
    python test_hardware.py --port COM3   # Conecta directo a COM3
"""

import argparse
import logging
import sys
import time

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

from hardware.yr9011_driver import YR9011Driver, list_available_ports


def pick_port() -> str:
    ports = list_available_ports()

    if not ports:
        print("\nNo se encontraron puertos COM.")
        print("Verifica que el YR9011 este conectado y el driver instalado.")
        sys.exit(1)

    print("\nPuertos COM disponibles:")
    for i, p in enumerate(ports):
        print(f"  [{i}] {p['port']} — {p['description']}")

    print()
    idx = input("Numero de puerto a usar (Enter para el primero): ").strip()
    if not idx:
        return ports[0]["port"]
    try:
        return ports[int(idx)]["port"]
    except (ValueError, IndexError):
        print("Seleccion invalida.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Test directo YR9011")
    parser.add_argument("--port", help="Puerto COM (ej. COM3)")
    parser.add_argument("--timeout", type=int, default=30,
                        help="Segundos de escaneo (default: 30)")
    args = parser.parse_args()

    port = args.port or pick_port()

    chips_detected = []

    def on_chip(chip_id: str):
        chips_detected.append(chip_id)
        print(f"\n  *** CHIP DETECTADO: {chip_id} ***\n")

    def on_error(msg: str):
        print(f"\n  [ERROR] {msg}\n")

    print(f"\nConectando a {port}...")
    driver = YR9011Driver(port=port, on_tag_detected=on_chip, on_error=on_error)

    if not driver.connect():
        print(f"No se pudo conectar a {port}.")
        print("Verifica:")
        print("  - Que el puerto sea el correcto")
        print("  - Que no este en uso por otra aplicacion")
        print("  - Que el lector este encendido")
        sys.exit(1)

    print(f"Lector conectado en {port}")
    print(f"Iniciando escaneo por {args.timeout} segundos...")
    print("Acerca un chip RFID al lector...")
    print("(Ctrl+C para detener antes)\n")

    driver.start_scanning()

    try:
        for remaining in range(args.timeout, 0, -1):
            print(f"\r  Esperando chip... {remaining:2d}s restantes | Detectados: {len(chips_detected)}", end="", flush=True)
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nDetenido por el usuario.")

    driver.stop_scanning()
    driver.disconnect()

    print(f"\n\nResumen:")
    print(f"  Chips detectados: {len(chips_detected)}")
    if chips_detected:
        unique = list(dict.fromkeys(chips_detected))
        print(f"  IDs unicos: {unique}")
        print()
        print("IMPORTANTE: Anotar estos IDs para comparar con los que")
        print("detecta la antena YR8900 para el mismo chip fisico.")
    else:
        print("  No se detectaron chips.")
        print("  Verifica que el chip este dentro del rango del lector (~5-10 cm).")


if __name__ == "__main__":
    main()
