#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import subprocess
from typing import Optional

import serial.tools.list_ports


def describe_serial_issue(port: str, error: Exception | None) -> str:
    error_text = str(error) if error else ""
    port_info = next(
        (item for item in serial.tools.list_ports.comports() if item.device.upper() == port.upper()),
        None,
    )

    if isinstance(error, FileNotFoundError) or "FileNotFoundError" in error_text:
        return f"{port} no existe en esta maquina."

    if isinstance(error, PermissionError) or "PermissionError" in error_text:
        device_hint = ""
        if port_info:
            device_hint = f" Dispositivo detectado: {port_info.description}."
        return f"{port} existe pero esta ocupado por otro proceso o sin permisos.{device_hint}"

    if port_info:
        return f"{port} detectado como {port_info.description}, pero no se pudo abrir: {error}"

    if error:
        return f"No se pudo abrir {port}: {error}"

    return f"No se pudo abrir {port}."


def find_tcp_listener_process(port: int) -> Optional[str]:
    try:
        result = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None

    pid = _extract_listener_pid(result.stdout, port)
    if not pid:
        return None

    try:
        tasklist = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return f"PID {pid}"

    process_name = _extract_process_name(tasklist.stdout)
    if process_name:
        return f"PID {pid} ({process_name})"
    return f"PID {pid}"


def _extract_listener_pid(output: str, port: int) -> Optional[str]:
    port_suffix = f":{port}"
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if "LISTENING" not in line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        local_address = parts[1]
        pid = parts[-1]
        if local_address.endswith(port_suffix):
            return pid
    return None


def _extract_process_name(output: str) -> Optional[str]:
    line = output.strip()
    if not line or line.startswith("INFO:"):
        return None

    if line.startswith('"'):
        parts = [part.strip('"') for part in line.split('","')]
        if parts:
            return parts[0]

    return None
