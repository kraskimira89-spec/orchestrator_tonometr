"""
Справочник ответственных: ФИО и MAX user_id.
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
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from db.database import get_responsible_persons_rows, upsert_responsible_person  # noqa: E402


class ResponsibleDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ответственные (MAX user_id)")
        self.setMinimumSize(560, 320)

        root = QVBoxLayout(self)
        title = QLabel(
            "Укажите MAX user_id для каждого ответственного.\n"
            "Новую строку добавьте кнопкой «Добавить ответственного» — ФИО вручную, затем «Сохранить»."
        )
        title.setWordWrap(True)
        f = QFont("Calibri", 10)
        f.setBold(True)
        title.setFont(f)
        root.addWidget(title)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["ФИО", "MAX user_id", "id (БД)"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setColumnHidden(2, True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.DoubleClicked)
        root.addWidget(self.table)

        btn_row = QHBoxLayout()
        btn_refresh = QPushButton("Обновить из БД")
        btn_refresh.clicked.connect(self._load)
        btn_add = QPushButton("➕ Добавить ответственного")
        btn_add.setToolTip("Пустая строка: введите ФИО и при необходимости MAX user_id, затем Сохранить")
        btn_add.clicked.connect(self._add_empty_row)
        btn_save = QPushButton("Сохранить")
        btn_save.clicked.connect(self._save)
        btn_close = QPushButton("Закрыть")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_refresh)
        btn_row.addWidget(btn_add)
        btn_row.addStretch()
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_close)
        root.addLayout(btn_row)

        self._load()

    def _fio_readonly_flags(self):
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def _fio_editable_flags(self):
        return (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEditable
        )

    def _add_empty_row(self):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(""))
        self.table.setItem(r, 1, QTableWidgetItem(""))
        self.table.setItem(r, 2, QTableWidgetItem(""))  # пусто = новая запись, ФИО можно править
        self.table.item(r, 0).setFlags(self._fio_editable_flags())
        self.table.setCurrentCell(r, 0)
        self.table.edit(self.table.model().index(r, 0))

    def _load(self):
        rows = get_responsible_persons_rows()
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            fio = row.get("fio") or ""
            mid = row.get("max_user_id")
            mid_s = "" if mid is None else str(mid)
            self.table.setItem(r, 0, QTableWidgetItem(fio))
            self.table.setItem(r, 1, QTableWidgetItem(mid_s))
            rid = row.get("id")
            self.table.setItem(r, 2, QTableWidgetItem("" if rid is None else str(rid)))
            self.table.item(r, 0).setFlags(self._fio_readonly_flags())

    def _save(self):
        for r in range(self.table.rowCount()):
            fio_item = self.table.item(r, 0)
            mid_item = self.table.item(r, 1)
            if not fio_item:
                continue
            fio = fio_item.text().strip()
            if not fio:
                continue
            raw = (mid_item.text() if mid_item else "").strip()
            max_uid = None
            if raw:
                try:
                    max_uid = int(raw)
                except ValueError:
                    QMessageBox.warning(
                        self,
                        "Ошибка",
                        f"Некорректный MAX user_id для «{fio}»: ожидается число.",
                    )
                    return
            try:
                upsert_responsible_person(fio, max_uid)
            except Exception as e:
                QMessageBox.critical(self, "Ошибка БД", str(e))
                return
        QMessageBox.information(self, "Готово", "Справочник ответственных сохранён.")
        self._load()
