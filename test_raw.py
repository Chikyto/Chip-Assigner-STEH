#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test de comunicación raw con el YR9011.
Envía el comando de inicialización y muestra los bytes que responde el lector.
Útil para verificar que el dispositivo responde antes de probar el driver completo.

Uso:
    python test_raw.py --port COM3
"""

import argparse
import sys
import time
import serial
import serial.tools.list_ports


def list_ports():
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("No se encontraron puertos COM.")
        return
    print("Puertos disponibles:")
    for p in ports:
        print(f"  {p.device:8s}  {p.description}  [{p.hwid}]")


def test_port(port: str):
    print(f"\nAbriendo {port} a 115200 bps...")
    try:
        s = serial.Serial(
            port=port, baudrate=115200, timeout=1,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
        )
    except Exception as e:
        print(f"Error abriendo puerto: {e}")
        sys.exit(1)

    s.reset_input_buffer()
    s.reset_output_buffer()
    time.sleep(0.5)

    # Comando: Reset (0x70)
    reset_cmd = bytes([0xA0, 0x04, 0x01, 0x70, 0x00, 0xB7])
    print(f"\nEnviando Reset (0x70): {reset_cmd.hex().upper()}")
    s.write(reset_cmd)
    time.sleep(1.2)
    resp = s.read(s.in_waiting or 16)
    if resp:
        print(f"  Respuesta: {resp.hex().upper()} ({len(resp)} bytes)")
    else:
        print("  Sin respuesta")

    # Comando: Host mode (0x75) — CRITICO, sin esto no funciona
    host_cmd = bytes([0xA0, 0x04, 0x01, 0x75, 0x01, 0xBC])
    print(f"\nEnviando Host mode (0x75): {host_cmd.hex().upper()}")
    s.write(host_cmd)
    time.sleep(0.4)
    resp = s.read(s.in_waiting or 16)
    if resp:
        print(f"  Respuesta: {resp.hex().upper()} ({len(resp)} bytes)")
    else:
        print("  Sin respuesta")

    # Comando: Get firmware version (0x72)
    fw_cmd = bytes([0xA0, 0x04, 0x01, 0x72, 0x00, 0xB9])
    print(f"\nEnviando Get Firmware (0x72): {fw_cmd.hex().upper()}")
    s.write(fw_cmd)
    time.sleep(0.3)
    resp = s.read(s.in_waiting or 16)
    if resp:
        print(f"  Respuesta: {resp.hex().upper()} ({len(resp)} bytes)")
        if len(resp) >= 6 and resp[0] == 0xA0:
            print(f"  -> Firmware: {resp[4]}.{resp[5]}")
            print("\n  COMUNICACION OK - el lector responde correctamente")
        else:
            print("  -> Respuesta inesperada (puede ser otro dispositivo)")
    else:
        print("  Sin respuesta (puerto incorrecto o driver no instalado)")

    # Intentar leer un tag
    print(f"\nIntentando leer tag (cmd 0x89)... acerca un chip al lector")
    inv_cmd = bytes([0xA0, 0x04, 0x01, 0x89, 0x01, 0xD1])
    for i in range(10):
        s.write(inv_cmd)
        time.sleep(0.3)
        resp = s.read(s.in_waiting or 64)
        if resp:
            print(f"  Bytes recibidos [{i+1}]: {resp.hex().upper()}")
            if len(resp) >= 16 and resp[0] == 0xA0 and resp[3] == 0x89:
                data = resp[4:-1]
                uid = data[-3:-1].hex().upper()
                print(f"  -> TAG DETECTADO: {uid}")
                break
        else:
            print(f"  [{i+1}/10] Sin respuesta...", end="\r")

    print()
    s.close()


def main():
    parser = argparse.ArgumentParser(description="Test raw YR9011")
    parser.add_argument("--port", help="Puerto COM (ej. COM3)")
    parser.add_argument("--list", action="store_true", help="Solo listar puertos")
    args = parser.parse_args()

    if args.list:
        list_ports()
        return

    if not args.port:
        list_ports()
        print()
        port = input("Puerto a testear: ").strip()
        if not port:
            sys.exit(1)
    else:
        port = args.port

    test_port(port)


if __name__ == "__main__":
    main()
