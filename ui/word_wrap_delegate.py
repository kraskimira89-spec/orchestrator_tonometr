"""Делегат отрисовки ячеек с переносом текста по словам (как в Excel)."""

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QTextDocument
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QStyledItemDelegate,
    QStyle,
    QStyleOptionViewItem,
)


class WordWrapDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text or ""
        if not text:
            super().paint(painter, option, index)
            return

        painter.save()
        style = QApplication.style()
        style.drawPrimitive(
            QStyle.PrimitiveElement.PE_PanelItemViewItem,
            opt,
            painter,
            opt.widget,
        )
        doc = QTextDocument()
        doc.setPlainText(text)
        doc.setDefaultFont(opt.font)
        # После translate() координаты локальные; clip в абсолютных opt.rect обрезал весь текст
        rw = max(20, opt.rect.width() - 8)
        rh = max(1, opt.rect.height() - 8)
        doc.setTextWidth(rw)

        painter.translate(opt.rect.left() + 4, opt.rect.top() + 4)
        painter.setClipRect(0, 0, rw, rh)
        doc.drawContents(painter)
        painter.restore()

    def sizeHint(self, option, index):
        text = index.data(Qt.ItemDataRole.DisplayRole)
        if text is None:
            text = ""
        text = str(text)
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        doc = QTextDocument()
        doc.setPlainText(text)
        doc.setDefaultFont(opt.font)
        w = max(80, option.rect.width() if option.rect.width() > 0 else 120)
        doc.setTextWidth(w)
        h = doc.size().height()
        return QSize(int(w + 8), max(26, int(h) + 12))


class LocationComboDelegate(QStyledItemDelegate):
    """Одна строка + выпадающий список мест (без переноса, как в Excel)."""

    def createEditor(self, parent, option, index):
        cb = QComboBox(parent)
        cb.setEditable(True)
        items = index.data(Qt.ItemDataRole.UserRole)
        if items:
            for s in items:
                cb.addItem(str(s))
        return cb

    def setEditorData(self, editor, index):
        if isinstance(editor, QComboBox):
            txt = index.data(Qt.ItemDataRole.EditRole)
            if txt is None:
                txt = index.data(Qt.ItemDataRole.DisplayRole)
            editor.setCurrentText("" if txt is None else str(txt))

    def setModelData(self, editor, model, index):
        if isinstance(editor, QComboBox):
            model.setData(index, editor.currentText().strip(), Qt.ItemDataRole.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        r = option.rect
        h = min(28, max(22, r.height()))
        editor.setGeometry(r.left(), r.top(), r.width(), h)
