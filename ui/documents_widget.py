import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from db.database import attach_document, delete_document, get_device_documents  # noqa: E402


class DocumentsWidget(QWidget):
    """
    Встраиваемый виджет для карточки прибора.
    Показывает список прикреплённых документов (PDF, JPG, PNG),
    позволяет добавлять и удалять.
    """

    def __init__(self, device_id: int, parent=None):
        super().__init__(parent)
        self.device_id = device_id
        self._build_ui()
        self._load()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        header = QHBoxLayout()
        lbl = QLabel("Документы (свидетельства о поверке):")
        lbl.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        btn_add = QPushButton("📎 Прикрепить")
        btn_add.setFixedWidth(110)
        btn_add.clicked.connect(self._attach)
        header.addWidget(lbl)
        header.addStretch()
        header.addWidget(btn_add)
        lay.addLayout(header)

        self.list_widget = QListWidget()
        self.list_widget.setMaximumHeight(120)
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.list_widget.itemDoubleClicked.connect(self._open_doc)
        lay.addWidget(self.list_widget)

        btn_row = QHBoxLayout()
        btn_open = QPushButton("🔍 Открыть")
        btn_open.clicked.connect(self._open_selected)
        btn_del = QPushButton("🗑 Удалить")
        btn_del.clicked.connect(self._delete_selected)
        btn_row.addWidget(btn_open)
        btn_row.addWidget(btn_del)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        hint = QLabel("Двойной клик — открыть файл")
        hint.setStyleSheet("color: grey; font-size: 9px;")
        lay.addWidget(hint)

        self._docs = []

    def _load(self):
        self.list_widget.clear()
        self._docs = get_device_documents(self.device_id)
        if not self._docs:
            item = QListWidgetItem("— нет прикреплённых документов —")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list_widget.addItem(item)
        else:
            for doc in self._docs:
                date_str = doc["uploaded_at"][:10] if doc.get("uploaded_at") else ""
                item = QListWidgetItem(f"📄 {doc['filename']}  [{date_str}]")
                item.setData(Qt.ItemDataRole.UserRole, doc["id"])
                self.list_widget.addItem(item)

    def _attach(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Выберите документы",
            "",
            "Документы (*.pdf *.jpg *.jpeg *.png *.tif *.tiff)",
        )
        for path in paths:
            try:
                attach_document(self.device_id, path)
            except Exception as e:
                QMessageBox.warning(self, "Ошибка", f"Не удалось прикрепить:\n{e}")
        self._load()

    def _open_doc(self, item: QListWidgetItem):
        doc_id = item.data(Qt.ItemDataRole.UserRole)
        if doc_id is None:
            return
        doc = next((d for d in self._docs if d["id"] == doc_id), None)
        if doc and os.path.exists(doc["filepath"]):
            os.startfile(doc["filepath"])
        else:
            QMessageBox.warning(self, "Файл не найден", "Файл не найден на диске.")

    def _open_selected(self):
        items = self.list_widget.selectedItems()
        if items:
            self._open_doc(items[0])

    def _delete_selected(self):
        items = self.list_widget.selectedItems()
        if not items:
            return
        doc_id = items[0].data(Qt.ItemDataRole.UserRole)
        if doc_id is None:
            return
        if (
            QMessageBox.question(
                self,
                "Удалить документ?",
                "Файл будет удалён с диска. Продолжить?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        ):
            delete_document(doc_id)
            self._load()
