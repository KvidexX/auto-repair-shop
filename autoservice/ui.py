"""Общие элементы оформления существующих экранов."""

from PySide6.QtCore import QDate, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPalette, QTextCharFormat
from PySide6.QtWidgets import (
    QCalendarWidget, QComboBox, QDateEdit, QListView, QProxyStyle, QStyleFactory,
    QStyledItemDelegate, QStyleOptionViewItem, QStyle, QToolButton, QWidget,
)


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


def light_palette():
    palette = QPalette()
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive, QPalette.ColorGroup.Disabled):
        for role, color in {
            QPalette.ColorRole.Window: '#FFFFFF', QPalette.ColorRole.Base: '#FFFFFF',
            QPalette.ColorRole.AlternateBase: '#F8FAFC', QPalette.ColorRole.Button: '#FFFFFF',
            QPalette.ColorRole.Text: '#344054', QPalette.ColorRole.WindowText: '#344054',
            QPalette.ColorRole.ButtonText: '#344054', QPalette.ColorRole.Highlight: '#DFE9FF',
            QPalette.ColorRole.HighlightedText: '#294F91',
            QPalette.ColorRole.Light: '#FFFFFF', QPalette.ColorRole.Midlight: '#F8FAFC',
            QPalette.ColorRole.Mid: '#F8FAFC', QPalette.ColorRole.Dark: '#F8FAFC',
            QPalette.ColorRole.Shadow: '#DDE3EC',
            QPalette.ColorRole.ToolTipBase: '#FFFFFF', QPalette.ColorRole.ToolTipText: '#344054',
            QPalette.ColorRole.Link: '#3767B2', QPalette.ColorRole.LinkVisited: '#294F91',
            QPalette.ColorRole.BrightText: '#FFFFFF', QPalette.ColorRole.PlaceholderText: '#818B9C',
            QPalette.ColorRole.Accent: '#3767B2',
        }.items():
            palette.setColor(group, role, QColor(color))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor('#98A2B3'))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor('#818B9C'))
    return palette


def apply_light_theme(app):
    """Одна тема для SQLite, demo и снимков, включая Qt popup-окна Windows."""
    app.setStyle('Fusion')
    app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    app.setPalette(light_palette())
    if not getattr(app, '_light_theme_fixed', False):
        def restore_palette(palette):
            if palette != light_palette():
                app.setPalette(light_palette())
        app.paletteChanged.connect(restore_palette)
        app._light_theme_fixed = True


class ComboStyle(QProxyStyle):
    def styleHint(self, hint, option=None, widget=None, returnData=None):
        if hint == QStyle.StyleHint.SH_ComboBox_UseNativePopup:
            return 0  # QListView, без нативного Windows/macOS menu popup.
        return super().styleHint(hint, option, widget, returnData)


class ComboItemDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        return QSize(option.fontMetrics.horizontalAdvance(str(index.data() or '')) + 28, 38)

    def paint(self, painter, option, index):
        painter.save()
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        painter.fillRect(option.rect, QColor('#DFE9FF' if selected else '#EEF3FC' if hovered else '#FFFFFF'))
        painter.setPen(QColor('#294F91' if selected else '#344054'))
        painter.setFont(option.font)
        rect = option.rect.adjusted(12, 0, -12, 0)
        text = option.fontMetrics.elidedText(str(index.data() or ''), Qt.TextElideMode.ElideRight, rect.width())
        painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        painter.restore()


class OwnerComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._popup_style = ComboStyle(QStyleFactory.create('Fusion'))
        self._popup_style.setParent(self)
        self.setStyle(self._popup_style)
        self.setPalette(light_palette())
        view = QListView(self)
        view.setObjectName('comboList')
        view.setStyle(self._popup_style)
        view.setPalette(light_palette())
        view.setMouseTracking(True)
        view.setUniformItemSizes(True)
        view.setItemDelegate(ComboItemDelegate(view))
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        view.entered.connect(view.setCurrentIndex)
        view.setStyleSheet('QListView { background: #FFFFFF; color: #344054; border: none; outline: none; padding: 0; }')
        self.setView(view)
        self.setMaxVisibleItems(6)

    def showPopup(self):
        available = self.screen().availableGeometry()
        rows = min(max(self.count(), 1), 6, max(1, (available.height() - 40) // 38))
        self.setMaxVisibleItems(rows)
        self.view().setMaximumHeight(rows * 38)
        popup = self.view().window()
        # На Windows Qt stylesheet может рассчитывать контейнер по всему
        # списку даже при maxVisibleItems; ограничиваем и само popup-окно.
        popup.setMaximumHeight(rows * 38 + 20)
        popup.setObjectName('comboPopup')
        popup.setPalette(light_palette())
        popup.setStyleSheet('QFrame#comboPopup { background: #FFFFFF; border: 1px solid #DDE3EC; border-radius: 6px; padding: 3px; }')
        # Qt stylesheet включает menu-scroller даже у QListView. Используем
        # обычную полосу прокрутки, без системных тёмных стрелочных полос.
        for child in popup.findChildren(QWidget):
            if child.metaObject().className() == 'QComboBoxPrivateScroller':
                child.setFixedHeight(0)
                child.hide()
        super().showPopup()
        self.view().setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    def paintEvent(self, event):
        super().paintEvent(event)
        paint_chevron(self)


class LightCalendar(QCalendarWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._calendar_style = QStyleFactory.create('Fusion')
        self._calendar_style.setParent(self)
        self.setStyle(self._calendar_style)
        self.setPalette(light_palette())
        self.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.setGridVisible(False)
        header = QTextCharFormat()
        header.setForeground(QColor('#526278'))
        header.setBackground(QColor('#F8FAFC'))
        self.setHeaderTextFormat(header)
        weekend = QTextCharFormat()
        weekend.setForeground(QColor('#526278'))
        for day in (Qt.DayOfWeek.Saturday, Qt.DayOfWeek.Sunday):
            self.setWeekdayTextFormat(day, weekend)
        self.setStyleSheet('''
            QCalendarWidget { background: #FFFFFF; color: #344054; }
            QCalendarWidget QWidget#qt_calendar_navigationbar { background: #F8FAFC; }
            QCalendarWidget QToolButton { background: #F8FAFC; color: #344054; border: none;
                border-radius: 5px; padding: 6px; min-height: 24px; }
            QCalendarWidget QToolButton:hover { background: #EBF1FD; }
            QCalendarWidget QAbstractItemView { background: #FFFFFF; color: #344054;
                selection-background-color: #DFE9FF; selection-color: #294F91; outline: none; border: none; }
            QCalendarWidget QSpinBox { background: #FFFFFF; color: #344054; border: 1px solid #DDE3EC; }
            QCalendarWidget QMenu { background: #FFFFFF; color: #344054; border: 1px solid #DDE3EC; }
            QCalendarWidget QMenu::item { padding: 7px 14px; }
            QCalendarWidget QMenu::item:selected { background: #DFE9FF; color: #294F91; }
        ''')
        for name, text in [('qt_calendar_prevmonth', '‹'), ('qt_calendar_nextmonth', '›')]:
            button = self.findChild(QToolButton, name)
            button.setIcon(QIcon())
            button.setText(text)

    def paintCell(self, painter, rect, day):
        painter.save()
        painter.fillRect(rect, QColor('#FFFFFF'))
        selected = day == self.selectedDate()
        enabled = self.minimumDate() <= day <= self.maximumDate()
        current_month = day.month() == self.monthShown()
        area = QRectF(rect.adjusted(2, 2, -2, -2))
        if selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor('#DFE9FF'))
            painter.drawRoundedRect(area, 5, 5)
        if day == QDate.currentDate():
            painter.setPen(QPen(QColor('#7396DF'), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(area, 5, 5)
        color = '#98A2B3' if not enabled or not current_month else '#294F91' if selected else '#344054'
        painter.setPen(QColor(color))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(day.day()))
        painter.restore()


class DateEdit(QDateEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCalendarPopup(True)
        self.setCalendarWidget(LightCalendar(self))

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


