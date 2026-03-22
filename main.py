import os
import sys

# При запуске из .exe (PyInstaller) — базовая папка рядом с .exe
# При запуске из исходников — папка проекта
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

os.environ["APP_BASE_DIR"] = BASE_DIR

# Дальше — импорты приложения (после установки APP_BASE_DIR для db и PyInstaller)
from pathlib import Path

_root = Path(BASE_DIR)
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from PyQt6.QtWidgets import QApplication

from ui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
