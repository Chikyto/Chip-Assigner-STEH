#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ícono en la bandeja del sistema para STEH Chip-Assigner.

Muestra el estado del servicio y permite cerrarlo desde el tray.
"""

import threading
import pystray
from PIL import Image, ImageDraw


def _make_icon(color: str) -> Image.Image:
    """Genera un ícono circular del color indicado."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, size - 4, size - 4], fill=color)
    return img


# Íconos según estado
ICON_READY      = _make_icon("#10b981")  # verde  — lector conectado
ICON_WAITING    = _make_icon("#f59e0b")  # naranja — esperando lector
ICON_ERROR      = _make_icon("#ef4444")  # rojo   — error


class TrayIcon:
    """Maneja el ícono de bandeja en un hilo separado."""

    def __init__(self, on_quit):
        self._on_quit = on_quit
        self._icon = pystray.Icon(
            name="STEH Chip-Assigner",
            icon=ICON_WAITING,
            title="STEH Chip-Assigner — Esperando lector...",
            menu=pystray.Menu(
                pystray.MenuItem("STEH Chip-Assigner", None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Salir", self._quit),
            ),
        )

    def set_waiting(self):
        self._icon.icon  = ICON_WAITING
        self._icon.title = "STEH Chip-Assigner — Esperando lector YR9011..."

    def set_ready(self, port: str):
        self._icon.icon  = ICON_READY
        self._icon.title = f"STEH Chip-Assigner — Lector conectado ({port})"

    def set_error(self, msg: str):
        self._icon.icon  = ICON_ERROR
        self._icon.title = f"STEH Chip-Assigner — Error: {msg}"

    def start(self):
        """Arranca el ícono en un hilo daemon."""
        t = threading.Thread(target=self._icon.run, daemon=True)
        t.start()

    def stop(self):
        self._icon.stop()

    def _quit(self, icon, item):
        self._on_quit()
        icon.stop()
