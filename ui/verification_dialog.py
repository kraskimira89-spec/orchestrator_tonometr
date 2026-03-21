import os
import sys
from datetime import date

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import (
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QTextEdit,
    QVBoxLayout,
)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from db.database import get_connection  # noqa: E402


class VerificationDialog(QDialog):
    def __init__(self, device_id: int, device_name: str, parent=None):
        super().__init__(parent)
        self.device_id = device_id
        self.setWindowTitle(f"Новая поверка — {device_name}")

        layout = QVBoxLayout(self)

        form = QFormLayout()

        self.verif_date = QDateEdit()
        self.verif_date.setCalendarPopup(True)
        self.verif_date.setDate(QDate.currentDate())
        form.addRow("Дата поверки:", self.verif_date)

        self.expiry_date = QDateEdit()
        self.expiry_date.setCalendarPopup(True)
        # по умолчанию +1 год
        today = date.today()
        self.expiry_date.setDate(QDate(today.year + 1, today.month, today.day))
        form.addRow("Дата окончания:", self.expiry_date)

        self.comment = QTextEdit()
        form.addRow("Комментарий:", self.comment)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save(self):
        qd_ver = self.verif_date.date()
        qd_exp = self.expiry_date.date()

        verif_str = f"{qd_ver.year():04d}-{qd_ver.month():02d}-{qd_ver.day():02d}"
        expiry_str = f"{qd_exp.year():04d}-{qd_exp.month():02d}-{qd_exp.day():02d}"

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO verifications (device_id, verification_date, expiry_date, result, comment)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                self.device_id,
                verif_str,
                expiry_str,
                "пройдено",
                self.comment.toPlainText().strip(),
            ),
        )
        conn.commit()
        conn.close()
