"""Заказы и история: реальные Qt-формы и изолированная SQLite."""

import copy
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox, QDialog

from autoservice.data import ORDER_STATUSES
from autoservice.database import Database
from autoservice.orders import OrderCard
from main import MainWindow
from tests import test_stage6 as helpers


class OrdersSqliteTests(unittest.TestCase):
    setUpClass = classmethod(helpers.OrdersTests.setUpClass.__func__)
    modal = helpers.OrdersTests.modal
    choose = helpers.OrdersTests.choose

    def setUp(self):
        root = Path(__file__).resolve().parents[1] / ".tmp"
        root.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="orders-test-", dir=root)
        self.path = Path(self.temporary.name) / "test.db"
        self.db = Database(self.path)
        discarded = self.db.add_client("Удалённый", "0")
        self.db.delete_client(discarded["id"])
        self.client = self.db.add_client("Вера Историческая", "+7 (900) 111-22-33")
        self.other = self.db.add_client("Другой Владелец", "89992223344")
        discarded = self.db.add_car(self.client["id"], "Удалённая", "Машина", "А001АА125")
        self.db.delete_car(discarded["id"])
        self.car = self.db.add_car(self.client["id"], "Honda", "Fit", "Е111АА125", 2018)
        discarded = self.db.add_service("Удалённая", "Ремонт", 0)
        self.db.delete_service(discarded["id"])
        self.service = self.db.add_service("Замена масла", "Техническое обслуживание", 800, 30)
        self.second = self.db.add_service("Замена фильтра", "Техническое обслуживание", 300, 10)
        self.window = MainWindow(database=self.db)
        self.window.centralWidget().setObjectName("central")
        self.window.show()
        self.page = self.window.orders_page
        self.errors = []
        QTest.qWait(10)

    def tearDown(self):
        self.window.close()
        self.db.close()
        self.temporary.cleanup()
        self.assertFalse(self.errors, self.errors)

    def fill(self, dialog):
        helpers.OrdersTests.fill(self, dialog, self.car["id"], (self.service["id"], self.second["id"]))

    def create(self):
        def submit(dialog):
            self.fill(dialog)
            dialog.save_button.click()
        self.modal(submit)
        self.page.add_button.click()
        return self.page.selected_order()

    def reopen(self):
        self.window.close()
        self.db.close()
        self.db = Database(self.path)
        self.window = MainWindow(database=self.db)
        self.window.show()
        self.page = self.window.orders_page

    @contextmanager
    def notices(self):
        messages = []
        original = QMessageBox.exec
        def execute(box):
            if box.windowTitle() == "Ошибка сохранения":
                messages.append((box.text(), box.detailedText()))
                return 0
            return original(box)
        with patch.object(QMessageBox, "exec", execute):
            yield messages

    def inspect_card(self, action, history=False, double_click=False):
        page = self.window.history_page if history else self.page
        self.window.show_section("history" if history else "orders")
        QTest.qWait(30)
        if double_click:
            point = page.table.visualItemRect(page.table.item(0, 0)).center()
            QTest.mouseClick(page.table.viewport(), Qt.MouseButton.LeftButton, pos=point)
        self.modal(action)
        if double_click:
            QTest.mouseDClick(page.table.viewport(), Qt.MouseButton.LeftButton, pos=point)
        else:
            page.open_button.click()

    def finish(self):
        def complete(card):
            for expected in ORDER_STATUSES[1:]:
                card.next_button.click()
                self.assertEqual(card.status_label.text(), expected)
            card.close_button.click()
        self.inspect_card(complete)

    def test_empty_database_has_no_automatic_demo_orders(self):
        self.assertEqual(self.page.orders, [])
        self.assertEqual(self.page.total.text(), "0")
        self.assertTrue(self.page.empty.isVisible())
        self.assertFalse(self.page.open_button.isEnabled())
        self.assertEqual(self.db.list_orders(), [])
        self.assertEqual(self.window.history_page.completed_orders(), [])
        self.assertIs(self.page.orders, self.window.history_page.orders)
        self.assertIsNone(self.page.next_id)
        self.assertEqual(self.window.appointments_page.appointments, [])

    def test_create_via_form_ids_items_total_and_restart(self):
        order = self.create()
        self.assertEqual(order["id"], 1)
        self.assertEqual((order["client_id"], order["car_id"]), (self.client["id"], self.car["id"]))
        self.assertEqual([i["service_id"] for i in order["items"]], [self.service["id"], self.second["id"]])
        self.assertEqual(order["total"], 1100)
        self.assertIs(type(order["total"]), int)
        self.assertEqual(order, self.db.get_order(order["id"]))
        self.assertEqual(self.page.table.item(0, 0).text(), "ЗН-0001")
        self.assertEqual(self.page.table.item(0, 4).text(), "1 100 ₽")
        self.assertEqual(self.page.total.text(), "1")
        self.reopen()
        self.assertEqual(self.page.orders, [order])
        self.assertIs(self.page.orders, self.window.history_page.orders)

    def test_search_and_card_button_and_double_click(self):
        order = self.create()
        self.reopen()
        for query in ("ЗН-0001", "историческая", "Honda", "Fit", "e111aa125"):
            self.page.search.setText(query)
            self.assertEqual(self.page.table.rowCount(), 1, query)
        self.page.search.setText("Не существует")
        self.assertEqual(self.page.table.rowCount(), 0)
        self.assertFalse(self.page.open_button.isEnabled())
        self.page.search.clear()
        self.choose(self.page.table, order["id"])
        def inspect(card):
            self.assertIsInstance(card, OrderCard)
            self.assertEqual(card.order, order)
            self.assertIs(card.order, self.page.orders[0])
            self.assertEqual(card.client_field.text(), order["client_name"])
            self.assertEqual(card.items_table.rowCount(), 2)
            self.assertTrue(card.reason_field.isReadOnly())
            card.close_button.click()
        self.inspect_card(inspect)
        self.inspect_card(inspect, double_click=True)

    def test_statuses_table_card_history_update_together_and_restart(self):
        self.create()
        orders = self.page.orders
        def complete(card):
            for status in ORDER_STATUSES[1:]:
                card.next_button.click()
                self.assertEqual(card.order["status"], status)
                self.assertEqual(card.status_label.text(), status)
                self.assertEqual(self.page.table.item(0, 5).text(), status)
                self.assertEqual(self.db.get_order(card.order["id"]), card.order)
                self.assertIs(card.order, self.page.selected_order())
                self.assertIs(self.window.history_page.orders, orders)
                self.assertEqual(self.window.history_page.total.text(), "1" if status == "Завершён" else "0")
            completed_at = card.order["completed_at"]
            self.assertEqual(completed_at.utcoffset(), timedelta(hours=10))
            self.assertEqual(completed_at.tzname(), "Asia/Vladivostok")
            self.assertIn(completed_at.strftime("%d.%m.%Y · %H:%M"), card.completed_label.text())
            self.assertFalse(card.next_button.isEnabled())
            before = copy.deepcopy(card.order)
            card.next_stage()
            self.assertEqual(card.order, before)
            card.close_button.click()
        self.inspect_card(complete)
        before = copy.deepcopy(self.page.orders)
        self.reopen()
        self.assertEqual(self.page.orders, before)
        history = self.window.history_page
        self.assertEqual(history.completed_orders(), before)
        self.assertEqual(history.table.item(0, 1).text(), before[0]["completed_at"].strftime("%d.%m.%Y\n%H:%M"))
        self.choose(history.table, before[0]["id"])
        def readonly(card):
            self.assertFalse(card.next_button.isEnabled())
            card.next_stage()
            self.assertEqual(card.order, before[0])
            card.close_button.click()
        self.inspect_card(readonly, history=True, double_click=True)
        self.assertEqual(self.db.get_order(before[0]["id"]), before[0])

    def test_history_sort_search_and_shared_collection(self):
        first = self.create()
        self.finish()
        second = self.create()
        self.finish()
        self.reopen()
        history = self.window.history_page
        self.assertEqual([o["id"] for o in history.completed_orders()], [second["id"], first["id"]])
        for query, expected in (("ЗН-0001", 1), ("Замена   масла", 2), ("Историческая", 2), ("Honda", 2), ("e111aa125", 2), ("Нет такой работы", 0)):
            history.search.setText(query)
            self.assertEqual(history.table.rowCount(), expected, query)
        self.assertIs(history.orders, self.page.orders)
        self.assertIs(history.completed_orders()[0], self.page.orders[0])

    def test_historical_document_survives_reference_edits_and_service_deletion(self):
        original = copy.deepcopy(self.create())
        w = self.window
        self.choose(w.client_table, self.client["id"])
        def client_edit(d):
            d.name_input.setText("Новое имя владельца")
            d.save_button.click()
        self.modal(client_edit)
        w.edit_client()
        self.choose(w.car_table, self.car["id"])
        def car_edit(d):
            d.owner_input.setCurrentIndex(d.owner_input.findData(self.other["id"]))
            d.brand_input.setText("Toyota")
            d.model_input.setText("Yaris")
            d.plate_input.setText("А222АА125")
            d.save_button.click()
        self.modal(car_edit)
        w.edit_car()
        services = w.services_page
        self.choose(services.table, self.service["id"])
        def service_edit(d):
            d.name_input.setText("Новое название")
            d.price_input.setText("1200")
            d.save_button.click()
        self.modal(service_edit)
        services.edit_service()
        self.assertEqual(self.db.get_order(original["id"]), original)
        self.modal(helpers.OrdersTests.answer_delete.__get__(self))
        services.delete_service()
        self.reopen()
        self.assertEqual(self.page.orders, [original])
        self.choose(self.page.table, original["id"])
        def inspect(card):
            self.assertEqual(card.order, original)
            self.assertEqual(card.items_table.item(0, 0).text(), "Замена масла")
            self.assertEqual(card.items_table.item(0, 1).text(), "800 ₽")
            self.assertIn("Honda Fit", card.car_field.text())
            card.close_button.click()
        self.inspect_card(inspect)
        self.finish()
        completed = copy.deepcopy(self.page.orders[0])
        self.reopen()
        self.assertEqual(self.window.history_page.completed_orders(), [completed])
        self.assertEqual(completed["items"], original["items"])
        self.assertEqual(completed["total"], 1100)
        self.window.history_page.search.setText("Замена масла")
        self.assertEqual(self.window.history_page.table.rowCount(), 1)
        self.window.history_page.search.setText("Новое название")
        self.assertEqual(self.window.history_page.table.rowCount(), 0)

    def test_existing_database_orders_define_ids_without_ui_counters(self):
        first = self.db.add_order(self.client["id"], self.car["id"], [self.service["id"]], "Существующий")
        self.reopen()
        self.assertEqual(self.page.orders, [first])
        second = self.create()
        self.assertEqual(second["id"], first["id"] + 1)
        self.reopen()
        third = self.create()
        self.assertEqual(third["id"], second["id"] + 1)
        self.assertEqual(len({o["id"] for o in self.page.orders}), 3)
        self.assertIsNone(self.page.next_id)

    def test_failed_create_rolls_back_items_and_preserves_form_for_retry(self):
        self.db._connection.execute("CREATE TRIGGER reject_second_item BEFORE INSERT ON order_items WHEN NEW.position=1 BEGIN SELECT RAISE(ABORT,'item denied'); END")
        def submit(dialog):
            self.fill(dialog)
            inputs = dialog.values()
            with self.notices() as messages:
                dialog.save_button.click()
            self.assertEqual(len(messages), 1)
            self.assertTrue(dialog.isVisible())
            self.assertEqual(dialog.values(), inputs)
            self.assertEqual(dialog.total_label.text(), "Итого: 1 100 ₽")
            self.assertEqual(dialog.items_table.rowCount(), 2)
            self.assertEqual(self.db.list_orders(), [])
            self.assertEqual(self.db._connection.execute("SELECT count(*) FROM order_items").fetchone()[0], 0)
            self.assertEqual(self.page.orders, [])
            self.assertEqual(self.page.total.text(), "0")
            self.db._connection.execute("DROP TRIGGER reject_second_item")
            dialog.save_button.click()
        self.modal(submit)
        self.page.add_order()
        self.assertEqual(self.page.orders, self.db.list_orders())
        self.assertEqual(len(self.page.orders), 1)

    def test_failed_refresh_rolls_back_creation_and_keeps_previous_selection(self):
        original = copy.deepcopy(self.create())
        self.page.search.setText("ЗН-0001")
        def submit(dialog):
            self.fill(dialog)
            with patch.object(self.db, "list_orders", side_effect=sqlite3.OperationalError("read failed")):
                with self.notices() as messages:
                    dialog.save_button.click()
            self.assertEqual(len(messages), 1)
            self.assertEqual(self.db.list_orders(), [original])
            self.assertEqual(self.page.selected_order(), original)
            self.assertEqual(self.page.search.text(), "ЗН-0001")
            dialog.cancel_button.click()
        self.modal(submit)
        self.page.add_order()
        self.assertEqual(self.page.orders, [original])

    def test_locked_status_does_not_change_card_table_or_history(self):
        self.create()
        self.db._connection.execute("PRAGMA busy_timeout=0")
        def inspect(card):
            before = copy.deepcopy(card.order)
            button = (card.next_button.text(), card.next_button.isEnabled())
            with Database(self.path) as other:
                with other.transaction():
                    with self.notices() as messages:
                        card.next_button.click()
            self.assertEqual(len(messages), 1)
            self.assertIn("SQLite", messages[0][0])
            self.assertEqual(card.order, before)
            self.assertEqual(card.status_label.text(), before["status"])
            self.assertEqual(self.page.selected_order(), before)
            self.assertEqual(self.page.table.item(0, 5).text(), before["status"])
            self.assertEqual((card.next_button.text(), card.next_button.isEnabled()), button)
            self.assertEqual(self.db.get_order(before["id"]), before)
            self.assertEqual(self.window.history_page.total.text(), "0")
            card.next_button.click()
            self.assertEqual(card.status_label.text(), "В работе")
            card.close_button.click()
        self.inspect_card(inspect)

    def test_failed_completion_keeps_timestamp_empty_and_history_unchanged(self):
        self.create()
        def inspect(card):
            card.next_button.click()
            card.next_button.click()
            before = copy.deepcopy(card.order)
            self.db._connection.execute("CREATE TRIGGER reject_completion BEFORE UPDATE ON orders WHEN NEW.status='Завершён' BEGIN SELECT RAISE(ABORT,'completion denied'); END")
            with self.notices() as messages:
                card.next_button.click()
            self.assertEqual(len(messages), 1)
            self.assertEqual(card.order, before)
            self.assertIsNone(card.order["completed_at"])
            self.assertEqual(card.status_label.text(), "Готов к выдаче")
            self.assertEqual(self.page.table.item(0, 5).text(), "Готов к выдаче")
            self.assertTrue(card.next_button.isEnabled())
            self.assertEqual(self.window.history_page.total.text(), "0")
            self.assertEqual(self.db.get_order(before["id"]), before)
            card.close_button.click()
        self.inspect_card(inspect)

    def test_commit_failure_rolls_back_status_and_shared_collection(self):
        self.create()
        def inspect(card):
            before = copy.deepcopy(card.order)
            def authorize(action, argument, *unused):
                if action == sqlite3.SQLITE_TRANSACTION and argument == "COMMIT":
                    return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            self.db._connection.set_authorizer(authorize)
            try:
                with self.notices() as messages:
                    card.next_button.click()
            finally:
                self.db._connection.set_authorizer(None)
            self.assertEqual(len(messages), 1)
            self.assertEqual(card.order, before)
            self.assertEqual(self.page.orders, [before])
            self.assertEqual(self.db.get_order(before["id"]), before)
            self.assertEqual(self.window.history_page.total.text(), "0")
            self.assertEqual(card.status_label.text(), "Оформлен")
            self.assertTrue(card.next_button.isEnabled())
            card.close_button.click()
        self.inspect_card(inspect)

    def test_status_refresh_failure_rolls_back_advance(self):
        self.create()
        def inspect(card):
            before = copy.deepcopy(card.order)
            with patch.object(self.db, "list_orders", side_effect=sqlite3.OperationalError("read failed")):
                with self.notices() as messages:
                    card.next_button.click()
            self.assertEqual(len(messages), 1)
            self.assertEqual(self.db.get_order(before["id"]), before)
            self.assertEqual(card.order, before)
            self.assertEqual(self.page.selected_order(), before)
            self.assertEqual(card.status_label.text(), "Оформлен")
            card.close_button.click()
        self.inspect_card(inspect)

    def test_sqlite_blocks_skip_snapshot_edit_and_repeat_completion(self):
        order = self.create()
        with self.assertRaises(sqlite3.IntegrityError):
            self.db._connection.execute("UPDATE orders SET status='Готов к выдаче' WHERE id=?", (order["id"],))
        self.assertEqual(self.db.get_order(order["id"]), order)
        self.finish()
        completed = self.db.get_order(order["id"])
        with self.assertRaises(sqlite3.IntegrityError):
            self.db._connection.execute("UPDATE orders SET reason='Изменено' WHERE id=?", (order["id"],))
        self.assertEqual(self.db.advance_order(order["id"]), completed)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db._connection.execute("UPDATE orders SET completed_at=? WHERE id=?", ((completed["completed_at"] + timedelta(days=1)).isoformat(), order["id"]))
        self.assertEqual(self.db.get_order(order["id"]), completed)

    def test_form_validation_cancel_and_other_sections_unchanged(self):
        references = copy.deepcopy((self.window.clients, self.window.cars, self.window.services_page.services))
        def validate(dialog):
            dialog.save_button.click()
            self.assertIn("клиента", dialog.error.text())
            self.fill(dialog)
            dialog.selected_ids.clear()
            dialog.refresh_items()
            dialog.save_button.click()
            self.assertIn("хотя бы одну", dialog.error.text())
            self.fill(dialog)
            dialog.car_input.addItem("Чужая машина", -100)
            dialog.car_input.setCurrentIndex(dialog.car_input.count() - 1)
            dialog.save_button.click()
            self.assertIn("автомобиль выбранного клиента", dialog.error.text())
            self.assertNotEqual(dialog.result(), QDialog.DialogCode.Accepted)
            dialog.cancel_button.click()
        self.modal(validate)
        self.page.add_order()
        self.assertEqual(self.db.list_orders(), [])
        self.create()
        self.assertEqual((self.window.clients, self.window.cars, self.window.services_page.services), references)
        for section in ("clients", "car", "services", "calendar", "history", "orders"):
            self.window.show_section(section)
            self.assertEqual(self.window.nav_buttons[section].objectName(), "activeNav")
            self.assertEqual((self.window.width(), self.window.height()), (1280, 720))
        self.assertEqual(self.window.appointments_page.appointments, [])
        self.assertEqual(self.db.list_appointments(), [])


if __name__ == "__main__":
    unittest.main()
