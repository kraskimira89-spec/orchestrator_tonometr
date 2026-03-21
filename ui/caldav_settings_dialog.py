import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog,
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

PROVIDER_HINTS = {
    "yandex": {
        "label": "Яндекс.Календарь",
        "url_hint": "https://caldav.yandex.ru/calendars/ВАШ_ЛОГИН/",
        "url_template": "https://caldav.yandex.ru/calendars/{login}/",
        "login_hint": "логин без @yandex.ru",
    },
    "mailru": {
        "label": "Mail.ru Календарь",
        "url_hint": "https://caldav.mail.ru/calendars/user@mail.ru/",
        "url_template": "https://caldav.mail.ru/calendars/{login}@mail.ru/",
        "login_hint": "логин@mail.ru",
    },
}


class _SyncThread(QThread):
    progress = pyqtSignal(int, int)
    done = pyqtSignal(dict)

    def __init__(self, provider: str):
        super().__init__()
        self.provider = provider

    def run(self):
        from core.calendar_sync import sync_all_devices

        result = sync_all_devices(
            provider=self.provider,
            progress_callback=lambda c, t: self.progress.emit(c, t),
        )
        self.done.emit(result)


class CalDAVSettingsDialog(QDialog):
    def __init__(self, provider: str = "yandex", parent=None):
        super().__init__(parent)
        self.provider = provider
        self._info = PROVIDER_HINTS.get(provider, PROVIDER_HINTS["yandex"])
        self._thread = None
        self.setWindowTitle(f"Авторизация — {self._info['label']}")
        self.setMinimumWidth(540)
        self._build_ui()
        self._load()

    def _build_ui(self):
        info = self._info
        lay = QVBoxLayout(self)

        title = QLabel(f"🔐 {info['label']}")
        title.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)

        hint = QLabel(
            f"Введите данные учётной записи {info['label']}.\n"
            "Пароль хранится только локально в БД приложения."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #555; font-size: 9px;")
        lay.addWidget(hint)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.inp_login = QLineEdit()
        self.inp_login.setPlaceholderText(info["login_hint"])
        self.inp_login.textChanged.connect(self._auto_url)

        self.inp_pass = QLineEdit()
        self.inp_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp_pass.setPlaceholderText("Пароль или пароль приложения")

        self.inp_url = QLineEdit()
        self.inp_url.setPlaceholderText(info["url_hint"])

        self.inp_cal = QLineEdit()
        self.inp_cal.setPlaceholderText("Оставьте пустым — первый календарь")

        form.addRow("Логин:", self.inp_login)
        form.addRow("Пароль:", self.inp_pass)
        form.addRow("CalDAV URL:", self.inp_url)
        form.addRow("Имя календаря:", self.inp_cal)
        lay.addLayout(form)

        note = QLabel(
            "⚠️ Яндекс и Mail.ru могут требовать пароль приложения вместо обычного пароля."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #b05800; font-size: 9px; padding: 4px;")
        lay.addWidget(note)

        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        lay.addWidget(self.lbl_status)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        lay.addWidget(self.progress)

        btn_row = QHBoxLayout()
        btn_test = QPushButton("🔌 Проверить соединение")
        btn_test.clicked.connect(self._test)
        btn_save = QPushButton("💾 Сохранить")
        btn_save.clicked.connect(self._save)
        btn_row.addWidget(btn_test)
        btn_row.addWidget(btn_save)
        lay.addLayout(btn_row)

        self.btn_sync = QPushButton("🔄 Синхронизировать все приборы")
        self.btn_sync.clicked.connect(self._sync_all)
        lay.addWidget(self.btn_sync)

        btn_close = QPushButton("Закрыть")
        btn_close.clicked.connect(self.accept)
        lay.addWidget(btn_close)

    def _auto_url(self, login: str):
        if not login or self.inp_url.text().strip():
            return
        login = login.strip()
        if self.provider == "mailru" and "@" in login:
            login = login.split("@")[0]
        if self.provider == "yandex" and "@" in login:
            login = login.split("@")[0]
        self.inp_url.setText(self._info["url_template"].replace("{login}", login))

    def _keys(self) -> tuple[str, str, str, str]:
        p = self.provider
        return (
            f"{p}_caldav_url",
            f"{p}_caldav_username",
            f"{p}_caldav_password",
            f"{p}_caldav_calendar",
        )

    def _load(self):
        k_url, k_user, k_pass, k_cal = self._keys()
        self.inp_login.setText(get_setting(k_user))
        self.inp_pass.setText(get_setting(k_pass))
        self.inp_url.setText(get_setting(k_url))
        self.inp_cal.setText(get_setting(k_cal))

    def _save(self):
        k_url, k_user, k_pass, k_cal = self._keys()
        set_setting(k_url, self.inp_url.text().strip())
        set_setting(k_user, self.inp_login.text().strip())
        set_setting(k_pass, self.inp_pass.text())
        set_setting(k_cal, self.inp_cal.text().strip())
        self.lbl_status.setText("✅ Настройки сохранены.")

    def _test(self):
        self._save()
        try:
            from core.calendar_sync import test_connection

            self.lbl_status.setText(test_connection(self.provider))
        except Exception as e:
            self.lbl_status.setText(f"❌ Ошибка: {e}")

    def _sync_all(self):
        self._save()
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.btn_sync.setEnabled(False)
        self._thread = _SyncThread(self.provider)
        self._thread.progress.connect(self._on_progress)
        self._thread.done.connect(self._on_sync_done)
        self._thread.start()

    def _on_progress(self, current: int, total: int):
        if total <= 0:
            self.progress.setRange(0, 0)
            return
        self.progress.setRange(0, 100)
        self.progress.setValue(int(current / total * 100))

    def _on_sync_done(self, result: dict):
        self.progress.setVisible(False)
        self.btn_sync.setEnabled(True)
        QMessageBox.information(
            self,
            "Синхронизация завершена",
            f"Синхронизировано: {result['synced']}\n"
            f"Пропущено (нет даты): {result['skipped']}\n"
            f"Ошибок: {result['errors']}",
        )
