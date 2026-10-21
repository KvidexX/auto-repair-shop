"""Интеграция существующих Qt-форм с отдельной SQLite-базой."""

import copy
from contextlib import contextmanager
from datetime import timedelta, time
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox

from autoservice.demo_data import CLIENTS, CARS, SERVICES
from autoservice.data import local_now
from autoservice.database import Database
from autoservice.services import ServicesPage
from autoservice.ui import RowSelectionDelegate
from autoservice.app import MainWindow
from autoservice.styles import STYLE
from tests import test_stage4


class ReferenceSqliteTests(unittest.TestCase):
    setUpClass = classmethod(test_stage4.ServicesTests.setUpClass.__func__)
    modal = test_stage4.ServicesTests.modal

    def setUp(self):
        root = Path(__file__).resolve().parents[1] / ".tmp"
        root.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="reference-test-", dir=root)
        self.path = Path(self.temporary.name) / "test.db"
        self.db = Database(self.path)
        # Leave deleted IDs so tests cannot accidentally pass with UI counters.
        discarded = self.db.add_client("Удалённый", "0")
        self.db.delete_client(discarded["id"])
        self.owner = self.db.add_client("Анна Тестовая", "+7 (900) 111-22-33")
        self.other = self.db.add_client("Борис Примеров", "+7 (900) 222-33-44")
        self.window = MainWindow(database=self.db)
        self.window.centralWidget().setObjectName("central")
        self.window.show()
        self.window.show_section("clients")
        QTest.qWait(10)
        self.errors = []

    def tearDown(self):
        self.window.close()
        self.db.close()
        self.temporary.cleanup()
        self.assertFalse(self.errors, self.errors)

    def choose(self, table, record_id):
        row = next(r for r in range(table.rowCount())
                   if table.item(r, 0).data(Qt.ItemDataRole.UserRole) == record_id)
        table.selectRow(row)

    def confirm(self, dialog):
        next(b for b in dialog.buttons() if b.text() == "Удалить").click()

    def add_client(self, name="Вера Новая", phone="89995554433"):
        def fill(dialog):
            dialog.name_input.setText(name)
            dialog.phone_input.setText(phone)
            dialog.note_input.setPlainText("Проверка сохранения")
            dialog.save_button.click()
        self.modal(fill)
        self.window.add_client()

    def add_car(self, owner_id=None, plate="Е111АА125"):
        def fill(dialog):
            owner = self.owner["id"] if owner_id is None else owner_id
            dialog.owner_input.setCurrentIndex(dialog.owner_input.findData(owner))
            dialog.brand_input.setText("Honda")
            dialog.model_input.setText("Fit")
            dialog.plate_input.setText(plate)
            dialog.year_input.setText("2018")
            dialog.mileage_input.setText("75000")
            dialog.save_button.click()
        self.window.show_section("car")
        self.modal(fill)
        self.window.add_car()

    def add_service(self):
        def fill(dialog):
            dialog.name_input.setText("Проверка освещения")
            dialog.category_input.setCurrentIndex(1)
            dialog.price_input.setText("1250")
            dialog.duration_input.setText("25")
            dialog.save_button.click()
        self.window.show_section("services")
        self.modal(fill)
        self.window.services_page.add_service()

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

    def counts(self):
        table = self.window.client_table
        return {table.item(r, 0).data(Qt.ItemDataRole.UserRole): int(table.item(r, 3).text())
                for r in range(table.rowCount())}

    def reopen(self):
        self.window.close()
        self.db.close()
        self.db = Database(self.path)
        self.window = MainWindow(database=self.db)
        self.window.show()

    def test_client_form_persistence_edit_search_and_delete(self):
        self.add_client()
        record = self.window.selected_client()
        self.assertEqual(record, self.db.get_client(record["id"]))
        self.assertEqual(record["id"], 4)
        self.reopen()
        self.choose(self.window.client_table, record["id"])
        self.assertEqual(self.window.selected_client(), record)
        def edit(dialog):
            dialog.name_input.setText("Вера Изменённая")
            dialog.save_button.click()
        self.modal(edit)
        self.window.edit_client()
        self.assertEqual(self.db.get_client(record["id"])["name"], "Вера Изменённая")
        for query in ("изменённая", "+7 (900) 111-22-33", "79001112233"):
            self.window.client_search.setText(query)
            self.assertEqual(self.window.client_table.rowCount(), 1)
        self.window.client_search.clear()
        self.choose(self.window.client_table, record["id"])
        self.modal(self.confirm)
        self.window.delete_client()
        self.reopen()
        self.assertNotIn(record["id"], [c["id"] for c in self.window.clients])

    def test_car_crud_transfer_counts_owner_rename_search_and_restart(self):
        self.add_car()
        car = self.window.selected_car()
        self.assertEqual(self.db.get_car(car["id"]), car)
        self.assertEqual(self.counts(), {self.owner["id"]: 1, self.other["id"]: 0})
        def edit(dialog):
            dialog.owner_input.setCurrentIndex(dialog.owner_input.findData(self.other["id"]))
            dialog.mileage_input.setText("80000")
            dialog.save_button.click()
        self.modal(edit)
        self.window.edit_car()
        self.assertEqual(self.counts(), {self.owner["id"]: 0, self.other["id"]: 1})
        self.assertEqual(self.db.car_count(self.other["id"]), 1)
        self.window.show_section("clients")
        self.choose(self.window.client_table, self.other["id"])
        def rename(dialog):
            dialog.name_input.setText("Борис Переименован")
            dialog.save_button.click()
        self.modal(rename)
        self.window.edit_client()
        self.assertEqual(self.window.car_table.item(0, 4).text(), "Борис Переименован")
        for query in ("honda", "fit", "е111аа125", "переименован"):
            self.window.car_search.setText(query)
            self.assertEqual(self.window.car_table.rowCount(), 1)
        self.window.car_search.clear()
        self.reopen()
        self.assertEqual(self.window.cars[0]["mileage"], 80000)
        self.assertEqual(self.counts()[self.other["id"]], 1)
        self.choose(self.window.car_table, car["id"])
        self.modal(self.confirm)
        self.window.delete_car()
        self.assertEqual(self.counts()[self.other["id"]], 0)
        self.assertEqual(self.db.list_cars(), [])

    def test_client_with_car_cannot_be_deleted(self):
        self.add_car()
        before = copy.deepcopy(self.window.clients)
        self.choose(self.window.client_table, self.owner["id"])
        def dismiss(dialog):
            self.assertIn("зарегистрированные автомобили", dialog.text())
            dialog.buttons()[0].click()
        self.modal(dismiss)
        self.window.delete_client()
        self.assertEqual(self.window.clients, before)
        self.assertEqual(self.db.list_clients(), before)

    def test_sqlite_restricts_deleting_car_with_persisted_appointment(self):
        self.add_car()
        car = self.window.selected_car()
        self.db.add_appointment(car["id"], local_now().date() + timedelta(days=2), time(9), "Проверка")
        self.modal(self.confirm)
        with self.notices() as messages:
            self.window.delete_car()
        self.assertEqual(len(messages), 1)
        self.assertIn("связана", messages[0][0])
        self.assertEqual(self.window.selected_car(), car)
        self.assertEqual(self.counts()[self.owner["id"]], 1)
        self.assertEqual(self.db.list_cars(), [car])

    def test_sqlite_restricts_client_after_owner_transfer_with_persisted_order(self):
        self.add_car()
        car = self.window.selected_car()
        self.add_service()
        service = self.window.services_page.selected_service()
        self.db.add_order(self.owner["id"], car["id"], [service["id"]], "Проверка")
        values = {k: v for k, v in car.items() if k != "id"}
        values["owner_id"] = self.other["id"]
        self.window.save_references(lambda: self.db.update_car(car["id"], **values))
        self.window.refresh_clients()
        self.window.refresh_cars()
        self.choose(self.window.client_table, self.owner["id"])
        self.modal(self.confirm)
        with self.notices() as messages:
            self.window.delete_client()
        self.assertEqual(len(messages), 1)
        self.assertEqual(self.window.selected_client(), self.owner)
        self.assertEqual(self.db.get_client(self.owner["id"]), self.owner)

    def test_service_crud_price_persistence_and_historical_snapshots(self):
        self.add_car()
        car = self.window.selected_car()
        self.add_service()
        page = self.window.services_page
        service = page.selected_service()
        order = self.db.add_order(self.owner["id"], car["id"], [service["id"]], "Проверка")
        def edit(dialog):
            dialog.price_input.setText("1700")
            dialog.category_input.setCurrentIndex(3)
            dialog.save_button.click()
        self.modal(edit)
        page.edit_service()
        self.reopen()
        page = self.window.services_page
        self.assertEqual(page.services[0]["price"], 1700)
        self.assertIs(type(page.services[0]["price"]), int)
        for query in ("освещения", "ремонт"):
            page.search.setText(query)
            self.assertEqual(page.table.rowCount(), 1)
        page.search.clear()
        self.choose(page.table, service["id"])
        self.modal(self.confirm)
        page.delete_service()
        self.assertEqual(page.total.text(), "0")
        self.assertEqual(self.db.list_services(), [])
        self.assertEqual(self.db.get_order(order["id"]), order)
        self.add_service()
        self.assertGreater(page.selected_service()["id"], service["id"])

    def test_failed_insert_has_no_phantom_client(self):
        before = copy.deepcopy(self.window.clients)
        self.choose(self.window.client_table, self.owner["id"])
        self.db._connection.execute("CREATE TRIGGER reject_client BEFORE INSERT ON clients BEGIN SELECT RAISE(ABORT,'test denial'); END")
        with self.notices() as messages:
            self.add_client()
        self.assertEqual(len(messages), 1)
        self.assertEqual(self.window.clients, before)
        self.assertEqual(self.db.list_clients(), before)
        self.assertEqual(self.window.selected_client(), self.owner)

    def test_failed_edit_and_delete_preserve_service_selection_and_search(self):
        self.add_service()
        page = self.window.services_page
        before = copy.deepcopy(page.services)
        page.search.setText("освещения")
        self.db._connection.execute("CREATE TRIGGER reject_service_edit BEFORE UPDATE ON services BEGIN SELECT RAISE(ABORT,'test denial'); END")
        def edit(dialog):
            dialog.price_input.setText("999")
            dialog.save_button.click()
        self.modal(edit)
        with self.notices() as messages:
            page.edit_service()
        self.assertEqual(len(messages), 1)
        self.assertEqual(page.services, before)
        self.assertEqual(page.selected_service(), before[0])
        self.assertEqual(page.search.text(), "освещения")
        self.db._connection.execute("CREATE TRIGGER reject_service_delete BEFORE DELETE ON services BEGIN SELECT RAISE(ABORT,'test denial'); END")
        self.modal(self.confirm)
        with self.notices() as messages:
            page.delete_service()
        self.assertEqual(len(messages), 1)
        self.assertEqual(self.db.list_services(), before)
        self.assertEqual(page.services, before)
        self.assertEqual(page.selected_service(), before[0])

    def test_failed_car_owner_change_preserves_both_counts(self):
        self.add_car()
        before = copy.deepcopy(self.window.cars)
        counts = self.counts()
        self.db._connection.execute("CREATE TRIGGER reject_owner BEFORE UPDATE ON cars BEGIN SELECT RAISE(ABORT,'test denial'); END")
        def edit(dialog):
            dialog.owner_input.setCurrentIndex(dialog.owner_input.findData(self.other["id"]))
            dialog.save_button.click()
        self.modal(edit)
        with self.notices() as messages:
            self.window.edit_car()
        self.assertEqual(len(messages), 1)
        self.assertEqual(self.window.cars, before)
        self.assertEqual(self.db.list_cars(), before)
        self.assertEqual(self.counts(), counts)
        self.assertEqual(self.window.selected_car(), before[0])

    def test_read_failure_after_insert_rolls_back_database_and_ui(self):
        before = copy.deepcopy(self.window.clients)
        with patch.object(self.db, "list_cars", side_effect=sqlite3.OperationalError("read failed")):
            with self.notices() as messages:
                self.add_client()
        self.assertEqual(len(messages), 1)
        self.assertEqual(self.db.list_clients(), before)
        self.assertEqual(self.window.clients, before)

    def test_locked_database_shows_error_and_keeps_ui(self):
        self.db._connection.execute("PRAGMA busy_timeout=0")
        before = copy.deepcopy(self.window.clients)
        with Database(self.path) as second:
            with second.transaction():
                with self.notices() as messages:
                    self.add_client()
        self.assertEqual(len(messages), 1)
        self.assertIn("SQLite", messages[0][0])
        self.assertEqual(self.window.clients, before)
        self.assertEqual(self.db.list_clients(), before)

    def test_database_uniqueness_catches_stale_ui(self):
        # Another connection changes the catalogue while the form still sees an empty list.
        with Database(self.path) as second:
            second.add_service("  ПРОВЕРКА   освещения ", "Ремонт", 100)
        with self.notices() as messages:
            self.add_service()
        self.assertEqual(len(messages), 1)
        self.assertEqual(self.window.services_page.services, [])
        self.assertEqual(len(self.db.list_services()), 1)

    def test_numeric_ids_layout_shared_lists_and_demo_compatibility(self):
        self.add_car()
        self.add_service()
        w = self.window
        self.assertEqual(w.client_table.item(0, 0).text(), "КЛ-0002")
        self.assertEqual(w.car_table.item(0, 0).text(), "АВ-0001")
        self.assertEqual(w.services_page.table.item(0, 0).text(), "УС-0001")
        self.assertIs(type(w.cars[0]["owner_id"]), int)
        self.assertEqual(w.orders_page.orders, [])
        self.assertEqual(w.appointments_page.appointments, [])
        self.assertIs(w.orders_page.clients, w.clients)
        self.assertIs(w.orders_page.cars, w.cars)
        self.assertIs(w.orders_page.services, w.services_page.services)
        self.assertIs(w.appointments_page.cars, w.cars)
        for section, table in (("clients", w.client_table), ("car", w.car_table), ("services", w.services_page.table)):
            w.show_section(section)
            QTest.qWait(10)
            self.assertEqual((w.width(), w.height()), (1280, 720))
            self.assertEqual(table.horizontalScrollBar().maximum(), 0)
            self.assertIsInstance(table.itemDelegate(), RowSelectionDelegate)
            self.assertEqual(table.rowHeight(0), 43)
            self.assertEqual(w.nav_buttons[section].objectName(), "activeNav")
        demo = MainWindow()
        try:
            self.assertEqual(demo.clients, CLIENTS)
            self.assertEqual(demo.cars, CARS)
            self.assertEqual(demo.services_page.services, SERVICES)
            self.assertEqual(len(demo.orders_page.orders), 7)
            self.assertEqual(len(demo.appointments_page.appointments), 7)
            self.assertIsNone(demo.database)
            self.assertEqual(demo.minimumSize(), w.minimumSize())
            self.assertEqual(self.app.styleSheet(), STYLE)
        finally:
            demo.close()

    def test_standalone_services_page_loads_without_main_window(self):
        self.db.add_service("Диагностика", "Диагностика", 0)
        page = ServicesPage(database=self.db)
        self.assertEqual(page.services, self.db.list_services())
        self.assertEqual(page.total.text(), "1")
        page.close()


if __name__ == "__main__":
    unittest.main()
