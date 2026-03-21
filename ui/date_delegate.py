import re

from PyQt6.QtCore import QDate, Qt, QModelIndex
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCalendarWidget,
    QHBoxLayout,
    QLineEdit,
    QStyledItemDelegate,
    QToolButton,
    QWidget,
)


def _normalize_date(raw: str) -> str:
    """
    Принимает дату в любом формате:
      23.07.2026 / 23/07/2026 / 2026-07-23 / 23-07-2026
    Возвращает YYYY-MM-DD или '' если не распознано.
    """
    raw = raw.strip()
    # уже YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return raw
    # DD.MM.YYYY или DD/MM/YYYY или DD-MM-YYYY
    m = re.match(r"^(\d{2})[.\-/](\d{2})[.\-/](\d{4})$", raw)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return ""


class _DateEditor(QWidget):
    """Встроенный редактор: поле ввода + кнопка открытия календаря."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAutoFillBackground(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(2)

        self.line = QLineEdit()
        self.line.setPlaceholderText("ГГГГ-ММ-ДД")
        layout.addWidget(self.line)

        self.btn = QToolButton()
        self.btn.setText("📅")
        self.btn.setFixedWidth(26)
        self.btn.clicked.connect(self._open_calendar)
        layout.addWidget(self.btn)

        # всплывающий календарь
        self._cal = QCalendarWidget()
        self._cal.setWindowFlags(Qt.WindowType.Popup)
        self._cal.setGridVisible(True)
        self._cal.activated.connect(self._pick_date)

    def _open_calendar(self):
        raw = self.line.text().strip()
        normalized = _normalize_date(raw)
        if normalized:
            y, m, d = normalized.split("-")
            self._cal.setSelectedDate(QDate(int(y), int(m), int(d)))
        else:
            self._cal.setSelectedDate(QDate.currentDate())
        pos = self.btn.mapToGlobal(self.btn.rect().bottomLeft())
        self._cal.move(pos)
        self._cal.show()

    def _pick_date(self, qdate: QDate):
        self.line.setText(qdate.toString("yyyy-MM-dd"))
        self._cal.hide()

    def get_date(self) -> str:
        return _normalize_date(self.line.text()) or self.line.text().strip()

    def set_date(self, value: str):
        self.line.setText(value)


class DateDelegate(QStyledItemDelegate):
    """
    Делегат для колонки 'Дата окончания'.
    При двойном клике показывает поле ввода с кнопкой 📅.
    Поддерживает ввод вручную в любом формате.
    """

    def createEditor(self, parent, option, index: QModelIndex):
        editor = _DateEditor(parent)
        return editor

    def setEditorData(self, editor: _DateEditor, index: QModelIndex):
        val = index.data(Qt.ItemDataRole.DisplayRole) or ""
        editor.set_date(val)

    def setModelData(self, editor: _DateEditor, model, index: QModelIndex):
        date_str = editor.get_date()
        if date_str:
            model.setData(index, date_str, Qt.ItemDataRole.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)
