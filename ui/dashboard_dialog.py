"""
Дашборд: сводка по статусам и разбивка по типам приборов.
"""
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from db.database import get_all_devices  # noqa: E402

TYPE_ORDER = ["Алкометры", "Тонометры"]


def _count_for_devices(rows):
    total = len(rows)
    green = sum(1 for r in rows if r.get("status") == "green")
    yellow = sum(1 for r in rows if r.get("status") == "yellow")
    red = sum(1 for r in rows if r.get("status") == "red")
    nodata = sum(1 for r in rows if r.get("status") == "no_data")
    return total, green, yellow, red, nodata


class DashboardDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Статистика")
        self.setMinimumSize(640, 420)

        devices = get_all_devices()
        total, green, yellow, red, nodata = _count_for_devices(devices)

        root = QVBoxLayout(self)

        title = QLabel("Сводка")
        f = QFont("Calibri", 11)
        f.setBold(True)
        title.setFont(f)
        root.addWidget(title)

        cards = QGridLayout()
        labels = [
            ("Всего", total, "#E3F2FD"),
            ("В норме", green, "#C8E6C9"),
            ("Скоро срок", yellow, "#FFF9C4"),
            ("Просрочено", red, "#FFCDD2"),
            ("Нет данных", nodata, "#E0E0E0"),
        ]
        for i, (name, val, bg) in enumerate(labels):
            ln = QLabel(name)
            ln.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lv = QLabel(str(val))
            lv.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ff = QFont("Calibri", 18)
            ff.setBold(True)
            lv.setFont(ff)
            inner = QWidget()
            inner_layout = QVBoxLayout(inner)
            inner_layout.addWidget(ln)
            inner_layout.addWidget(lv)
            inner.setStyleSheet(f"background:{bg}; border-radius:8px; padding:12px;")
            cards.addWidget(inner, 0, i)
        root.addLayout(cards)

        t2 = QLabel("По типам приборов")
        t2.setFont(f)
        root.addWidget(t2)

        table = QTableWidget(len(TYPE_ORDER), 6)
        table.setHorizontalHeaderLabels(
            ["Тип", "Всего", "В норме", "Скоро срок", "Просрочено", "Нет данных"]
        )
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        by_type = {t: [d for d in devices if d.get("type") == t] for t in TYPE_ORDER}

        for r, tname in enumerate(TYPE_ORDER):
            rows = by_type.get(tname, [])
            tt, tg, ty, tr, tn = _count_for_devices(rows)
            table.setItem(r, 0, QTableWidgetItem(tname))
            table.setItem(r, 1, QTableWidgetItem(str(tt)))
            table.setItem(r, 2, QTableWidgetItem(str(tg)))
            table.setItem(r, 3, QTableWidgetItem(str(ty)))
            table.setItem(r, 4, QTableWidgetItem(str(tr)))
            table.setItem(r, 5, QTableWidgetItem(str(tn)))

        root.addWidget(table)
