import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.email_notifier import (
    ADMIN_EMAIL_KEY,
    SMTP_PRESETS,
    send_email_notifications,
    test_smtp,
)
from db.database import get_responsible_persons_rows, get_setting, set_responsible_person_email, set_setting


class _EmailSendThread(QThread):
    done = pyqtSignal(dict)

    def __init__(self, dry_run: bool = False):
        super().__init__()
        self.dry_run = dry_run

    def run(self):
        result = send_email_notifications(dry_run=self.dry_run)
        self.done.emit(result)


class EmailSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📨 Email-уведомления (SMTP)")
        self.setMinimumWidth(640)
        self._build_ui()
        self._load()

    def _build_ui(self):
        lay = QVBoxLayout(self)

        title = QLabel("📨 Настройки SMTP и рассылка по ответственным")
        title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)

        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Провайдер:"))
        self.combo_preset = QComboBox()
        self.combo_preset.addItems(list(SMTP_PRESETS.keys()))
        self.combo_preset.currentTextChanged.connect(self._on_preset)
        preset_row.addWidget(self.combo_preset)
        preset_row.addStretch()
        lay.addLayout(preset_row)

        form = QFormLayout()
        self.inp_host = QLineEdit()
        self.inp_port = QLineEdit()
        self.inp_port.setMaximumWidth(80)
        self.inp_ssl = QComboBox()
        self.inp_ssl.addItems(["SSL (465)", "STARTTLS (587)"])
        self.inp_login = QLineEdit()
        self.inp_pass = QLineEdit()
        self.inp_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp_from = QLineEdit()
        self.inp_from.setPlaceholderText("Как в «От:» (по умолчанию = логин)")
        self.inp_admin = QLineEdit()
        self.inp_admin.setPlaceholderText("Если у ответственного нет email — сюда")
        form.addRow("SMTP host:", self.inp_host)
        hp = QHBoxLayout()
        hp.addWidget(self.inp_port)
        hp.addWidget(QLabel("SSL:"))
        hp.addWidget(self.inp_ssl)
        hp.addStretch()
        w_hp = QWidget()
        w_hp.setLayout(hp)
        form.addRow("Порт / шифрование:", w_hp)
        form.addRow("Логин:", self.inp_login)
        form.addRow("Пароль приложения:", self.inp_pass)
        form.addRow("От (From):", self.inp_from)
        form.addRow("Email администратора (fallback):", self.inp_admin)
        lay.addLayout(form)

        note = QLabel(
            "⚠️  Для Mail.ru и Яндекс используйте отдельный «пароль приложения», "
            "не основной пароль аккаунта."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            "color: #7a4500; background: #fff3cd; border-radius: 4px; "
            "padding: 6px; font-size: 9px;"
        )
        lay.addWidget(note)

        row_btns = QHBoxLayout()
        btn_save_smtp = QPushButton("💾 Сохранить SMTP")
        btn_save_smtp.clicked.connect(self._save_smtp)
        btn_test = QPushButton("🔌 Тестовое письмо")
        btn_test.clicked.connect(self._test)
        row_btns.addWidget(btn_save_smtp)
        row_btns.addWidget(btn_test)
        lay.addLayout(row_btns)

        test_to = QHBoxLayout()
        test_to.addWidget(QLabel("Отправить тест на:"))
        self.inp_test_to = QLineEdit()
        self.inp_test_to.setPlaceholderText("email@example.com")
        test_to.addWidget(self.inp_test_to)
        lay.addLayout(test_to)

        lay.addWidget(QLabel("<b>Email ответственных</b> (из справочника):"))
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["ФИО", "Email"])
        self.table.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.table)

        row_em = QHBoxLayout()
        btn_save_emails = QPushButton("💾 Сохранить email в таблице")
        btn_save_emails.clicked.connect(self._save_emails_table)
        btn_send = QPushButton("📤 Рассылка сейчас (фон)")
        btn_send.clicked.connect(self._send_bulk)
        row_em.addWidget(btn_save_emails)
        row_em.addWidget(btn_send)
        lay.addLayout(row_em)

        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        lay.addWidget(self.lbl_status)

        btn_close = QPushButton("Закрыть")
        btn_close.clicked.connect(self.accept)
        lay.addWidget(btn_close)

    def _on_preset(self, name: str):
        p = SMTP_PRESETS.get(name, SMTP_PRESETS["Другой"])
        self.inp_host.setText(p["host"])
        self.inp_port.setText(str(p["port"]))
        self.inp_ssl.setCurrentIndex(0 if p["ssl"] else 1)

    def _load(self):
        self.inp_host.setText(get_setting("smtp_host"))
        self.inp_port.setText(get_setting("smtp_port", "465"))
        ssl_on = get_setting("smtp_ssl", "1") == "1"
        self.inp_ssl.setCurrentIndex(0 if ssl_on else 1)
        self.inp_login.setText(get_setting("smtp_login"))
        self.inp_pass.setText(get_setting("smtp_password"))
        self.inp_from.setText(get_setting("smtp_from"))
        self.inp_admin.setText(get_setting(ADMIN_EMAIL_KEY))
        self._reload_table()

    def _reload_table(self):
        rows = get_responsible_persons_rows()
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            fio = r.get("fio") or ""
            em = r.get("email") or ""
            self.table.setItem(i, 0, QTableWidgetItem(fio))
            self.table.item(i, 0).setFlags(
                Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
            )
            self.table.setItem(i, 1, QTableWidgetItem(em))

    def _save_smtp(self):
        set_setting("smtp_host", self.inp_host.text().strip())
        set_setting("smtp_port", self.inp_port.text().strip() or "465")
        set_setting("smtp_ssl", "1" if self.inp_ssl.currentIndex() == 0 else "0")
        set_setting("smtp_login", self.inp_login.text().strip())
        set_setting("smtp_password", self.inp_pass.text())
        set_setting("smtp_from", self.inp_from.text().strip())
        set_setting(ADMIN_EMAIL_KEY, self.inp_admin.text().strip())
        self.lbl_status.setText("✅ Настройки SMTP сохранены.")
        self.lbl_status.setStyleSheet("color: green;")

    def _save_emails_table(self):
        for row in range(self.table.rowCount()):
            fio_item = self.table.item(row, 0)
            em_item = self.table.item(row, 1)
            if not fio_item:
                continue
            fio = fio_item.text().strip()
            em = em_item.text().strip() if em_item else ""
            set_responsible_person_email(fio, em)
        self.lbl_status.setText("✅ Email ответственных сохранены.")
        self.lbl_status.setStyleSheet("color: green;")

    def _test(self):
        self._save_smtp()
        to_addr = self.inp_test_to.text().strip() or self.inp_admin.text().strip()
        if not to_addr:
            QMessageBox.warning(self, "Тест", "Укажите email для теста или fallback администратора.")
            return
        self.lbl_status.setText("Отправка теста...")
        self.lbl_status.setStyleSheet("color: grey;")
        result = test_smtp(to_addr)
        self.lbl_status.setText(result)
        self.lbl_status.setStyleSheet(
            "color: green;" if result.startswith("✅") else "color: red;"
        )

    def _send_bulk(self):
        self._save_smtp()
        self._save_emails_table()
        self.lbl_status.setText("Рассылка запущена в фоне...")
        self.lbl_status.setStyleSheet("color: grey;")
        self._thread = _EmailSendThread(dry_run=False)
        self._thread.done.connect(self._on_send_done)
        self._thread.start()

    def _on_send_done(self, result: dict):
        msg = (
            f"Готово: отправлено {result['sent']}, "
            f"пропущено {result['skipped']}, ошибок {result['errors']}"
        )
        self.lbl_status.setText(msg)
        self.lbl_status.setStyleSheet(
            "color: green;" if result["errors"] == 0 else "color: orange;"
        )
        QMessageBox.information(self, "Email-рассылка", msg)
