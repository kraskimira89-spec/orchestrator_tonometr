"""Пути к ресурсам приложения (исходники и сборка PyInstaller)."""

import os
import sys


def get_help_index_path() -> str:
    """
    Абсолютный путь к help/index.html.
    В onefile-сборке сначала ищет в распакованном каталоге (_MEIPASS),
    затем рядом с .exe (портативная папка), затем корень проекта при запуске из исходников.
    """
    name = os.path.join("help", "index.html")

    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        p = os.path.join(sys._MEIPASS, name)
        if os.path.isfile(p):
            return os.path.abspath(p)

    base = os.environ.get("APP_BASE_DIR")
    if base:
        p = os.path.join(base, name)
        if os.path.isfile(p):
            return os.path.abspath(p)

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.abspath(os.path.join(root, name))
