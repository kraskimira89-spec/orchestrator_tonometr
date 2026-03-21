import os
import sys

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QCursor, QColor, QPalette
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class _ResizeHandle(QWidget):
    """Полоска слева — тянем для изменения ширины панели."""

    def __init__(self, target: QWidget, parent=None):
        super().__init__(parent)
        self._target = target
        self._dragging = False
        self._start_x = 0
        self._start_w = 0
        self.setFixedWidth(5)
        self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
        self.setStyleSheet("background:#AAAAAA;")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._start_x = event.globalPosition().toPoint().x()
            self._start_w = self._target.width()

    def mouseMoveEvent(self, event):
        if self._dragging:
            dx = self._start_x - event.globalPosition().toPoint().x()
            new_w = max(160, min(500, self._start_w + dx))
            self._target.setFixedWidth(new_w)

    def mouseReleaseEvent(self, event):
        self._dragging = False


class _FloatWindow(QWidget):
    """Плавающее окно панели — отдельное, с видимым заголовком и рамкой."""

    def __init__(self, panel: "SidePanel", parent=None):
        super().__init__(
            parent,
            Qt.WindowType.Tool | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowCloseButtonHint
        )
        self.setWindowTitle("Действия")
        self.resize(220, 420)
        self._panel = panel

        # видимая рамка окна
        self.setStyleSheet("""
            QWidget {
                background: #F0F0F0;
                border: 2px solid #555555;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        btn_style = (
            "QPushButton {"
            "  text-align: left;"
            "  padding: 7px 10px;"
            "  border: 1px solid #999999;"
            "  border-radius: 4px;"
            "  background: #FFFFFF;"
            "  font-size: 10pt;"
            "}"
            "QPushButton:hover { background: #E0E0E0; }"
            "QPushButton:pressed { background: #C8C8C8; }"
        )

        lbl = QLabel("Поиск по столбцу:")
        lbl.setStyleSheet("border:none;")
        layout.addWidget(lbl)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Введите текст...")
        self.search_box.setStyleSheet("border: 1px solid #999; border-radius:3px; background:white;")
        self.search_box.textChanged.connect(panel.search_box.setText)
        panel.search_box.textChanged.connect(
            lambda t: self.search_box.setText(t) if self.search_box.text() != t else None
        )
        layout.addWidget(self.search_box)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet("border: 1px solid #AAAAAA;")
        layout.addWidget(sep)

        add_btn = QPushButton("➕  Добавить прибор")
        add_btn.setStyleSheet(btn_style)
        add_btn.setFixedHeight(40)
        add_btn.clicked.connect(panel.sig_add_device.emit)
        layout.addWidget(add_btn)

        notify_btn = QPushButton("🔔  Уведомления")
        notify_btn.setStyleSheet(btn_style)
        notify_btn.setFixedHeight(40)
        notify_btn.clicked.connect(panel.sig_notify.emit)
        layout.addWidget(notify_btn)

        export_btn = QPushButton("📥  Экспорт в Excel")
        export_btn.setStyleSheet(btn_style)
        export_btn.setFixedHeight(40)
        export_btn.clicked.connect(panel.sig_export.emit)
        layout.addWidget(export_btn)

        import_btn = QPushButton("📥  Импорт из Excel")
        import_btn.setStyleSheet(btn_style)
        import_btn.setFixedHeight(40)
        import_btn.clicked.connect(panel.sig_import_excel.emit)
        layout.addWidget(import_btn)

        resp_btn = QPushButton("👤  Ответственные")
        resp_btn.setStyleSheet(btn_style)
        resp_btn.setFixedHeight(40)
        resp_btn.clicked.connect(panel.sig_responsible.emit)
        layout.addWidget(resp_btn)

        dash_btn = QPushButton("📊  Статистика")
        dash_btn.setStyleSheet(btn_style)
        dash_btn.setFixedHeight(40)
        dash_btn.clicked.connect(panel.sig_dashboard.emit)
        layout.addWidget(dash_btn)

        cal_btn = QPushButton("📅  Синхр. календарь")
        cal_btn.setStyleSheet(btn_style)
        cal_btn.setFixedHeight(40)
        cal_btn.clicked.connect(panel.sig_caldav.emit)
        layout.addWidget(cal_btn)

        layout.addStretch()

        # кнопка «Прикрепить →» (стрелка вправо — прикрепляем обратно)
        dock_btn = QPushButton("▶  Прикрепить")
        dock_btn.setFixedHeight(36)
        dock_btn.setStyleSheet(
            "QPushButton { border:1px solid #888; border-radius:4px; "
            "background:#E8E8E8; font-weight:bold; }"
            "QPushButton:hover { background:#D0D0D0; }"
        )
        dock_btn.clicked.connect(self._dock_back)
        layout.addWidget(dock_btn)

    def _dock_back(self):
        self._panel._show_panel()
        self.close()

    def closeEvent(self, event):
        # при закрытии крестиком — тоже прикрепляем
        self._panel._show_panel()
        super().closeEvent(event)


class SidePanel(QWidget):
    """Правая боковая панель: прикреплённая / скрытая / плавающая."""

    sig_add_device = pyqtSignal()
    sig_notify     = pyqtSignal()
    sig_export     = pyqtSignal()
    sig_import_excel = pyqtSignal()
    sig_responsible = pyqtSignal()
    sig_dashboard = pyqtSignal()
    sig_caldav = pyqtSignal()

    DOCKED   = "docked"
    HIDDEN   = "hidden"
    FLOATING = "floating"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode = self.DOCKED
        self._float_win = None
        self._panel_width = 210

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._handle = _ResizeHandle(self, self)
        outer.addWidget(self._handle)

        self._content = QWidget()
        self._content.setMinimumWidth(160)
        self._content.setStyleSheet("background:#F5F5F5;")
        outer.addWidget(self._content, stretch=1)

        self._build_content(self._content)
        self.setFixedWidth(self._panel_width)

    def _build_content(self, parent: QWidget):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(8, 10, 8, 12)
        layout.setSpacing(8)

        # заголовок + кнопки управления
        title_row = QHBoxLayout()

        title = QLabel("Действия")
        f = QFont("Calibri", 10)
        f.setBold(True)
        title.setFont(f)
        title.setStyleSheet("background:transparent;")
        title_row.addWidget(title)
        title_row.addStretch()

        # кнопка «плавающая ⧉»
        self.btn_float = QPushButton("⧉")
        self.btn_float.setToolTip("Открепить (плавающее окно)")
        self.btn_float.setFixedSize(24, 24)
        self.btn_float.setFlat(True)
        self.btn_float.setStyleSheet(
            "QPushButton { font-size:13pt; border:none; background:transparent; }"
            "QPushButton:hover { background:#DDDDDD; border-radius:4px; }"
        )
        self.btn_float.clicked.connect(self._make_floating)
        title_row.addWidget(self.btn_float)

        # кнопка «скрыть ◀»
        self.btn_hide = QPushButton("◀")
        self.btn_hide.setToolTip("Скрыть панель")
        self.btn_hide.setFixedSize(24, 24)
        self.btn_hide.setFlat(True)
        self.btn_hide.setStyleSheet(
            "QPushButton { font-size:11pt; border:none; background:transparent; }"
            "QPushButton:hover { background:#DDDDDD; border-radius:4px; }"
        )
        self.btn_hide.clicked.connect(self._hide_panel)
        title_row.addWidget(self.btn_hide)

        layout.addLayout(title_row)

        sep0 = QFrame()
        sep0.setFrameShape(QFrame.Shape.HLine)
        sep0.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep0)

        # поиск
        lbl_search = QLabel("Поиск по столбцу:")
        lbl_search.setStyleSheet("background:transparent;")
        layout.addWidget(lbl_search)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Введите текст...")
        self.search_box.setStyleSheet(
            "border:1px solid #AAAAAA; border-radius:3px; "
            "background:white; padding:2px 4px;"
        )
        layout.addWidget(self.search_box)

        layout.addSpacing(4)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep1)

        layout.addSpacing(2)

        # стиль кнопок — без цветов, белый фон
        btn_style = (
            "QPushButton {"
            "  text-align: left;"
            "  padding: 7px 10px;"
            "  border: 1px solid #AAAAAA;"
            "  border-radius: 4px;"
            "  background: #FFFFFF;"
            "  font-size: 10pt;"
            "}"
            "QPushButton:hover { background: #E8E8E8; }"
            "QPushButton:pressed { background: #D0D0D0; }"
        )

        self.add_btn = QPushButton("➕  Добавить прибор")
        self.add_btn.setStyleSheet(btn_style)
        self.add_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.add_btn.setFixedHeight(40)
        self.add_btn.clicked.connect(self.sig_add_device.emit)
        layout.addWidget(self.add_btn)

        self.notify_btn = QPushButton("🔔  Уведомления")
        self.notify_btn.setStyleSheet(btn_style)
        self.notify_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.notify_btn.setFixedHeight(40)
        self.notify_btn.clicked.connect(self.sig_notify.emit)
        layout.addWidget(self.notify_btn)

        self.export_btn = QPushButton("📥  Экспорт в Excel")
        self.export_btn.setStyleSheet(btn_style)
        self.export_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.export_btn.setFixedHeight(40)
        self.export_btn.clicked.connect(self.sig_export.emit)
        layout.addWidget(self.export_btn)

        self.import_excel_btn = QPushButton("📥  Импорт из Excel")
        self.import_excel_btn.setStyleSheet(btn_style)
        self.import_excel_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.import_excel_btn.setFixedHeight(40)
        self.import_excel_btn.clicked.connect(self.sig_import_excel.emit)
        layout.addWidget(self.import_excel_btn)

        self.responsible_btn = QPushButton("👤  Ответственные")
        self.responsible_btn.setStyleSheet(btn_style)
        self.responsible_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.responsible_btn.setFixedHeight(40)
        self.responsible_btn.clicked.connect(self.sig_responsible.emit)
        layout.addWidget(self.responsible_btn)

        self.dashboard_btn = QPushButton("📊  Статистика")
        self.dashboard_btn.setStyleSheet(btn_style)
        self.dashboard_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.dashboard_btn.setFixedHeight(40)
        self.dashboard_btn.clicked.connect(self.sig_dashboard.emit)
        layout.addWidget(self.dashboard_btn)

        self.caldav_btn = QPushButton("📅  Синхр. календарь")
        self.caldav_btn.setStyleSheet(btn_style)
        self.caldav_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.caldav_btn.setFixedHeight(40)
        self.caldav_btn.clicked.connect(self.sig_caldav.emit)
        layout.addWidget(self.caldav_btn)

        layout.addSpacing(4)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep2)

        # счётчик
        self.counter_label = QLabel("Всего: —")
        self.counter_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.counter_label.setWordWrap(True)
        self.counter_label.setStyleSheet(
            "color:#444; font-size:9pt; padding-top:4px; background:transparent;"
        )
        layout.addWidget(self.counter_label)

        layout.addStretch()

        ver = QLabel("v0.2.0 · Спринт 2")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver.setStyleSheet("color:#AAAAAA; font-size:8pt; background:transparent;")
        layout.addWidget(ver)

    def update_counter(self, total, green, yellow, red):
        self.counter_label.setText(
            f"Всего: {total}\n"
            f"🟢 В норме: {green}\n"
            f"🟡 Скоро: {yellow}\n"
            f"🔴 Просрочено: {red}"
        )

    # ── кнопка «показать» при скрытой панели ─────────────────────────────
    def _ensure_show_btn(self):
        if not hasattr(self, "_show_btn"):
            self._show_btn = QPushButton("▶", self)
            self._show_btn.setFixedSize(22, 70)
            self._show_btn.setToolTip("Показать панель")
            self._show_btn.setStyleSheet(
                "QPushButton { border:1px solid #AAAAAA; border-radius:3px; "
                "background:#E0E0E0; font-size:13pt; color:#333; }"
                "QPushButton:hover { background:#C8C8C8; }"
            )
            self._show_btn.clicked.connect(self._show_panel)
        self._show_btn.move(1, max(0, (self.height() - 70) // 2))
        self._show_btn.show()

    def _hide_panel(self):
        self._mode = self.HIDDEN
        self._content.hide()
        self._handle.hide()
        self.setFixedWidth(24)
        self._ensure_show_btn()

    def _show_panel(self):
        self._mode = self.DOCKED
        self._content.show()
        self._handle.show()
        self.setFixedWidth(self._panel_width)
        if hasattr(self, "_show_btn"):
            self._show_btn.hide()
        if self._float_win:
            self._float_win.close()
            self._float_win = None

    def _make_floating(self):
        self._mode = self.FLOATING
        self._content.hide()
        self._handle.hide()
        self.setFixedWidth(24)
        self._ensure_show_btn()
        self._float_win = _FloatWindow(self, self.window())
        self._float_win.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_show_btn") and self._show_btn.isVisible():
            self._show_btn.move(1, max(0, (self.height() - 70) // 2))
