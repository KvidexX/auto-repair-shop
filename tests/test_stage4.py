"""Основные сценарии каталога услуг через QtTest."""

import copy
from pathlib import Path
import unittest

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QTableWidget

from autoservice.data import SERVICES
from main import MainWindow, STYLE
from autoservice.services import ServiceDialog


class ServicesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.app.setFont(QFont("Segoe UI", 10))
        cls.app.setStyleSheet(STYLE)

    def setUp(self):
        self.window = MainWindow()
        self.window.centralWidget().setObjectName("central")
        self.window.show()
        self.window.show_section("services")
        QTest.qWait(30)
        self.page = self.window.services_page
        self.errors = []
        self.previous = copy.deepcopy((self.window.clients, self.window.cars, self.window.orders_page.orders))
        self.orders_table = self.window.pages.widget(0).findChild(QTableWidget)
        self.order_cells = self.read_orders()

    def read_orders(self):
        return [[self.orders_table.item(r, c).text() for c in range(6)] for r in range(7)]

    def tearDown(self):
        self.assertEqual((self.window.clients, self.window.cars, self.window.orders_page.orders), self.previous)
        self.assertEqual(self.read_orders(), self.order_cells)
        for widget in QApplication.topLevelWidgets():
            widget.close()
        self.assertFalse(self.errors, self.errors)

    def modal(self, action):
        def run():
            dialog = self.app.activeModalWidget()
            try:
                self.assertIsNotNone(dialog)
                action(dialog)
                if dialog.isVisible():
                    message = dialog.error.text() if hasattr(dialog, "error") else "Диалог не закрылся"
                    self.fail(message)
            except Exception as error:
                self.errors.append(error)
                if dialog:
                    dialog.reject()
        QTimer.singleShot(30, run)

    def fill(self, dialog):
        dialog.name_input.setText("  Проверка   освещения  ")
        dialog.category_input.setCurrentIndex(1)
        dialog.price_input.setText("0")

    def test_validation(self):
        for field, value, message in [
            ("name_input", " \t ", "наименование"),
            ("name_input", " компьютерная   ДИАГНОСТИКА ", "уже есть"),
            ("price_input", "", "Стоимость"), ("price_input", "-1", "Стоимость"),
            ("price_input", "1.5", "Стоимость"), ("price_input", "abc", "Стоимость"),
            ("duration_input", "0", "время"), ("duration_input", "-10", "время"),
            ("duration_input", "1.5", "время"),
        ]:
            with self.subTest(field=field, value=value):
                dialog = ServiceDialog(self.page.services, self.window)
                self.fill(dialog)
                getattr(dialog, field).setText(value)
                dialog.save_button.click()
                self.assertNotEqual(dialog.result(), QDialog.DialogCode.Accepted)
                self.assertIn(message, dialog.error.text())
        dialog = ServiceDialog(self.page.services, self.window)
        self.fill(dialog)
        dialog.category_input.setCurrentIndex(0)
        dialog.save_button.click()
        self.assertIn("категорию", dialog.error.text())
        dialog = ServiceDialog(self.page.services, self.window, self.page.services[0])
        dialog.save_button.click()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        dialog = ServiceDialog(self.page.services, self.window, self.page.services[1])
        dialog.name_input.setText(self.page.services[0]["name"])
        dialog.save_button.click()
        self.assertIn("уже есть", dialog.error.text())

    def test_crud_ids_cancel_and_double_click(self):
        p = self.page
        def add(dialog):
            self.fill(dialog)
            dialog.save_button.click()
        self.modal(add)
        p.add_button.click()
        service = p.selected_service()
        self.assertEqual(service["id"], 10)
        self.assertEqual(service["name"], "Проверка освещения")
        self.assertEqual(service["price"], 0)
        self.assertIs(type(service["price"]), int)
        self.assertIsNone(service["duration"])
        self.assertEqual(p.table.item(9, 3).text(), "—")
        self.assertEqual(p.total.text(), "10")
        def edit(dialog):
            self.assertEqual(dialog.price_input.text(), "0")
            dialog.name_input.setText("Проверка световых приборов")
            dialog.category_input.setCurrentIndex(3)
            dialog.price_input.setText("1250")
            dialog.duration_input.setText("25")
            dialog.description_input.setPlainText("Проверка фар и фонарей")
            dialog.save_button.click()
        self.modal(edit)
        cell = p.table.visualItemRect(p.table.item(9, 1)).center()
        QTest.mouseClick(p.table.viewport(), Qt.MouseButton.LeftButton, pos=cell)
        QTest.mouseDClick(p.table.viewport(), Qt.MouseButton.LeftButton, pos=cell)
        self.assertEqual(service["id"], 10)
        self.assertEqual(service["price"], 1250)
        self.assertEqual(service["duration"], 25)
        self.assertEqual(service["category"], "Ремонт")
        self.assertEqual(service["description"], "Проверка фар и фонарей")
        before = copy.deepcopy(p.services)
        def cancel(dialog):
            dialog.name_input.setText("Не сохранять")
            QTest.keyClick(dialog, Qt.Key.Key_Escape)
        self.modal(cancel)
        p.edit_button.click()
        self.modal(lambda d: d.cancel_button.click())
        p.add_button.click()
        self.assertEqual(p.services, before)
        def answer(dialog, text):
            self.assertIsInstance(dialog, QMessageBox)
            next(b for b in dialog.buttons() if b.text() == text).click()
        self.modal(lambda d: answer(d, "Отмена"))
        p.delete_button.click()
        self.assertEqual(p.services, before)
        self.modal(lambda d: answer(d, "Удалить"))
        p.delete_button.click()
        self.assertEqual(len(p.services), 9)
        self.assertEqual(p.total.text(), "9")
        self.modal(add)
        p.add_button.click()
        self.assertEqual(p.selected_service()["id"], 11)
        fresh = MainWindow()
        self.assertEqual(fresh.services_page.services, SERVICES)
        fresh.close()

    def test_search_layout_navigation_and_screenshots(self):
        w, p = self.window, self.page
        self.assertEqual((w.width(), w.height()), (1280, 720))
        self.assertEqual(p.table.horizontalScrollBar().maximum(), 0)
        for key, index in [("orders", 0), ("clients", 1), ("car", 2), ("services", 3)]:
            QTest.mouseClick(w.nav_buttons[key], Qt.MouseButton.LeftButton)
            self.assertEqual(w.pages.currentIndex(), index)
            self.assertEqual(w.nav_buttons[key].objectName(), "activeNav")
        self.assertTrue(w.nav_buttons["calendar"].isEnabled())
        self.assertTrue(w.nav_buttons["history"].isEnabled())
        for query, count in [("  ЗАМЕНА   МОТОРНОГО  ", 1), ("диагностика", 3),
                             ("техническое обслуживание", 4), ("ремонт", 2), ("нет такой услуги", 0)]:
            p.search.setText(query)
            self.assertEqual(p.table.rowCount(), count, query)
            self.assertEqual(p.total.text(), "9")
        self.assertTrue(p.empty.isVisible())
        self.assertFalse(p.edit_button.isEnabled())
        p.search.clear()
        p.table.selectRow(1)
        self.assertTrue(p.delete_button.isEnabled())
        w.show_section("clients")
        w.show_section("services")
        self.assertEqual(p.selected_service()["id"], 2)
        output = Path(__file__).resolve().parents[1] / "screenshots"
        output.mkdir(exist_ok=True)
        self.assertTrue(w.grab().save(str(output / "services.png"), "PNG"))
        dialog = ServiceDialog(p.services, w)
        dialog.show()
        QTest.qWait(40)
        self.assertLess(dialog.frameGeometry().height(), 680)
        self.assertTrue(w.frameGeometry().contains(dialog.frameGeometry()))
        self.assertTrue(dialog.rect().contains(dialog.save_button.geometry()))
        self.assertTrue(dialog.grab().save(str(output / "add_service.png"), "PNG"))
        dialog.reject()


if __name__ == "__main__":
    unittest.main()
