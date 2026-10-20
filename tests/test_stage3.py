"""Проверки Qt-интерфейса: python -m unittest -v tests.test_stage3."""

import copy
from datetime import date
from pathlib import Path
import unittest

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QTableWidget

from autoservice.data import CLIENTS, CARS, normalize_plate
from main import MainWindow, CarDialog, ClientDialog, RowSelectionDelegate, STYLE


class PrototypeTests(unittest.TestCase):
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
        self.window.show_section("car")
        QTest.qWait(30)
        self.modal_errors = []
        self.original_orders = copy.deepcopy(self.window.orders_page.orders)
        self.order_table = self.window.pages.widget(0).findChild(QTableWidget)
        self.original_order_cells = self.order_cells()

    def tearDown(self):
        self.assertEqual(self.window.orders_page.orders, self.original_orders)
        self.assertEqual(self.order_cells(), self.original_order_cells)
        for widget in QApplication.topLevelWidgets():
            widget.close()
        self.assertFalse(self.modal_errors, self.modal_errors)

    def order_cells(self):
        return [[self.order_table.item(r, c).text() for c in range(6)] for r in range(7)]

    def modal(self, action):
        def run():
            dialog = self.app.activeModalWidget()
            try:
                self.assertIsNotNone(dialog)
                action(dialog)
            except Exception as error:
                self.modal_errors.append(error)
                if dialog:
                    dialog.reject()
        QTimer.singleShot(20, run)

    def counts(self):
        return {int(self.window.client_table.item(row, 0).data(Qt.ItemDataRole.UserRole)):
                int(self.window.client_table.item(row, 3).text())
                for row in range(self.window.client_table.rowCount())}

    def fill_car(self, dialog, owner_id=1, plate="Е111АА125"):
        self.assertIsInstance(dialog, CarDialog)
        dialog.owner_input.setCurrentIndex(dialog.owner_input.findData(owner_id))
        dialog.brand_input.setText("Honda")
        dialog.model_input.setText("Fit")
        dialog.plate_input.setText(plate)

    def choose(self, table, record_id):
        row = next(row for row in range(table.rowCount())
                   if table.item(row, 0).data(Qt.ItemDataRole.UserRole) == record_id)
        table.selectRow(row)

    def answer_delete(self, dialog, confirm):
        self.assertIsInstance(dialog, QMessageBox)
        button = next(b for b in dialog.buttons() if b.text() == ("Удалить" if confirm else "Отмена"))
        button.click()

    def test_layout_navigation_and_screenshots(self):
        w = self.window
        self.assertEqual((w.width(), w.height()), (1280, 720))
        self.assertEqual(len(w.cars), 9)
        self.assertTrue(all(car["owner_id"] in {c["id"] for c in w.clients} for car in w.cars))
        self.assertTrue(all("cars" not in c for c in w.clients))
        self.assertEqual(self.counts(), {1: 1, 2: 2, 3: 1, 4: 1, 5: 2, 6: 1, 7: 1})
        for key, index in [("orders", 0), ("clients", 1), ("car", 2)]:
            QTest.mouseClick(w.nav_buttons[key], Qt.MouseButton.LeftButton)
            self.assertEqual(w.pages.currentIndex(), index)
            self.assertEqual(w.nav_buttons[key].objectName(), "activeNav")
        self.assertTrue(w.nav_buttons["history"].isEnabled())
        self.assertEqual(w.car_table.horizontalScrollBar().maximum(), 0)
        self.assertIsInstance(w.client_table.itemDelegate(), RowSelectionDelegate)
        QTest.mouseClick(w.car_table.viewport(), Qt.MouseButton.LeftButton,
                         pos=w.car_table.visualItemRect(w.car_table.item(1, 1)).center())
        self.assertEqual(w.selected_car()["id"], 2)
        self.assertTrue(w.edit_car_button.isEnabled())
        output = Path(__file__).resolve().parents[1] / "screenshots"
        output.mkdir(exist_ok=True)
        self.assertTrue(w.grab().save(str(output / "cars.png"), "PNG"))
        dialog = CarDialog(w.clients, w.cars, w)
        dialog.show()
        QTest.qWait(40)
        self.assertLess(dialog.frameGeometry().height(), 680)
        self.assertLess(dialog.frameGeometry().width(), 1280)
        self.assertTrue(w.frameGeometry().contains(dialog.frameGeometry()))
        self.assertTrue(dialog.rect().contains(dialog.save_button.geometry()))
        self.assertTrue(dialog.grab().save(str(output / "add_car.png"), "PNG"))
        dialog.reject()
        w.show_section("clients")
        w.client_table.selectRow(1)
        self.assertTrue(w.grab().save(str(output / "clients.png"), "PNG"))

    def test_required_numeric_vin_and_duplicate_validation(self):
        cases = [
            ("owner_input", None, "владельца"),
            ("brand_input", "   ", "марку"), ("model_input", "", "модель"),
            ("plate_input", "  ", "госномер"), ("plate_input", "- ·", "госномер"),
            ("plate_input", " a123bc 125 ", "уже зарегистрирован"),
            ("year_input", "1899", "Год выпуска"),
            ("year_input", str(date.today().year + 2), "Год выпуска"),
            ("year_input", "abc", "Год выпуска"),
            ("mileage_input", "-1", "Пробег"), ("mileage_input", "1.5", "Пробег"),
            ("mileage_input", "2147483648", "Пробег"),
            ("vin_input", "1234567890123456", "17 символов"),
            ("vin_input", "123456789012345678", "17 символов"),
        ]
        for field, value, message in cases:
            with self.subTest(field=field, value=value):
                dialog = CarDialog(self.window.clients, self.window.cars, self.window)
                self.fill_car(dialog)
                if field == "owner_input":
                    dialog.owner_input.setCurrentIndex(0)
                else:
                    getattr(dialog, field).setText(value)
                dialog.save_button.click()
                self.assertNotEqual(dialog.result(), QDialog.DialogCode.Accepted)
                self.assertIn(message, dialog.error.text())
                dialog.close()
        for year, mileage, vin in [("", "", ""), ("1900", "0", "12345678901234567"),
                                   (str(date.today().year + 1), "2147483647", "")]:
            dialog = CarDialog(self.window.clients, self.window.cars, self.window)
            self.fill_car(dialog)
            dialog.year_input.setText(year)
            dialog.mileage_input.setText(mileage)
            dialog.vin_input.setText(vin)
            dialog.save_button.click()
            self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
            self.assertEqual(dialog.values()["year"], int(year) if year else None)
            self.assertEqual(dialog.values()["mileage"], int(mileage) if mileage else None)

    def test_car_crud_owner_transfer_and_cancel(self):
        w = self.window
        def add(dialog):
            self.fill_car(dialog)
            dialog.save_button.click()
        self.modal(add)
        w.add_car_button.click()
        self.assertEqual(len(w.cars), 10)
        self.assertEqual(self.counts()[1], 2)
        self.assertEqual(w.selected_car()["id"], 10)
        self.assertIsNone(w.selected_car()["year"])
        def transfer(dialog):
            self.assertEqual(dialog.owner_input.currentData(), 1)
            self.assertEqual(dialog.plate_input.text(), "Е111АА125")
            dialog.owner_input.setCurrentIndex(dialog.owner_input.findData(2))
            dialog.year_input.setText("2020")
            dialog.mileage_input.setText("12345")
            dialog.vin_input.setText("12345678901234567")
            dialog.save_button.click()
        self.modal(transfer)
        w.edit_car_button.click()
        self.assertEqual(self.counts()[1], 1)
        self.assertEqual(self.counts()[2], 3)
        self.assertEqual(w.selected_car()["owner_id"], 2)
        self.assertEqual(w.selected_car()["mileage"], 12345)
        before = copy.deepcopy(w.cars)
        def cancel(dialog):
            self.fill_car(dialog, 3, "Е222АА125")
            QTest.keyClick(dialog, Qt.Key.Key_Escape)
        self.modal(cancel)
        w.edit_car_button.click()
        self.modal(lambda d: d.cancel_button.click())
        w.add_car_button.click()
        self.assertEqual(w.cars, before)
        self.modal(lambda d: self.answer_delete(d, False))
        w.delete_car_button.click()
        self.assertEqual(w.cars, before)
        self.modal(lambda d: self.answer_delete(d, True))
        w.delete_car_button.click()
        self.assertEqual(len(w.cars), 9)
        self.assertEqual(self.counts()[2], 2)
        self.modal(add)
        w.add_car_button.click()
        self.assertEqual(w.selected_car()["id"], 11)

    def test_client_rename_delete_guard_and_id_relationship(self):
        w = self.window
        w.show_section("clients")
        self.choose(w.client_table, 1)
        def rename(dialog):
            self.assertIsInstance(dialog, ClientDialog)
            dialog.name_input.setText(w.clients[1]["name"])
            dialog.save_button.click()
        self.modal(rename)
        w.edit_client_button.click()
        self.assertEqual(w.cars[0]["owner_id"], 1)
        self.assertEqual(w.car_table.item(0, 4).text(), w.clients[1]["name"])
        self.assertEqual(self.counts()[1], 1)
        self.assertEqual(self.counts()[2], 2)
        def blocked(dialog):
            self.assertIn("заказ-наряде", dialog.text())
            dialog.buttons()[0].click()
        self.modal(blocked)
        w.delete_client_button.click()
        self.assertEqual(len(w.clients), 7)
        # Освобождаем первого клиента, изменяя владельца машины через форму.
        w.show_section("car")
        self.choose(w.car_table, 1)
        def transfer(dialog):
            matches = [dialog.owner_input.itemData(i) for i in range(1, dialog.owner_input.count())
                       if w.clients[1]["name"] in dialog.owner_input.itemText(i)]
            self.assertEqual(matches, [1, 2])
            dialog.owner_input.setCurrentIndex(dialog.owner_input.findData(2))
            dialog.save_button.click()
        self.modal(transfer)
        w.edit_car_button.click()
        self.assertEqual(self.counts()[1], 0)
        self.assertEqual(self.counts()[2], 3)
        w.show_section("clients")
        self.choose(w.client_table, 1)
        # После смены владельца документ по-прежнему ссылается на исходного клиента.
        self.modal(blocked)
        w.delete_client_button.click()
        self.assertEqual(len(w.clients), 7)
        self.assertTrue(all(car["owner_id"] != 1 for car in w.cars))
        w.show_section("car")
        dialog = CarDialog(w.clients, w.cars, w)
        self.assertNotEqual(dialog.owner_input.findData(1), -1)

    def test_new_client_and_car_relationship(self):
        w = self.window
        w.show_section("clients")
        def add_client(dialog):
            dialog.name_input.setText("Тестов Илья Андреевич")
            dialog.phone_input.setText("+7 (900) 000-00-99")
            dialog.note_input.setPlainText("Новый владелец")
            dialog.save_button.click()
        self.modal(add_client)
        w.add_client_button.click()
        self.assertEqual(w.selected_client()["id"], 8)
        self.assertEqual(self.counts()[8], 0)
        w.show_section("car")
        def add_car(dialog):
            self.fill_car(dialog, 8)
            dialog.save_button.click()
        self.modal(add_car)
        w.add_car_button.click()
        self.assertEqual(w.selected_car()["owner_id"], 8)
        self.assertEqual(self.counts()[8], 1)
        w.show_section("clients")
        w.client_search.setText("тестов")
        self.assertEqual(w.client_table.rowCount(), 1)
        self.assertEqual(w.client_table.item(0, 3).text(), "1")
        w.show_section("car")
        self.modal(lambda d: self.answer_delete(d, True))
        w.delete_car_button.click()
        self.assertEqual(w.client_table.item(0, 3).text(), "0")
        w.show_section("clients")
        self.modal(lambda d: self.answer_delete(d, True))
        w.delete_client_button.click()
        self.assertEqual(len(w.clients), 7)
        self.assertEqual(w.client_table.rowCount(), 0)

    def test_search_and_memory_reset(self):
        w = self.window
        for query, expected in [("kia", 1), ("COROLLA", 1), ("a 123 bc 125", 1),
                                ("СОКОЛОВА", 2), ("Смирнов Алексей", 1), ("Нет такого", 0)]:
            w.car_search.setText(query)
            self.assertEqual(w.car_table.rowCount(), expected, query)
        self.assertTrue(w.empty_cars.isVisible())
        self.assertFalse(w.edit_car_button.isEnabled())
        w.car_search.clear()
        self.assertEqual(w.car_table.rowCount(), 9)
        w.cars[0]["owner_id"] = 2
        w.clients[0]["name"] = "Изменено"
        fresh = MainWindow()
        self.assertEqual(fresh.clients, CLIENTS)
        self.assertEqual(fresh.cars, CARS)
        fresh.close()
        self.assertEqual(normalize_plate("a 123 bc-125"), "А123ВС125")
        empty = CarDialog([], [], w)
        self.fill_car(empty)
        empty.save_button.click()
        self.assertNotEqual(empty.result(), QDialog.DialogCode.Accepted)


if __name__ == "__main__":
    unittest.main()
