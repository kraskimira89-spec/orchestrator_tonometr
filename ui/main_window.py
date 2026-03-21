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
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
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
from ui.side_panel import SidePanel
from ui.import_excel_dialog import ImportExcelDialog
from ui.responsible_dialog import ResponsibleDialog
from ui.dashboard_dialog import DashboardDialog
from ui.caldav_settings_dialog import CalDAVSettingsDialog


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


# ── Константы столбцов ────────────────────────────────────────────────────────
COL_ID       = 0
COL_TYPE     = 1
COL_INV      = 2
COL_LOCATION = 3
COL_EXPIRY   = 4
COL_STATUS   = 5
COL_RESP     = 6

COLUMNS = ["ID", "Тип", "Инв. №", "Место", "Дата окончания", "Статус", "Ответственный"]

COL_FIELDS = {
    COL_ID:       "id",
    COL_TYPE:     "type",
    COL_INV:      "inventory_number",
    COL_LOCATION: "location",
    COL_EXPIRY:   "expiry_date",
    COL_STATUS:   "status",
    COL_RESP:     "responsible_fio",
}

STATUS_ORDER  = {"green": 0, "yellow": 1, "red": 2, "no_data": 3}
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

HEADER_ROWS = 2


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Поверки. Алкометры и Тонометры")
        self.resize(1300, 750)

        self._sort_col = None
        self._sort_asc = True

        central = QWidget()
        self.setCentralWidget(central)

        # ── главный layout: таблица слева, панель справа ──────────────────
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── левая часть ───────────────────────────────────────────────────
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(6, 6, 6, 6)
        left_layout.setSpacing(6)

        # фильтры
        filters_layout = QHBoxLayout()

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

        filters_layout.addStretch()
        left_layout.addLayout(filters_layout)

        # таблица
        self.table = QTableWidget()
        self._header_delegate = HeaderBorderDelegate()
        self.table.setItemDelegate(self._header_delegate)
        self._date_delegate = DateDelegate()
        self.table.setItemDelegateForColumn(COL_EXPIRY, self._date_delegate)
        self.table.setEditTriggers(QTableWidget.EditTrigger.DoubleClicked)
        self.table.horizontalHeader().setVisible(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(False)
        self.table.cellClicked.connect(self.on_cell_clicked)
        self.table.cellDoubleClicked.connect(self.on_cell_double_clicked)
        self.table.itemChanged.connect(self.on_item_changed)
        left_layout.addWidget(self.table)

        main_layout.addWidget(left_widget, stretch=1)

        # ── правая панель ─────────────────────────────────────────────────
        self.side_panel = SidePanel(self)
        self.side_panel.sig_add_device.connect(self.on_add_device)
        self.side_panel.sig_notify.connect(self.on_send_notifications)
        self.side_panel.sig_export.connect(self.on_export_excel)
        self.side_panel.sig_import_excel.connect(self.on_import_excel)
        self.side_panel.sig_responsible.connect(self.on_responsible)
        self.side_panel.sig_dashboard.connect(self.on_dashboard)
        self.side_panel.sig_caldav.connect(self.on_caldav)
        # поиск из панели подключаем к refresh_table
        self.side_panel.search_box.textChanged.connect(self.refresh_table)
        main_layout.addWidget(self.side_panel)

        init_database()
        self.refresh_table()
        self.fill_filter_values()

    # ── вспомогательные ───────────────────────────────────────────────────
    def _status_from_filter(self):
        return {
            "🟢 Зелёный":   "green",
            "🟡 Жёлтый":    "yellow",
            "🔴 Красный":   "red",
            "⚪ Нет данных": "no_data",
        }.get(self.status_filter.currentText(), "")

    def _status_key_from_label(self, label: str) -> str:
        return {
            "В норме":    "green",
            "Скоро срок": "yellow",
            "Просрочено": "red",
        }.get(label, "no_data")

    def _device_full_by_id(self, device_id: int):
        for d in get_all_devices():
            if d.get("id") == device_id:
                return d
        return None

    # ── заполнение фильтров ───────────────────────────────────────────────
    def fill_filter_values(self):
        devices = get_all_devices()
        locations    = sorted({r["location"] for r in devices if r.get("location")})
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

    # ── основная отрисовка таблицы ────────────────────────────────────────
    def refresh_table(self):
        self.table.blockSignals(True)

        all_devices = get_all_devices()

        type_filter   = self.type_filter.currentText()
        status_filter = self._status_from_filter()
        loc_filter    = self.location_filter.currentText()
        resp_filter   = self.responsible_filter.currentText()
        search_text   = self.side_panel.search_box.text().strip().lower()
        current_col   = self.table.currentColumn()

        filtered = []
        for row in all_devices:
            if type_filter != "Все" and row.get("type") != type_filter:
                continue
            if status_filter and row.get("status") != status_filter:
                continue
            if loc_filter != "Все" and row.get("location") != loc_filter:
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

        # сортировка
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

        total_rows = len(filtered) + HEADER_ROWS
        self.table.clearContents()
        self.table.setRowCount(total_rows)
        self.table.setColumnCount(len(COLUMNS))

        # строка 0 — номера столбцов
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

        # строка 1 — заголовки
        hdr_font = QFont("Calibri", 10)
        hdr_font.setBold(True)
        for c, col_name in enumerate(COLUMNS):
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

        # строки данных
        for r, row in enumerate(filtered):
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

        # обновляем счётчик в правой панели
        total  = len(filtered)
        green  = sum(1 for r in filtered if r.get("status") == "green")
        yellow = sum(1 for r in filtered if r.get("status") == "yellow")
        red    = sum(1 for r in filtered if r.get("status") == "red")
        self.side_panel.update_counter(total, green, yellow, red)

        self.table.blockSignals(False)

    # ── клик по ячейке ────────────────────────────────────────────────────
    def on_cell_clicked(self, row, col):
        if row == 1:
            if self._sort_col == col:
                self._sort_asc = not self._sort_asc
            else:
                self._sort_col = col
                self._sort_asc = True
            self.refresh_table()

    def on_cell_double_clicked(self, row, col):
        if row < HEADER_ROWS:
            return
        if col == COL_EXPIRY:
            return

        id_item = self.table.item(row, COL_ID)
        if not id_item:
            return
        try:
            device_id = int(id_item.text())
        except ValueError:
            return

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
        full = self._device_full_by_id(device_id)
        if full:
            device_data["verification_date"] = full.get("verification_date") or ""

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

        elif col == COL_RESP:
            fio = item.text().strip()
            update_responsible_fio(device_id, fio)

    # ── обработчики кнопок из правой панели ───────────────────────────────
    def on_add_device(self):
        dlg = AddDeviceDialog(self)
        if dlg.exec():
            init_database()
            self.refresh_table()
            self.fill_filter_values()
            last_row = self.table.rowCount() - 1
            if last_row >= HEADER_ROWS:
                self.table.scrollToItem(self.table.item(last_row, 0))
                self.table.selectRow(last_row)

    def on_import_excel(self):
        dlg = ImportExcelDialog(self)
        if dlg.exec():
            init_database()
            self.refresh_table()
            self.fill_filter_values()

    def on_responsible(self):
        ResponsibleDialog(self).exec()

    def on_dashboard(self):
        DashboardDialog(self).exec()

    def on_caldav(self):
        CalDAVSettingsDialog(self).exec()

    def on_send_notifications(self):
        reply = QMessageBox.question(
            self,
            "Отправить уведомления",
            "Отправить напоминания всем ответственным\nпо приборам с истекающим сроком поверки?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.side_panel.notify_btn.setEnabled(False)
        self.side_panel.notify_btn.setText("⏳  Отправка...")

        try:
            from core.notifier import check_and_notify
            result = check_and_notify(dry_run=False)
            QMessageBox.information(
                self,
                "Готово",
                f"✅ Отправлено:  {result['sent']}\n"
                f"⏭  Пропущено: {result['skipped']}\n"
                f"❌ Ошибок:    {result['errors']}\n\n"
                f"Приборов с истекающим сроком: {len(result['messages'])}",
            )
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))
        finally:
            self.side_panel.notify_btn.setEnabled(True)
            self.side_panel.notify_btn.setText("🔔  Уведомления")

    def on_export_excel(self):
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from datetime import datetime

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить журнал поверок",
            f"Журнал_поверок_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            "Excel Files (*.xlsx)",
        )
        if not path:
            return

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Журнал поверок"

        headers = ["ID", "Тип", "Инв. №", "Место", "Дата окончания", "Статус", "Ответственный"]
        header_font = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
        header_fill = PatternFill("solid", fgColor="1F3864")
        header_align = Alignment(horizontal="center", vertical="center")

        STATUS_COLORS_XL = {
            "green":   "C6EFCE",
            "yellow":  "FFEB9C",
            "red":     "FFC7CE",
            "no_data": "D9D9D9",
        }

        thin = Side(style="thin", color="000000")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)

        for c, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=c, value=h)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align
            cell.border = border

        ws.row_dimensions[1].height = 22

        devices = get_all_devices()
        type_f   = self.type_filter.currentText()
        status_f = self._status_from_filter()
        loc_f    = self.location_filter.currentText()
        resp_f   = self.responsible_filter.currentText()

        filtered = []
        for row in devices:
            if type_f != "Все" and row.get("type") != type_f:
                continue
            if status_f and row.get("status") != status_f:
                continue
            if loc_f != "Все" and row.get("location") != loc_f:
                continue
            if resp_f != "Все" and row.get("responsible_fio") != resp_f:
                continue
            filtered.append(row)

        for r, row in enumerate(filtered, 2):
            status = row.get("status") or "no_data"
            values = [
                row.get("id"),
                row.get("type") or "",
                row.get("inventory_number") or "",
                row.get("location") or "",
                row.get("expiry_date") or "",
                STATUS_LABELS.get(status, "Нет данных"),
                row.get("responsible_fio") or "",
            ]
            bg = STATUS_COLORS_XL.get(status, "FFFFFF")
            fill = PatternFill("solid", fgColor=bg)

            for c, val in enumerate(values, 1):
                cell = ws.cell(row=r, column=c, value=val)
                cell.fill = fill
                cell.border = border
                cell.alignment = Alignment(horizontal="center", vertical="center")
            ws.row_dimensions[r].height = 18

        col_widths = [6, 12, 16, 45, 16, 14, 25]
        for i, w in enumerate(col_widths, 1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

        wb.save(path)
        QMessageBox.information(
            self, "Экспорт завершён",
            f"Файл сохранён:\n{path}\n\nСтрок экспортировано: {len(filtered)}"
        )
