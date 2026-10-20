"""Общие элементы оформления существующих экранов."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QComboBox, QDateEdit, QStyledItemDelegate, QStyleOptionViewItem, QStyle


def icon(kind: str, color: str = "#798599") -> QIcon:
    """Небольшие векторные иконки без внешних файлов и шрифтовых символов."""
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(color), 1.7, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    if kind == "orders":
        painter.drawRoundedRect(QRectF(5, 4, 14, 17), 2, 2)
        for y in (9, 13, 17):
            painter.drawLine(9, y, 15, y)
    elif kind == "clients":
        painter.drawEllipse(QRectF(8, 3, 8, 8))
        path = QPainterPath(QPointF(4, 21))
        path.cubicTo(4, 11, 20, 11, 20, 21)
        painter.drawPath(path)
    elif kind == "car":
        painter.drawRoundedRect(QRectF(3, 10, 18, 9), 2, 2)
        painter.drawPolyline([QPointF(5, 10), QPointF(8, 5), QPointF(16, 5), QPointF(19, 10)])
        painter.drawLine(6, 19, 6, 21)
        painter.drawLine(18, 19, 18, 21)
        painter.drawLine(6, 14, 8, 14)
        painter.drawLine(16, 14, 18, 14)
    elif kind == "calendar":
        painter.drawRoundedRect(QRectF(4, 5, 16, 16), 2, 2)
        painter.drawLine(4, 10, 20, 10)
        painter.drawLine(8, 3, 8, 7)
        painter.drawLine(16, 3, 16, 7)
        painter.drawLine(8, 15, 10, 15)
        painter.drawLine(14, 15, 16, 15)
    elif kind == "services":
        for y in (6, 12, 18):
            painter.drawEllipse(QRectF(3, y - 1, 2, 2))
            painter.drawLine(9, y, 21, y)
    elif kind == "history":
        painter.drawArc(QRectF(4, 4, 16, 16), 40 * 16, 290 * 16)
        painter.drawLine(12, 7, 12, 12)
        painter.drawLine(12, 12, 16, 14)
        painter.drawLine(3, 4, 3, 9)
        painter.drawLine(3, 9, 8, 9)
    elif kind == "search":
        painter.drawEllipse(QRectF(4, 3, 12, 12))
        painter.drawLine(14, 14, 20, 20)
    elif kind == "plus":
        painter.drawLine(5, 12, 19, 12)
        painter.drawLine(12, 5, 12, 19)
    painter.end()
    return QIcon(pixmap)


class RowSelectionDelegate(QStyledItemDelegate):
    """Сохраняет клавиатурную навигацию, убирая рамку отдельной ячейки."""

    def paint(self, painter, option, index):
        clean = QStyleOptionViewItem(option)
        clean.state &= ~QStyle.StateFlag.State_HasFocus
        super().paint(painter, clean, index)


class OwnerComboBox(QComboBox):
    def paintEvent(self, event):
        super().paintEvent(event)
        paint_chevron(self)


class DateEdit(QDateEdit):
    def paintEvent(self, event):
        super().paintEvent(event)
        paint_chevron(self)


def paint_chevron(widget):
    painter = QPainter(widget)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor("#798599" if widget.isEnabled() else "#BAC3D0"), 1.5))
    x, y = widget.width() - 18, widget.height() // 2
    painter.drawPolyline([QPointF(x - 4, y - 2), QPointF(x, y + 2), QPointF(x + 4, y - 2)])
    painter.end()


