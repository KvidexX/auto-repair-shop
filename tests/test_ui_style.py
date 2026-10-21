"""Оформление popup, календаря и компоновки без изменения данных."""

import os
from pathlib import Path
import subprocess
import sys
import unittest

from PySide6.QtCore import QDate, QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QLabel, QTableView, QToolButton

from autoservice.appointments import AppointmentDialog
from autoservice.services import ServiceDialog
from autoservice.ui import DateEdit, LightCalendar, OwnerComboBox
from main import CarDialog, MainWindow, OrderDialog, STYLE
from tests import test_stage4 as helpers

ROOT = Path(__file__).resolve().parents[1]


def capture(window, filename, dialog=None, popup=None):
    """Снимок только собственных Qt-окон, без чужих окон рабочего стола."""
    image = window.grab()
    painter = QPainter(image)
    origin = window.mapToGlobal(QPoint(0, 0))
    for widget in (dialog, popup):
        if widget is not None:
            painter.drawPixmap(widget.mapToGlobal(QPoint(0, 0)) - origin, widget.grab())
    painter.end()
    assert image.save(str(ROOT / 'screenshots' / filename), 'PNG')


def scale_probe():
    app = QApplication([])
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)
    dialog = QDialog()
    dialog.resize(420, 200)
    combo = OwnerComboBox(dialog)
    combo.setGeometry(15, 120, 380, 38)
    combo.addItems([f'Клиент {i}' for i in range(100)])
    dialog.show()
    QTest.qWait(30)
    combo.showPopup()
    QTest.qWait(30)
    popup = combo.view().window()
    assert popup.isVisible()
    assert combo.screen().availableGeometry().contains(popup.frameGeometry()), (combo.screen().availableGeometry(), popup.frameGeometry())
    assert combo.view().sizeHintForRow(0) == 38
    combo.hidePopup()
    edit = DateEdit(dialog)
    edit.setGeometry(15, 20, 180, 38)
    edit.show()
    QTest.mouseClick(edit, Qt.MouseButton.LeftButton, pos=QPoint(edit.width() - 15, edit.height() // 2))
    QTest.qWait(30)
    calendar = edit.calendarWidget()
    assert calendar.screen().availableGeometry().contains(calendar.window().frameGeometry())
    app.closeAllWindows()


class UiStyleTests(unittest.TestCase):
    setUpClass = classmethod(helpers.ServicesTests.setUpClass.__func__)

    def setUp(self):
        self.palette = self.app.palette()
        self.window = MainWindow()
        self.window.centralWidget().setObjectName('central')
        self.window.show()
        QTest.qWait(20)

    def tearDown(self):
        self.app.closeAllWindows()
        self.app.setPalette(self.palette)

    def test_removed_labels_and_six_sections_have_more_work_space(self):
        banned = ('Учебный проект', 'Графический прототип', 'ДАННЫЕ SQLITE', 'ДЕМОНСТРАЦИОННЫЕ ДАННЫЕ', 'Рабочее место мастера-приёмщика', 'Изменения сохранены в SQLite', 'до закрытия приложения')
        for section in ('orders', 'clients', 'car', 'services', 'calendar', 'history'):
            self.window.show_section(section)
            text = ' '.join(label.text() for label in self.window.findChildren(QLabel))
            self.assertFalse(any(value in text for value in banned), text)
            self.assertEqual(self.window.pages.geometry().top(), 0)
            self.assertEqual((self.window.width(), self.window.height()), (1280, 720))
        self.assertIsNone(self.window.findChild(QLabel, 'sidebarFooter'))
        self.window.show_section('orders')
        capture(self.window, 'stage9_main.png')

    def test_all_existing_forms_use_common_combo_and_calendar(self):
        w = self.window
        forms = [CarDialog(w.clients, w.cars, w), ServiceDialog(w.services_page.services, w),
                 OrderDialog(w.clients, w.cars, w.services_page.services, w),
                 AppointmentDialog(w.clients, w.cars, w.appointments_page.appointments, w)]
        for form in forms:
            for combo in form.findChildren(QComboBox):
                self.assertIsInstance(combo, OwnerComboBox)
                self.assertEqual(combo.style().styleHint(combo.style().StyleHint.SH_ComboBox_Popup, None, combo), 0)
                self.assertEqual(combo.style().styleHint(combo.style().StyleHint.SH_ComboBox_UseNativePopup, None, combo), 0)
            for edit in form.findChildren(DateEdit):
                self.assertIsInstance(edit.calendarWidget(), LightCalendar)
        self.assertIsInstance(w.appointments_page.date_filter.calendarWidget(), LightCalendar)

    def test_short_long_popup_mouse_keyboard_and_scroll(self):
        combo = OwnerComboBox(self.window)
        combo.setGeometry(350, 80, 300, 38)
        combo.addItems(['Первый', 'Второй'])
        combo.show()
        combo.showPopup()
        QTest.qWait(30)
        self.assertLessEqual(combo.view().window().height(), 96)
        self.assertEqual(combo.view().sizeHintForRow(0), 38)
        point = combo.view().visualRect(combo.model().index(1, 0)).center()
        QTest.mouseMove(combo.view().viewport(), point)
        # SendInput/QCursor в фоновом Windows-тесте может не доставить move;
        # проверяем тот же mouse-move event непосредственно в viewport Qt.
        viewport = combo.view().viewport()
        event = QMouseEvent(QEvent.Type.MouseMove, QPointF(point), QPointF(viewport.mapToGlobal(point)),
                            Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(viewport, event)
        QTest.qWait(20)
        self.assertEqual(combo.view().currentIndex().row(), 1)
        self.assertEqual(combo.currentIndex(), 0)  # Наведение не подтверждает выбор.
        QTest.mouseClick(combo.view().viewport(), Qt.MouseButton.LeftButton, pos=point)
        self.assertEqual(combo.currentIndex(), 1)
        combo.clear()
        combo.addItems([f'Клиент {i}' for i in range(200)])
        combo.showPopup()
        QTest.qWait(30)
        self.assertLessEqual(combo.view().window().height(), 248)
        self.assertGreater(combo.view().verticalScrollBar().maximum(), 0)
        self.assertTrue(combo.screen().availableGeometry().contains(combo.view().window().frameGeometry()))
        QTest.keyClick(combo.view(), Qt.Key.Key_End)
        QTest.keyClick(combo.view(), Qt.Key.Key_Return)
        self.assertEqual(combo.currentIndex(), 199)

    def test_light_controls_under_dark_and_light_application_palettes(self):
        for background in ('#202020', '#FFFFFF'):
            palette = QPalette()
            palette.setColor(QPalette.ColorRole.Window, QColor(background))
            palette.setColor(QPalette.ColorRole.Base, QColor(background))
            palette.setColor(QPalette.ColorRole.Text, QColor('#FFFFFF' if background == '#202020' else '#202020'))
            self.app.setPalette(palette)
            combo = OwnerComboBox(self.window)
            calendar = LightCalendar(self.window)
            for widget in (combo, combo.view(), calendar):
                for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
                    self.assertEqual(widget.palette().color(group, QPalette.ColorRole.Base).name(), '#ffffff')
                    self.assertEqual(widget.palette().color(group, QPalette.ColorRole.Text).name(), '#344054')
            for name in ('qt_calendar_prevmonth', 'qt_calendar_nextmonth'):
                button = calendar.findChild(QToolButton, name)
                self.assertTrue(button.text())
            calendar.close()
            combo.close()

    def test_calendar_mouse_keyboard_and_screenshots(self):
        w = self.window
        dialog = AppointmentDialog(w.clients, w.cars, w.appointments_page.appointments, w)
        dialog.date_input.setDate(QDate(2026, 10, 15))
        dialog.show()
        QTest.qWait(30)
        edit = dialog.date_input
        QTest.mouseClick(edit, Qt.MouseButton.LeftButton, pos=QPoint(edit.width() - 15, edit.height() // 2))
        QTest.qWait(30)
        calendar = edit.calendarWidget()
        self.assertTrue(calendar.isVisible())
        self.assertTrue(calendar.screen().availableGeometry().contains(calendar.window().frameGeometry()))
        capture(w, 'stage9_calendar.png', dialog, calendar.window())
        view = calendar.findChild(QTableView, 'qt_calendar_calendarview')
        QTest.keyClick(view, Qt.Key.Key_Right)
        QTest.keyClick(view, Qt.Key.Key_Return)
        self.assertEqual(edit.date(), QDate(2026, 10, 16))
        QTest.mouseClick(edit, Qt.MouseButton.LeftButton, pos=QPoint(edit.width() - 15, edit.height() // 2))
        QTest.qWait(20)
        index = view.model().index(2, 2)
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=view.visualRect(index).center())
        self.assertNotEqual(edit.date(), QDate(2026, 10, 16))
        self.assertTrue(edit.date().isValid())

    def test_client_and_service_popup_screenshots(self):
        w = self.window
        dialog = OrderDialog(w.clients, w.cars, w.services_page.services, w)
        dialog.show()
        QTest.qWait(30)
        for combo, filename in ((dialog.client_input, 'stage9_clients_popup.png'), (dialog.service_input, 'stage9_services_popup.png')):
            combo.showPopup()
            QTest.qWait(30)
            self.assertTrue(combo.view().isVisible())
            capture(w, filename, dialog, combo.view().window())
            combo.hidePopup()

    def test_popup_screen_bounds_at_100_125_150_percent(self):
        for factor in ('1', '1.25', '1.5'):
            with self.subTest(factor=factor):
                environment = dict(os.environ, QT_SCALE_FACTOR=factor)
                result = subprocess.run([sys.executable, '-m', 'tests.test_ui_style', '--scale-probe'], cwd=ROOT,
                                        env=environment, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))


if __name__ == '__main__':
    if '--scale-probe' in sys.argv:
        scale_probe()
    else:
        unittest.main()
