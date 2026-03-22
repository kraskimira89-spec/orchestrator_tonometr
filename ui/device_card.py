import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCalendarWidget,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from db.database import get_connection, get_device_verifications, update_responsible_fio
from ui.documents_widget import DocumentsWidget


def _date_str_to_qdate(s: str) -> QDate:
    """'2026-07-23' → QDate"""
    try:
        y, m, d = s.split("-")
        return QDate(int(y), int(m), int(d))
    except Exception:
        return QDate.currentDate()


class DatePickerWidget(QWidget):
    """Поле ввода даты с кнопкой открытия календаря."""

    def __init__(self, initial: str = "", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.line = QLineEdit(initial)
        self.line.setPlaceholderText("ГГГГ-ММ-ДД")
        self.line.setFixedWidth(110)
        layout.addWidget(self.line)

        self.btn = QToolButton()
        self.btn.setText("📅")
        self.btn.setToolTip("Выбрать дату")
        self.btn.clicked.connect(self._open_calendar)
        layout.addWidget(self.btn)

        layout.addStretch()

        # всплывающий календарь
        self._cal_popup = QCalendarWidget()
        self._cal_popup.setWindowFlags(Qt.WindowType.Popup)
        self._cal_popup.setGridVisible(True)
        self._cal_popup.activated.connect(self._date_selected)

    def _open_calendar(self):
        qd = _date_str_to_qdate(self.line.text())
        self._cal_popup.setSelectedDate(qd)
        pos = self.btn.mapToGlobal(self.btn.rect().bottomLeft())
        self._cal_popup.move(pos)
        self._cal_popup.show()

    def _date_selected(self, qdate: QDate):
        self.line.setText(qdate.toString("yyyy-MM-dd"))
        self._cal_popup.hide()

    def get_value(self) -> str:
        return self.line.text().strip()


class DeviceCardDialog(QDialog):
    """Карточка прибора — просмотр и редактирование всех полей."""

    def __init__(self, device: dict, parent=None):
        super().__init__(parent)
        self.device = device
        self.setWindowTitle(f"Карточка прибора — ID {device.get('id', '')}")
        self.setMinimumWidth(520)

        root = QVBoxLayout(self)
        root.setSpacing(12)

        # ── заголовок карточки ────────────────────────────────────────────
        title_font = QFont("Calibri", 13)
        title_font.setBold(True)
        title = QLabel(device.get("inventory_number") or "Без инв. №")
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title)

        # горизонтальный разделитель
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        root.addWidget(line)

        # ── форма полей ───────────────────────────────────────────────────
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)

        lbl_font = QFont("Calibri", 10)
        lbl_font.setBold(True)

        def make_label(text):
            l = QLabel(text)
            l.setFont(lbl_font)
            return l

        # Тип
        self.f_type = QLineEdit(device.get("type") or "")
        form.addRow(make_label("Тип:"), self.f_type)

        # Инв. №
        self.f_inv = QLineEdit(device.get("inventory_number") or "")
        form.addRow(make_label("Инв. №:"), self.f_inv)

        # Наименование (модель / название прибора)
        self.f_name = QLineEdit(device.get("name") or "")
        self.f_name.setPlaceholderText("Например: Анализатор Динго")
        form.addRow(make_label("Наименование:"), self.f_name)

        # Серийный номер (заводской)
        self.f_serial = QLineEdit(device.get("serial_number") or "")
        self.f_serial.setPlaceholderText("Заводской серийный номер")
        form.addRow(make_label("Серийный номер:"), self.f_serial)

        # Место
        self.f_location = QLineEdit(device.get("location") or "")
        self.f_location.setMinimumWidth(300)
        form.addRow(make_label("Место:"), self.f_location)

        # Ответственный (ФИО)
        self.f_resp = QLineEdit(device.get("responsible_fio") or "")
        self.f_resp.setPlaceholderText("Иванов Иван Иванович")
        form.addRow(make_label("Ответственный:"), self.f_resp)

        # Дата последней поверки
        self.f_verif_date = DatePickerWidget(device.get("verification_date") or "")
        form.addRow(make_label("Дата поверки:"), self.f_verif_date)

        # Дата окончания поверки
        self.f_expiry = DatePickerWidget(device.get("expiry_date") or "")
        form.addRow(make_label("Дата окончания:"), self.f_expiry)

        root.addLayout(form)

        # ── статус (только показ) ─────────────────────────────────────────
        status = device.get("status") or "no_data"
        STATUS_LABELS = {
            "green":   ("В норме",    "#C6EFCE", "#276221"),
            "yellow":  ("Скоро срок", "#FFEB9C", "#9C5700"),
            "red":     ("Просрочено", "#FFC7CE", "#9C0006"),
            "no_data": ("Нет данных", "#D9D9D9", "#444444"),
        }
        label_text, bg, fg = STATUS_LABELS.get(status, STATUS_LABELS["no_data"])
        status_lbl = QLabel(f"Статус:  {label_text}")
        status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_lbl.setStyleSheet(
            f"background:{bg}; color:{fg}; border-radius:6px; "
            f"padding:6px 20px; font-weight:bold; font-size:11pt;"
        )
        root.addWidget(status_lbl)

        # ── история поверок ─────────────────────────────────────────────────
        hist_title = QLabel("История поверок")
        ht = QFont("Calibri", 10)
        ht.setBold(True)
        hist_title.setFont(ht)
        root.addWidget(hist_title)

        self.history_table = QTableWidget()
        self.history_table.setColumnCount(4)
        self.history_table.setHorizontalHeaderLabels(
            ["Дата поверки", "Дата окончания", "Результат", "Комментарий"]
        )
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.history_table.setMaximumHeight(220)

        did = device.get("id")
        if did is not None:
            rows = get_device_verifications(int(did))
            self.history_table.setRowCount(len(rows))
            for i, rec in enumerate(rows):
                vd = rec.get("verification_date") or "—"
                ed = rec.get("expiry_date") or "—"
                rs = rec.get("result") or "—"
                cm = (rec.get("comment") or "").replace("\n", " ")
                for j, val in enumerate([vd, ed, rs, cm]):
                    self.history_table.setItem(i, j, QTableWidgetItem(str(val)))
            self.history_table.resizeColumnsToContents()
        else:
            self.history_table.setRowCount(0)

        root.addWidget(self.history_table)

        # ── документы (свидетельства) ───────────────────────────────────────
        if did is not None:
            sep2 = QFrame()
            sep2.setFrameShape(QFrame.Shape.HLine)
            sep2.setStyleSheet("color: #ccc;")
            root.addWidget(sep2)

            self.docs_widget = DocumentsWidget(device_id=int(did), parent=self)
            root.addWidget(self.docs_widget)

        # ── кнопки ────────────────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("💾  Сохранить")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self.save_and_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    # ── сохранение ────────────────────────────────────────────────────────
    def save_and_accept(self):
        device_id   = self.device.get("id")
        new_type    = self.f_type.get_value() if hasattr(self.f_type, "get_value") else self.f_type.text().strip()
        new_inv     = self.f_inv.text().strip()
        new_name    = self.f_name.text().strip()
        new_serial  = self.f_serial.text().strip()
        new_loc     = self.f_location.text().strip()
        new_resp    = self.f_resp.text().strip()
        new_expiry  = self.f_expiry.get_value()
        new_vdate   = self.f_verif_date.get_value()

        conn = get_connection()
        cur  = conn.cursor()

        if not new_name:
            new_name = new_type or "Прибор"

        # обновляем основные поля прибора
        cur.execute(
            """
            UPDATE devices
            SET type = ?, name = ?, inventory_number = ?, serial_number = ?,
                location = ?, responsible_fio = ?
            WHERE id = ?
            """,
            (new_type, new_name, new_inv, new_serial, new_loc, new_resp, device_id),
        )

        # если изменилась дата окончания — добавляем новую запись поверки
        old_expiry = self.device.get("expiry_date") or ""
        if new_expiry and new_expiry != old_expiry:
            vdate = new_vdate if new_vdate else None
            cur.execute(
                """
                INSERT INTO verifications
                    (device_id, verification_date, expiry_date, result, comment)
                VALUES (?, ?, ?, ?, ?)
                """,
                (device_id, vdate, new_expiry, "пройдено", "Из карточки прибора"),
            )

        conn.commit()
        conn.close()

        # Автосинхронизация CalDAV (не блокирует сохранение карточки)
        try:
            from core.calendar_sync import auto_sync_device

            expiry_for_sync = new_expiry or old_expiry
            if expiry_for_sync:
                device_for_sync = {
                    "id": device_id,
                    "type": new_type,
                    "inventory_number": new_inv,
                    "location": new_loc,
                    "responsible_fio": new_resp,
                    "calendar_event_id": self.device.get("calendar_event_id"),
                }
                auto_sync_device(device_for_sync, expiry_for_sync)
                self.device["calendar_event_id"] = device_for_sync.get("calendar_event_id")
        except Exception as e:
            print(f"CalDAV auto-sync: {e}")

        self.accept()
