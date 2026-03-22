import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from db.database import get_connection, get_location_choices
from ui.device_card import DatePickerWidget


class AddDeviceDialog(QDialog):
    """Форма добавления нового прибора."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Добавить новый прибор")
        self.setMinimumWidth(480)

        root = QVBoxLayout(self)
        root.setSpacing(12)

        # ── заголовок ─────────────────────────────────────────────────────
        title_font = QFont("Calibri", 13)
        title_font.setBold(True)
        title = QLabel("Новый прибор")
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        root.addWidget(line)

        # ── форма ─────────────────────────────────────────────────────────
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)

        lbl_font = QFont("Calibri", 10)
        lbl_font.setBold(True)

        def lbl(text):
            l = QLabel(text)
            l.setFont(lbl_font)
            return l

        # Тип прибора — выпадающий список
        self.f_type = QComboBox()
        self.f_type.addItems(["Алкометры", "Тонометры"])
        form.addRow(lbl("Тип прибора:"), self.f_type)

        # Инвентарный номер — обязательное поле
        self.f_inv = QLineEdit()
        self.f_inv.setPlaceholderText("ИМ-00001234  (обязательно)")
        self.f_inv.setMinimumWidth(260)
        form.addRow(lbl("Инв. №:"), self.f_inv)

        # Место (склад/вагон)
        self.f_location = QComboBox()
        self.f_location.setEditable(True)
        self.f_location.setMinimumWidth(320)
        self.f_location.addItems(get_location_choices())
        self.f_location.lineEdit().setPlaceholderText(
            "Ангаро-Ленское 28 ССК Том.фил. (ВАГОН 1)"
        )
        form.addRow(lbl("Место:"), self.f_location)

        # Ответственный
        self.f_resp = QLineEdit()
        self.f_resp.setPlaceholderText("Иванов Иван Иванович")
        form.addRow(lbl("Ответственный:"), self.f_resp)

        # ── разделитель блока поверки ─────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        form.addRow(sep)

        note = QLabel("Данные последней поверки (если известны):")
        note.setStyleSheet("color: #555; font-style: italic;")
        form.addRow(note)

        # Дата поверки
        self.f_vdate = DatePickerWidget("")
        form.addRow(lbl("Дата поверки:"), self.f_vdate)

        # Дата окончания поверки
        self.f_expiry = DatePickerWidget("")
        form.addRow(lbl("Дата окончания:"), self.f_expiry)

        root.addLayout(form)

        # ── кнопки ────────────────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("➕  Добавить")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    # ── валидация и сохранение ────────────────────────────────────────────
    def _validate_and_accept(self):
        inv = self.f_inv.text().strip()
        if not inv:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Инвентарный номер обязателен для заполнения.",
            )
            self.f_inv.setFocus()
            return

        device_type  = self.f_type.currentText()
        location     = self.f_location.currentText().strip()
        resp         = self.f_resp.text().strip()
        expiry       = self.f_expiry.get_value()
        vdate        = self.f_vdate.get_value()

        conn = get_connection()
        cur  = conn.cursor()

        # добавляем прибор
        cur.execute(
            """
            INSERT INTO devices (type, inventory_number, location, responsible_fio)
            VALUES (?, ?, ?, ?)
            """,
            (device_type, inv, location, resp),
        )
        device_id = cur.lastrowid

        # если указана дата окончания — сразу добавляем поверку
        if expiry:
            cur.execute(
                """
                INSERT INTO verifications
                    (device_id, verification_date, expiry_date, result, comment)
                VALUES (?, ?, ?, ?, ?)
                """,
                (device_id, vdate or None, expiry, "пройдено", "При добавлении прибора"),
            )

        conn.commit()
        conn.close()
        self.accept()
