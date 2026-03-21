import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from db.database import get_setting, set_setting  # noqa: E402
from core.calendar_sync import sync_all_devices, test_connection  # noqa: E402

PRESETS = {
    "Mail.ru": "https://caldav.mail.ru/calendars/{login}@mail.ru/",
    "Яндекс": "https://caldav.yandex.ru/calendars/{login}/",
    "Другой": "",
}


class _SyncThread(QThread):
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(dict)

    def run(self):
        result = sync_all_devices(
            progress_callback=lambda c, t: self.progress.emit(c, t),
        )
        self.finished.emit(result)


class CalDAVSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки CalDAV-календаря")
        self.setMinimumWidth(520)
        self._sync_thread = None
        self._build_ui()
        self._load()

    def _build_ui(self):
        lay = QVBoxLayout(self)

        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Провайдер:"))
        self.combo_preset = QComboBox()
        self.combo_preset.addItems(list(PRESETS.keys()))
        self.combo_preset.currentTextChanged.connect(self._on_preset)
        preset_row.addWidget(self.combo_preset)
        preset_row.addStretch()
        lay.addLayout(preset_row)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.inp_url = QLineEdit()
        self.inp_url.setPlaceholderText("https://caldav.mail.ru/calendars/user@mail.ru/")
        self.inp_user = QLineEdit()
        self.inp_user.setPlaceholderText("user@mail.ru")
        self.inp_user.textChanged.connect(self._maybe_fill_preset_url)
        self.inp_pass = QLineEdit()
        self.inp_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp_cal = QLineEdit()
        self.inp_cal.setPlaceholderText("Пусто — первый доступный календарь")

        form.addRow("CalDAV URL:", self.inp_url)
        form.addRow("Логин:", self.inp_user)
        form.addRow("Пароль:", self.inp_pass)
        form.addRow("Имя календаря:", self.inp_cal)
        lay.addLayout(form)

        hint = QLabel(
            "Mail.ru: https://caldav.mail.ru/calendars/ВАШ_ЛОГИН@mail.ru/\n"
            "Яндекс: https://caldav.yandex.ru/calendars/ВАШ_ЛОГИН/"
        )
        hfont = QFont()
        hfont.setPointSize(9)
        hint.setFont(hfont)
        hint.setStyleSheet("color: grey;")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        btn_row = QHBoxLayout()
        btn_test = QPushButton("🔌 Проверить соединение")
        btn_test.clicked.connect(self._test)
        self.btn_sync = QPushButton("📅 Синхронизировать все приборы")
        self.btn_sync.clicked.connect(self._sync)
        btn_save = QPushButton("💾 Сохранить настройки")
        btn_save.clicked.connect(self._save)
        btn_row.addWidget(btn_test)
        btn_row.addWidget(self.btn_sync)
        btn_row.addWidget(btn_save)
        lay.addLayout(btn_row)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        lay.addWidget(self.progress)

        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        box.rejected.connect(self.reject)
        box.button(QDialogButtonBox.StandardButton.Close).setText("Закрыть")
        lay.addWidget(box)

    def _load(self):
        self.combo_preset.blockSignals(True)
        preset = get_setting("caldav_preset", "Другой")
        idx = self.combo_preset.findText(preset)
        if idx >= 0:
            self.combo_preset.setCurrentIndex(idx)
        self.combo_preset.blockSignals(False)
        self.inp_url.setText(get_setting("caldav_url"))
        self.inp_user.setText(get_setting("caldav_username"))
        self.inp_pass.setText(get_setting("caldav_password"))
        self.inp_cal.setText(get_setting("caldav_calendar"))

    def _persist_from_form(self):
        set_setting("caldav_preset", self.combo_preset.currentText())
        set_setting("caldav_url", self.inp_url.text().strip())
        set_setting("caldav_username", self.inp_user.text().strip())
        set_setting("caldav_password", self.inp_pass.text())
        set_setting("caldav_calendar", self.inp_cal.text().strip())

    def _login_for_preset(self, login: str, preset_name: str) -> str:
        login = login.strip()
        if preset_name == "Mail.ru" and "@" in login:
            return login.split("@")[0]
        return login

    def _on_preset(self, name: str):
        tmpl = PRESETS.get(name, "")
        if not tmpl:
            return
        login = self.inp_user.text().strip()
        if login:
            self.inp_url.setText(tmpl.format(login=self._login_for_preset(login, name)))

    def _maybe_fill_preset_url(self):
        name = self.combo_preset.currentText()
        tmpl = PRESETS.get(name, "")
        if not tmpl:
            return
        login = self.inp_user.text().strip()
        if not login:
            return
        self.inp_url.setText(tmpl.format(login=self._login_for_preset(login, name)))

    def _test(self):
        self._persist_from_form()
        r = test_connection()
        QMessageBox.information(self, "Проверка соединения", r)

    def _save(self):
        self._persist_from_form()
        QMessageBox.information(self, "Сохранено", "Настройки CalDAV сохранены в базе.")

    def _sync(self):
        self._persist_from_form()
        self.btn_sync.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)

        self._sync_thread = _SyncThread()
        self._sync_thread.progress.connect(self._on_sync_progress)
        self._sync_thread.finished.connect(self._on_sync_finished)
        self._sync_thread.start()

    def _on_sync_progress(self, current: int, total: int):
        if total <= 0:
            return
        self.progress.setRange(0, total)
        self.progress.setValue(current)

    def _on_sync_finished(self, result: dict):
        self.progress.setVisible(False)
        self.btn_sync.setEnabled(True)
        QMessageBox.information(
            self,
            "Синхронизация",
            f"Готово.\nСинхронизировано: {result.get('synced', 0)}\n"
            f"Пропущено (нет даты): {result.get('skipped', 0)}\n"
            f"Ошибок: {result.get('errors', 0)}",
        )
