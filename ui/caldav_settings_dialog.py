import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QPushButton,
    QLabel,
    QHBoxLayout,
    QProgressBar,
    QMessageBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

from db.database import get_setting, set_setting
from core.calendar_sync import test_connection, sync_all_devices


PROVIDERS = {
    "yandex": {
        "label": "Яндекс.Календарь",
        "icon": "🟡",
        "url_tmpl": "https://caldav.yandex.ru/calendars/{login}/",
        "login_ph": "логин (без @yandex.ru)",
        "pass_note": (
            "Яндекс требует «пароль приложения» вместо основного.\n"
            "Создайте его: passport.yandex.ru → Безопасность → Пароли приложений."
        ),
    },
    "mailru": {
        "label": "Mail.ru Календарь",
        "icon": "📧",
        "url_tmpl": "https://caldav.mail.ru/calendars/{login}@mail.ru/",
        "login_ph": "логин@mail.ru",
        "pass_note": (
            "Mail.ru требует «пароль для внешних приложений».\n"
            "Создайте его: account.mail.ru → Безопасность → Пароли для приложений."
        ),
    },
}


class _SyncThread(QThread):
    progress = pyqtSignal(int, int)
    done = pyqtSignal(dict)

    def __init__(self, provider: str):
        super().__init__()
        self.provider = provider

    def run(self):
        result = sync_all_devices(
            provider=self.provider,
            progress_callback=lambda c, t: self.progress.emit(c, t),
        )
        self.done.emit(result)


class CalDAVSettingsDialog(QDialog):
    def __init__(self, provider: str = "yandex", parent=None):
        super().__init__(parent)
        self.provider = provider
        info = PROVIDERS.get(provider, PROVIDERS["yandex"])
        self.setWindowTitle(f"{info['icon']} Авторизация — {info['label']}")
        self.setMinimumWidth(560)
        self._info = info
        self._build_ui()
        self._load()

    def _build_ui(self):
        info = self._info
        lay = QVBoxLayout(self)

        title = QLabel(f"{info['icon']} {info['label']}")
        title.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.inp_login = QLineEdit()
        self.inp_login.setPlaceholderText(info["login_ph"])
        self.inp_login.textChanged.connect(self._auto_url)

        self.inp_pass = QLineEdit()
        self.inp_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp_pass.setPlaceholderText("Пароль приложения")

        self.inp_url = QLineEdit()
        self.inp_url.setPlaceholderText(info["url_tmpl"].replace("{login}", "ВАШ_ЛОГИН"))

        self.inp_cal = QLineEdit()
        self.inp_cal.setPlaceholderText("Оставьте пустым — использовать первый календарь")

        form.addRow("Логин:", self.inp_login)
        form.addRow("Пароль приложения:", self.inp_pass)
        form.addRow("CalDAV URL:", self.inp_url)
        form.addRow("Имя календаря:", self.inp_cal)
        lay.addLayout(form)

        note = QLabel(f"⚠️  {info['pass_note']}")
        note.setWordWrap(True)
        note.setStyleSheet(
            "color: #7a4500; background: #fff3cd; "
            "border-radius: 4px; padding: 6px; font-size: 9px;"
        )
        lay.addWidget(note)

        remind_info = QLabel(
            "📅  В календарь будут добавлены напоминания:\n"
            "     за 2 месяца (60 дней) · за 1 месяц (30 дней) · "
            "за 1 неделю (7 дней) · за 2 дня"
        )
        remind_info.setWordWrap(True)
        remind_info.setStyleSheet(
            "color: #0a4a00; background: #d4edda; "
            "border-radius: 4px; padding: 6px; font-size: 9px;"
        )
        lay.addWidget(remind_info)

        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        lay.addWidget(self.lbl_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        lay.addWidget(self.progress_bar)

        row1 = QHBoxLayout()
        btn_test = QPushButton("🔌 Проверить соединение")
        btn_test.clicked.connect(self._test)
        btn_save = QPushButton("💾 Сохранить")
        btn_save.clicked.connect(self._save)
        row1.addWidget(btn_test)
        row1.addWidget(btn_save)
        lay.addLayout(row1)

        btn_sync = QPushButton("🔄 Синхронизировать все приборы в календарь")
        btn_sync.clicked.connect(self._sync_all)
        lay.addWidget(btn_sync)

        btn_close = QPushButton("Закрыть")
        btn_close.clicked.connect(self.accept)
        lay.addWidget(btn_close)

    def _auto_url(self, login: str):
        if login and not self.inp_url.text().strip():
            tmpl = self._info["url_tmpl"]
            self.inp_url.setText(tmpl.replace("{login}", login))

    def _load(self):
        p = self.provider
        self.inp_login.setText(get_setting(f"{p}_caldav_username"))
        self.inp_pass.setText(get_setting(f"{p}_caldav_password"))
        self.inp_url.setText(get_setting(f"{p}_caldav_url"))
        self.inp_cal.setText(get_setting(f"{p}_caldav_calendar"))

    def _save(self):
        p = self.provider
        set_setting(f"{p}_caldav_url", self.inp_url.text().strip())
        set_setting(f"{p}_caldav_username", self.inp_login.text().strip())
        set_setting(f"{p}_caldav_password", self.inp_pass.text())
        set_setting(f"{p}_caldav_calendar", self.inp_cal.text().strip())
        self.lbl_status.setText("✅ Настройки сохранены.")
        self.lbl_status.setStyleSheet("color: green;")

    def _test(self):
        self._save()
        self.lbl_status.setText("Проверяю соединение...")
        self.lbl_status.setStyleSheet("color: grey;")
        result = test_connection(self.provider)
        self.lbl_status.setText(result)
        color = "green" if result.startswith("✅") else "red"
        self.lbl_status.setStyleSheet(f"color: {color};")

    def _sync_all(self):
        self._save()
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.lbl_status.setText("Синхронизация запущена...")
        self.lbl_status.setStyleSheet("color: grey;")

        self._thread = _SyncThread(self.provider)
        self._thread.progress.connect(
            lambda c, t: self.progress_bar.setValue(int(c / t * 100) if t else 0)
        )
        self._thread.done.connect(self._on_sync_done)
        self._thread.start()

    def _on_sync_done(self, result: dict):
        self.progress_bar.setVisible(False)
        msg = (
            f"✅ Готово: синхронизировано {result['synced']}, "
            f"пропущено {result['skipped']}, ошибок {result['errors']}"
        )
        self.lbl_status.setText(msg)
        color = "green" if result["errors"] == 0 else "orange"
        self.lbl_status.setStyleSheet(f"color: {color};")

        if result["errors"]:
            QMessageBox.warning(
                self,
                "Синхронизация завершена с ошибками",
                f"Синхронизировано: {result['synced']}\n"
                f"Пропущено (нет даты):  {result['skipped']}\n"
                f"Ошибок: {result['errors']}\n\n"
                "Проверьте консоль (python main.py) для деталей.",
            )
        else:
            QMessageBox.information(
                self,
                "Синхронизация завершена",
                f"Все приборы синхронизированы с {self._info['label']}.\n\n"
                f"Синхронизировано: {result['synced']}\n"
                f"Пропущено (нет даты): {result['skipped']}",
            )
