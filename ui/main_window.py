import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from db.database import get_all_devices, get_connection, init_database, update_responsible_fio
from ui.verification_dialog import VerificationDialog
from ui.device_card import DeviceCardDialog
from ui.add_device_dialog import AddDeviceDialog
from ui.date_delegate import DateDelegate


# ── Делегат: жирная черта под строкой заголовков ──────────────────────────────
class HeaderBorderDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option, index):
        super().paint(painter, option, index)
        if index.row() == 1:
            pen = QPen(QColor("#000000"))
            pen.setWidth(3)
            painter.setPen(pen)
            rect = option.rect
            painter.drawLine(rect.bottomLeft(), rect.bottomRight())


# Индексы столбцов в таблице
COL_ID       = 0
COL_TYPE     = 1
COL_INV      = 2      # ← Инв. №  (колонка 2)
COL_LOCATION = 3      # ← Место   (колонка 3)
COL_EXPIRY   = 4
COL_STATUS   = 5
COL_RESP     = 6

COLUMNS = ["ID", "Тип", "Инв. №", "Место", "Дата окончания", "Статус", "Ответственный"]

# Поля БД, соответствующие каждому столбцу (для сортировки и поиска)
COL_FIELDS = {
    COL_ID:       "id",
    COL_TYPE:     "type",
    COL_INV:      "inventory_number",
    COL_LOCATION: "location",
    COL_EXPIRY:   "expiry_date",
    COL_STATUS:   "status",
    COL_RESP:     "responsible_fio",
}

STATUS_ORDER = {"green": 0, "yellow": 1, "red": 2, "no_data": 3}

STATUS_COLORS = {
    "green":   ("#C6EFCE", "#276221"),
    "yellow":  ("#FFEB9C", "#9C5700"),
    "red":     ("#FFC7CE", "#9C0006"),
    "no_data": ("#D9D9D9", "#444444"),
}

STATUS_LABELS = {
    "green":   "В норме",
    "yellow":  "Скоро срок",
    "red":     "Просрочено",
    "no_data": "Нет данных",
}

HEADER_ROWS = 2   # строка 0 — нумерация, строка 1 — названия


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Оркестратор — приборы")
        self.resize(1200, 700)

        self._sort_col = None
        self._sort_asc = True

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # ── панель фильтров ───────────────────────────────────────────────
        filters_layout = QHBoxLayout()
        layout.addLayout(filters_layout)

        filters_layout.addWidget(QLabel("Тип:"))
        self.type_filter = QComboBox()
        self.type_filter.addItems(["Все", "Алкометры", "Тонометры"])
        self.type_filter.currentIndexChanged.connect(self.refresh_table)
        filters_layout.addWidget(self.type_filter)

        filters_layout.addWidget(QLabel("Статус:"))
        self.status_filter = QComboBox()
        self.status_filter.addItems(["Все", "🟢 Зелёный", "🟡 Жёлтый", "🔴 Красный", "⚪ Нет данных"])
        self.status_filter.currentIndexChanged.connect(self.refresh_table)
        filters_layout.addWidget(self.status_filter)

        filters_layout.addWidget(QLabel("Место:"))
        self.location_filter = QComboBox()
        self.location_filter.addItem("Все")
        self.location_filter.currentIndexChanged.connect(self.refresh_table)
        filters_layout.addWidget(self.location_filter)

        filters_layout.addWidget(QLabel("Ответственный:"))
        self.responsible_filter = QComboBox()
        self.responsible_filter.addItem("Все")
        self.responsible_filter.currentIndexChanged.connect(self.refresh_table)
        filters_layout.addWidget(self.responsible_filter)

        self.refresh_button = QPushButton("Обновить")
        self.refresh_button.clicked.connect(self.refresh_table)
        filters_layout.addWidget(self.refresh_button)

        filters_layout.addWidget(QLabel("Поиск по столбцу:"))
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Введите текст...")
        self.search_box.textChanged.connect(self.refresh_table)
        filters_layout.addWidget(self.search_box)

        self.add_btn = QPushButton("➕  Добавить прибор")
        self.add_btn.setStyleSheet(
            "QPushButton { background:#1F3864; color:white; font-weight:bold; "
            "padding:4px 14px; border-radius:4px; }"
            "QPushButton:hover { background:#2E4FA3; }"
        )
        self.add_btn.clicked.connect(self.on_add_device)
        filters_layout.addWidget(self.add_btn)

        filters_layout.addStretch()

        # ── таблица ───────────────────────────────────────────────────────
        self.table = QTableWidget()
        self._header_delegate = HeaderBorderDelegate()
        self.table.setItemDelegate(self._header_delegate)

        # делегат с календарём только для колонки "Дата окончания"
        self._date_delegate = DateDelegate()
        self.table.setItemDelegateForColumn(COL_EXPIRY, self._date_delegate)
        self.table.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked
        )
        self.table.horizontalHeader().setVisible(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(False)

        # клик по заголовку (строка 1) — сортировка
        self.table.cellClicked.connect(self.on_cell_clicked)
        self.table.cellDoubleClicked.connect(self.on_cell_double_clicked)
        self.table.itemChanged.connect(self.on_item_changed)

        layout.addWidget(self.table)

        init_database()
        self.refresh_table()
        self.fill_filter_values()

    # ── вспомогательные ───────────────────────────────────────────────────
    def _status_from_filter(self):
        t = self.status_filter.currentText()
        return {
            "🟢 Зелёный": "green",
            "🟡 Жёлтый":  "yellow",
            "🔴 Красный": "red",
            "⚪ Нет данных": "no_data",
        }.get(t, "")

    def _status_key_from_label(self, label: str) -> str:
        return {
            "В норме":    "green",
            "Скоро срок": "yellow",
            "Просрочено": "red",
        }.get(label, "no_data")

    # ── заполнение выпадашек ──────────────────────────────────────────────
    def fill_filter_values(self):
        devices = get_all_devices()
        locations   = sorted({r["location"] for r in devices if r.get("location")})
        responsibles = sorted({r["responsible_fio"] for r in devices if r.get("responsible_fio")})

        cur_loc  = self.location_filter.currentText()
        cur_resp = self.responsible_filter.currentText()

        self.location_filter.blockSignals(True)
        self.responsible_filter.blockSignals(True)

        self.location_filter.clear()
        self.location_filter.addItem("Все")
        self.location_filter.addItems(locations)

        self.responsible_filter.clear()
        self.responsible_filter.addItem("Все")
        self.responsible_filter.addItems(responsibles)

        idx = self.location_filter.findText(cur_loc)
        if idx != -1:
            self.location_filter.setCurrentIndex(idx)

        idx = self.responsible_filter.findText(cur_resp)
        if idx != -1:
            self.responsible_filter.setCurrentIndex(idx)

        self.location_filter.blockSignals(False)
        self.responsible_filter.blockSignals(False)

    def on_add_device(self):
        dlg = AddDeviceDialog(self)
        if dlg.exec():
            init_database()
            self.refresh_table()
            self.fill_filter_values()
            # прокручиваем к последней строке — там новый прибор
            last_row = self.table.rowCount() - 1
            if last_row >= HEADER_ROWS:
                self.table.scrollToItem(
                    self.table.item(last_row, 0),
                )
                self.table.selectRow(last_row)

    # ── основная отрисовка таблицы ────────────────────────────────────────
    def refresh_table(self):
        self.table.blockSignals(True)

        all_devices = get_all_devices()

        data_rows    = all_devices
        summary_rows = []

        # ── фильтрация (только data_rows) ────────────────────────────────
        type_filter       = self.type_filter.currentText()
        status_filter_val = self._status_from_filter()
        location_filter   = self.location_filter.currentText()
        resp_filter       = self.responsible_filter.currentText()
        search_text       = self.search_box.text().strip().lower()
        current_col       = self.table.currentColumn()

        filtered = []
        for row in data_rows:
            if type_filter != "Все" and row.get("type") != type_filter:
                continue
            if status_filter_val and row.get("status") != status_filter_val:
                continue
            if location_filter != "Все" and row.get("location") != location_filter:
                continue
            if resp_filter != "Все" and row.get("responsible_fio") != resp_filter:
                continue
            if search_text and current_col not in (-1, 0, 1):
                field = COL_FIELDS.get(current_col)
                if field:
                    val = row.get(field)
                    if val is None or search_text not in str(val).lower():
                        continue
            filtered.append(row)

        # ── сортировка (только отфильтрованные данные) ────────────────────
        if self._sort_col is not None:
            field = COL_FIELDS.get(self._sort_col)
            if field:
                if field == "status":
                    filtered.sort(
                        key=lambda r: STATUS_ORDER.get(r.get("status") or "no_data", 9),
                        reverse=not self._sort_asc,
                    )
                else:
                    filtered.sort(
                        key=lambda r: (r.get(field) or ""),
                        reverse=not self._sort_asc,
                    )

        all_visible = filtered

        total_rows = len(all_visible) + HEADER_ROWS
        self.table.clearContents()
        self.table.setRowCount(total_rows)
        self.table.setColumnCount(len(COLUMNS))

        # ── строка 0: номера столбцов ────────────────────────────────────
        num_font = QFont("Calibri", 8)
        for c in range(len(COLUMNS)):
            cell = QTableWidgetItem(str(c))
            cell.setFont(num_font)
            cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            cell.setFlags(Qt.ItemFlag.ItemIsEnabled)
            cell.setBackground(QColor("#D9D9D9"))
            cell.setForeground(QColor("#555555"))
            self.table.setItem(0, c, cell)
        self.table.setRowHeight(0, 16)

        # ── строка 1: заголовки ──────────────────────────────────────────
        hdr_font = QFont("Calibri", 10)
        hdr_font.setBold(True)
        for c, col_name in enumerate(COLUMNS):
            # добавляем стрелку сортировки
            arrow = ""
            if self._sort_col == c:
                arrow = " ▲" if self._sort_asc else " ▼"
            cell = QTableWidgetItem(col_name + arrow)
            cell.setFont(hdr_font)
            cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            cell.setFlags(Qt.ItemFlag.ItemIsEnabled)
            cell.setBackground(QColor("#1F3864"))
            cell.setForeground(QColor("#FFFFFF"))
            self.table.setItem(1, c, cell)
        self.table.setRowHeight(1, 28)

        # ── строки данных ────────────────────────────────────────────────
        for r, row in enumerate(all_visible):
            actual_row = r + HEADER_ROWS

            status = row.get("status") or "no_data"
            expiry = row.get("expiry_date") or ""

            values = [
                str(row.get("id") or ""),
                row.get("type") or "",
                row.get("inventory_number") or "",
                row.get("location") or "",
                expiry,
                STATUS_LABELS.get(status, "Нет данных"),
                row.get("responsible_fio") or "",
            ]

            bg_status, fg_status = STATUS_COLORS.get(status, STATUS_COLORS["no_data"])

            for c, val in enumerate(values):
                cell = QTableWidgetItem(val)
                cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if c == COL_STATUS:
                    cell.setBackground(QColor(bg_status))
                    cell.setForeground(QColor(fg_status))
                    cell.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                elif c == COL_EXPIRY:
                    cell.setBackground(QColor("#FFFFFF"))
                    cell.setForeground(QColor("#000000"))
                    cell.setFlags(
                        Qt.ItemFlag.ItemIsEnabled
                        | Qt.ItemFlag.ItemIsSelectable
                        | Qt.ItemFlag.ItemIsEditable
                    )
                elif c == COL_RESP:
                    cell.setBackground(QColor("#FFFFFF"))
                    cell.setForeground(QColor("#000000"))
                    cell.setFlags(
                        Qt.ItemFlag.ItemIsEnabled
                        | Qt.ItemFlag.ItemIsSelectable
                        | Qt.ItemFlag.ItemIsEditable
                    )
                else:
                    cell.setBackground(QColor("#FFFFFF"))
                    cell.setForeground(QColor("#000000"))
                    cell.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)

                self.table.setItem(actual_row, c, cell)

            self.table.setRowHeight(actual_row, 22)

        self.table.resizeColumnsToContents()
        self.table.blockSignals(False)

    # ── клик по ячейке ────────────────────────────────────────────────────
    def on_cell_clicked(self, row, col):
        if row == 1:
            # клик по заголовку — переключаем сортировку
            if self._sort_col == col:
                self._sort_asc = not self._sort_asc
            else:
                self._sort_col = col
                self._sort_asc = True
            self.refresh_table()

    def on_cell_double_clicked(self, row, col):
        # заголовки — игнорируем
        if row < HEADER_ROWS:
            return

        # на колонке даты — разрешаем встроенное редактирование (не карточку)
        if col == COL_EXPIRY:
            return

        id_item = self.table.item(row, COL_ID)
        if not id_item:
            return
        try:
            device_id = int(id_item.text())
        except ValueError:
            return

        # собираем текущие данные строки для передачи в карточку
        def cell_text(c):
            it = self.table.item(row, c)
            return it.text() if it else ""

        device_data = {
            "id":               device_id,
            "type":             cell_text(COL_TYPE),
            "inventory_number": cell_text(COL_INV),
            "location":         cell_text(COL_LOCATION),
            "expiry_date":      cell_text(COL_EXPIRY),
            "responsible_fio":  cell_text(COL_RESP),
            "status":           self._status_key_from_label(cell_text(COL_STATUS)),
            "verification_date": "",
        }

        dlg = DeviceCardDialog(device_data, self)
        if dlg.exec():
            init_database()
            self.refresh_table()
            self.fill_filter_values()

    def on_item_changed(self, item):
        row = item.row()
        col = item.column()

        if row < HEADER_ROWS:
            return

        id_item = self.table.item(row, COL_ID)
        if not id_item:
            return
        try:
            device_id = int(id_item.text())
        except ValueError:
            return

        # Редактирование даты окончания
        if col == COL_EXPIRY:
            new_date = item.text().strip()
            parts = new_date.split("-")
            if len(parts) != 3:
                return
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO verifications (device_id, verification_date, expiry_date, result, comment)
                VALUES (?, ?, ?, ?, ?)
                """,
                (device_id, None, new_date, "пройдено", "Ручное редактирование"),
            )
            conn.commit()
            conn.close()
            init_database()
            self.refresh_table()
            self.fill_filter_values()

        # Редактирование ФИО ответственного
        elif col == COL_RESP:
            fio = item.text().strip()
            update_responsible_fio(device_id, fio)
            # не перезагружаем всю таблицу — просто сохраняем
