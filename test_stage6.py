"""Заказы: оформление, исторические снимки, статусы и защита ссылок."""

import copy
from pathlib import Path
import unittest

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QTableWidget, QMessageBox

import test_stage4 as helpers
from main import MainWindow
from orders import OrderDialog, OrderCard, number, money
from data import ORDER_STATUSES, create_order, advance_order
from appointments import local_now


class OrdersTests(unittest.TestCase):
    setUpClass = classmethod(helpers.ServicesTests.setUpClass.__func__)
    modal = helpers.ServicesTests.modal

    def setUp(self):
        self.window = MainWindow()
        self.window.centralWidget().setObjectName("central")
        self.window.show()
        QTest.qWait(30)
        self.page = self.window.orders_page
        self.errors = []
        self.references = copy.deepcopy(self.reference_data())

    def reference_data(self):
        return (self.window.clients, self.window.cars, self.window.services_page.services,
                self.window.appointments_page.appointments)

    def tearDown(self):
        self.assertEqual(self.reference_data(), self.references)
        for widget in QApplication.topLevelWidgets():
            widget.close()
        self.assertFalse(self.errors, self.errors)

    def fill(self, dialog, car_id=1, service_ids=(3, 4)):
        car = next(c for c in self.window.cars if c["id"] == car_id)
        dialog.client_input.setCurrentIndex(dialog.client_input.findData(car["owner_id"]))
        dialog.car_input.setCurrentIndex(dialog.car_input.findData(car_id))
        dialog.reason_input.setText("Плановое обслуживание")
        for sid in service_ids:
            dialog.service_input.setCurrentIndex(dialog.service_input.findData(sid))
            dialog.add_item_button.click()

    def choose(self, table, record_id):
        row = next(r for r in range(table.rowCount())
                   if table.item(r, 0).data(Qt.ItemDataRole.UserRole) == record_id)
        table.selectRow(row)

    def answer_delete(self, dialog):
        self.assertIsInstance(dialog, QMessageBox)
        next(b for b in dialog.buttons() if b.text() == "Удалить").click()

    def test_demo_integrity_and_independent_instances(self):
        p = self.page
        self.assertIs(p.clients, self.window.clients)
        self.assertIs(p.cars, self.window.cars)
        self.assertIs(p.services, self.window.services_page.services)
        self.assertEqual(len(p.orders), 7)
        self.assertEqual(len({o["id"] for o in p.orders}), 7)
        self.assertEqual({o["status"] for o in p.orders}, set(ORDER_STATUSES))
        for order in p.orders:
            self.assertIn(order["client_id"], {c["id"] for c in p.clients})
            self.assertIn(order["car_id"], {c["id"] for c in p.cars})
            self.assertEqual(order["total"], sum(i["price"] for i in order["items"]))
            self.assertIs(type(order["total"]), int)
            self.assertGreater(len(order["items"]), 0)
            self.assertEqual(len({i["service_id"] for i in order["items"]}), len(order["items"]))
            for item in order["items"]:
                service = next(s for s in p.services if s["id"] == item["service_id"])
                self.assertEqual((item["name"], item["price"]), (service["name"], service["price"]))
                self.assertIs(type(item["price"]), int)
                self.assertIsNot(item, service)
        original = copy.deepcopy(p.orders)
        p.orders[0]["items"][0]["name"] = "Только в этом окне"
        fresh = MainWindow()
        self.assertEqual(fresh.orders_page.orders, original)
        fresh.close()

    def test_picker_validation_duplicates_and_total(self):
        d = OrderDialog(self.page.clients, self.page.cars, self.page.services, self.window)
        self.assertFalse(d.car_input.isEnabled())
        d.save_button.click()
        self.assertIn("клиента", d.error.text())
        d.client_input.setCurrentIndex(d.client_input.findData(2))
        self.assertEqual([d.car_input.itemData(i) for i in range(1, d.car_input.count())], [2, 8])
        d.car_input.setCurrentIndex(1)
        d.client_input.setCurrentIndex(d.client_input.findData(1))
        self.assertIsNone(d.car_input.currentData())
        d.car_input.addItem("Чужая машина", 2)
        d.car_input.setCurrentIndex(d.car_input.count() - 1)
        d.save_button.click()
        self.assertIn("автомобиль выбранного клиента", d.error.text())
        self.fill(d, service_ids=())
        d.reason_input.setText("   ")
        d.save_button.click()
        self.assertIn("причину", d.error.text())
        d.reason_input.setText("Проверка")
        d.save_button.click()
        self.assertIn("хотя бы одну", d.error.text())
        for sid in (3, 4):
            d.service_input.setCurrentIndex(d.service_input.findData(sid))
            d.add_item_button.click()
        self.assertEqual(d.total_label.text(), "Итого: 1 100 ₽")
        self.assertEqual(d.items_table.rowCount(), 2)
        self.assertEqual(d.service_input.findData(3), -1)
        d.service_input.addItem("Дубль", 3)
        d.service_input.setCurrentIndex(d.service_input.count() - 1)
        d.add_item_button.click()
        self.assertEqual(d.selected_ids, [3, 4])
        d.items_table.selectRow(0)
        d.remove_item_button.click()
        self.assertEqual(d.selected_ids, [4])
        self.assertEqual(d.total_label.text(), "Итого: 300 ₽")
        self.assertEqual(d.items_table.editTriggers(), QTableWidget.EditTrigger.NoEditTriggers)
        d.save_button.click()
        self.assertEqual(d.result(), QDialog.DialogCode.Accepted)
        # Пустой каталог не позволяет создать заказ.
        empty = OrderDialog(self.page.clients, self.page.cars, [], self.window)
        self.fill(empty, service_ids=())
        self.assertFalse(empty.add_item_button.isEnabled())
        empty.save_button.click()
        self.assertNotEqual(empty.result(), QDialog.DialogCode.Accepted)
        free = copy.deepcopy(self.page.services)
        free[0]["price"] = 0
        zero = OrderDialog(self.page.clients, self.page.cars, free, self.window)
        self.fill(zero, service_ids=(1,))
        self.assertEqual(zero.total_label.text(), "Итого: 0 ₽")
        zero.save_button.click()
        self.assertEqual(zero.result(), QDialog.DialogCode.Accepted)

    def test_create_cancel_and_unique_ids(self):
        p = self.page
        before = copy.deepcopy(p.orders)
        def cancel(d):
            self.fill(d)
            d.cancel_button.click()
        self.modal(cancel)
        p.add_button.click()
        self.assertEqual(p.orders, before)
        self.modal(lambda d: QTest.keyClick(d, Qt.Key.Key_Escape))
        p.add_button.click()
        self.assertEqual(p.orders, before)
        def create(d):
            self.fill(d)
            d.save_button.click()
        self.modal(create)
        p.add_button.click()
        order = p.selected_order()
        self.assertEqual(order["id"], 28)
        self.assertEqual(order["status"], "Оформлен")
        self.assertEqual(order["date"], local_now().date())
        self.assertEqual((order["car_id"], order["client_id"]), (1, 1))
        self.assertEqual(order["client_name"], self.window.clients[0]["name"])
        self.assertEqual(order["total"], 1100)
        self.assertEqual(p.table.item(0, 4).text(), "1 100 ₽")
        self.assertEqual(p.total.text(), "8")
        self.modal(create)
        p.add_button.click()
        self.assertEqual(p.selected_order()["id"], 29)
        self.assertEqual(len(p.orders), 9)

    def test_historical_snapshots_survive_reference_changes_and_service_deletion(self):
        w, p = self.window, self.page
        original = copy.deepcopy(p.orders)
        # Изменяем услугу штатной формой, затем удаляем её из каталога.
        sp = w.services_page
        w.show_section("services")
        self.choose(sp.table, 3)
        def edit_service(d):
            d.name_input.setText("Новое название работы")
            d.price_input.setText("9999")
            d.save_button.click()
        self.modal(edit_service)
        sp.edit_button.click()
        self.modal(self.answer_delete)
        sp.delete_button.click()
        self.assertTrue(all(s["id"] != 3 for s in sp.services))
        w.show_section("clients")
        self.choose(w.client_table, 1)
        def rename(d):
            d.name_input.setText("Переименован Новый Владелец")
            d.save_button.click()
        self.modal(rename)
        w.edit_client_button.click()
        w.show_section("car")
        self.choose(w.car_table, 1)
        def edit_car(d):
            d.owner_input.setCurrentIndex(d.owner_input.findData(2))
            d.brand_input.setText("Honda")
            d.model_input.setText("Fit")
            d.plate_input.setText("Е111АА125")
            d.save_button.click()
        self.modal(edit_car)
        w.edit_car_button.click()
        self.assertEqual(p.orders, original)
        w.show_section("orders")
        p.refresh()
        card = OrderCard(p.orders[0], w)
        self.assertEqual(card.client_field.text(), original[0]["client_name"])
        self.assertIn("Kia Rio", card.car_field.text())
        self.assertEqual(card.items_table.item(0, 0).text(), "Замена моторного масла")
        self.assertEqual(card.items_table.item(0, 1).text(), "800 ₽")
        self.assertEqual(p.orders[0]["total"], 1100)
        p.search.setText("А123ВС125")
        self.assertEqual(p.table.rowCount(), 1)
        # Новое оформление использует актуального владельца и актуальный каталог.
        d = OrderDialog(w.clients, w.cars, sp.services, w)
        d.client_input.setCurrentIndex(d.client_input.findData(1))
        self.assertEqual(d.car_input.count(), 1)
        self.assertFalse(d.car_input.isEnabled())
        d.client_input.setCurrentIndex(d.client_input.findData(2))
        self.assertNotEqual(d.car_input.findData(1), -1)
        self.assertEqual(d.service_input.findData(3), -1)
        self.references = copy.deepcopy(self.reference_data())

    def test_status_sequence_card_and_double_click(self):
        p = self.page
        self.choose(p.table, 26)
        order = p.selected_order()
        immutable = copy.deepcopy({k: v for k, v in order.items() if k not in ("status", "completed_at")})
        def progress(d):
            self.assertIsInstance(d, OrderCard)
            self.assertTrue(d.client_field.isReadOnly())
            self.assertTrue(d.reason_field.isReadOnly())
            self.assertEqual(d.items_table.editTriggers(), QTableWidget.EditTrigger.NoEditTriggers)
            for expected in ORDER_STATUSES[1:]:
                d.next_button.click()
                self.assertEqual(order["status"], expected)
            self.assertFalse(d.next_button.isEnabled())
            d.next_stage()
            self.assertEqual(order["status"], "Завершён")
            d.close_button.click()
        self.modal(progress)
        row = p.table.currentRow()
        pos = p.table.visualItemRect(p.table.item(row, 0)).center()
        QTest.mouseClick(p.table.viewport(), Qt.MouseButton.LeftButton, pos=pos)
        QTest.mouseDClick(p.table.viewport(), Qt.MouseButton.LeftButton, pos=pos)
        self.assertEqual(order["status"], "Завершён")
        self.assertEqual(p.table.item(p.table.currentRow(), 5).text(), "Завершён")
        self.assertEqual({k: v for k, v in order.items() if k not in ("status", "completed_at")}, immutable)
        self.assertIsNotNone(order["completed_at"])
        self.assertEqual(len(p.orders), 7)
        def completed(d):
            self.assertFalse(d.next_button.isEnabled())
            self.assertFalse(advance_order(order))
            d.close_button.click()
        self.modal(completed)
        p.open_button.click()

    def test_deletion_guards_for_historical_client_and_car(self):
        w, p = self.window, self.page
        # Машина 8 не имеет записей на обслуживание: проверяем именно новый запрет по заказу.
        def create(d):
            self.fill(d, car_id=8)
            d.save_button.click()
        self.modal(create)
        p.add_button.click()
        historical = p.selected_order()
        w.show_section("car")
        self.choose(w.car_table, 8)
        def blocked(d):
            self.assertIn("заказ-наряде", d.text())
            d.buttons()[0].click()
        self.modal(blocked)
        w.delete_car_button.click()
        self.assertEqual(len(w.cars), 9)
        # Текущий владелец может смениться; исходный клиент документа остаётся защищённым.
        def transfer(d):
            d.owner_input.setCurrentIndex(d.owner_input.findData(1))
            d.save_button.click()
        self.modal(transfer)
        w.edit_car_button.click()
        w.show_section("clients")
        self.choose(w.client_table, 2)
        self.modal(blocked)
        w.delete_client_button.click()
        self.assertEqual(len(w.clients), 7)
        self.assertEqual(historical["client_id"], 2)
        self.references = copy.deepcopy(self.reference_data())

    def test_search_layout_and_screenshots(self):
        w, p = self.window, self.page
        self.assertEqual((w.width(), w.height()), (1280, 720))
        self.assertEqual(p.table.horizontalScrollBar().maximum(), 0)
        old_car_widget = p.table.cellWidget(0, 2)
        p.search.setText("ЗН-0027")
        self.assertTrue(old_car_widget.isHidden())
        p.search.clear()
        for query, count in [("ЗН-0027", 1), ("СМИРНОВ", 1), ("kia rio", 1),
                             ("a 123 bc 125", 1), ("нет такого", 0)]:
            p.search.setText(query)
            self.assertEqual(p.table.rowCount(), count)
        self.assertTrue(p.empty.isVisible())
        self.assertFalse(p.open_button.isEnabled())
        p.search.clear()
        self.choose(p.table, 27)
        QTest.qWait(30)
        output = Path(__file__).resolve().parent / "screenshots"
        self.assertTrue(w.grab().save(str(output / "orders.png"), "PNG"))
        self.assertTrue(w.grab().save(str(output / "screenshot.png"), "PNG"))
        d = OrderDialog(p.clients, p.cars, p.services, w)
        self.fill(d)
        d.show()
        QTest.qWait(40)
        self.assertTrue(w.frameGeometry().contains(d.frameGeometry()))
        self.assertLess(d.frameGeometry().height(), 680)
        self.assertTrue(d.rect().contains(d.save_button.geometry()))
        self.assertTrue(d.grab().save(str(output / "new_order.png"), "PNG"))
        d.reject()
        card = OrderCard(p.orders[0], w)
        card.show()
        QTest.qWait(40)
        self.assertTrue(w.frameGeometry().contains(card.frameGeometry()))
        self.assertLess(card.frameGeometry().height(), 680)
        self.assertTrue(card.grab().save(str(output / "order_card.png"), "PNG"))
        card.reject()

    def test_model_rejects_inconsistent_orders(self):
        clients, cars, services = self.page.clients, self.page.cars, self.page.services
        def build(client=clients[0], selected=(services[0],), reason="Проверка"):
            return create_order(100, local_now().date(), client, cars[0], selected, reason)
        with self.assertRaises(ValueError):
            build(client=clients[1])
        with self.assertRaises(ValueError):
            build(selected=())
        with self.assertRaises(ValueError):
            build(selected=(services[0], services[0]))
        with self.assertRaises(ValueError):
            build(reason="   ")
        for price in (-1, 12.5):
            with self.assertRaises(ValueError):
                build(selected=({**services[0], "price": price},))
        order = build(selected=({**services[0], "price": 0},))
        self.assertEqual(order["total"], 0)
        self.assertIs(type(order["total"]), int)


if __name__ == "__main__":
    unittest.main()
