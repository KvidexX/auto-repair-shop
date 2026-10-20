"""Расписание: Qt-формы, транзакции и временные SQLite-базы."""

import copy
from contextlib import contextmanager
from datetime import datetime, time, timedelta
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox, QDialog

from autoservice.appointments import AppointmentDialog, PLANNED, CANCELLED, SLOTS, qt_date
from autoservice.data import local_now
from autoservice.database import Database
from main import MainWindow
from tests import test_orders_sqlite as helpers


class AppointmentsSqliteTests(unittest.TestCase):
    setUpClass = classmethod(helpers.OrdersSqliteTests.setUpClass.__func__)
    modal = helpers.OrdersSqliteTests.modal
    choose = helpers.OrdersSqliteTests.choose
    notices = helpers.OrdersSqliteTests.notices

    def setUp(self):
        root = Path(__file__).resolve().parents[1] / ".tmp"
        root.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="appointments-test-", dir=root)
        self.path = Path(self.temporary.name) / "test.db"
        self.db = Database(self.path)
        discarded = self.db.add_client("Удалённый", "0")
        self.db.delete_client(discarded["id"])
        self.client = self.db.add_client("Вера Записанная", "89991112233")
        self.other = self.db.add_client("Борис Второй", "89992223344")
        discarded = self.db.add_car(self.client["id"], "Удалённая", "Машина", "А001АА125")
        self.db.delete_car(discarded["id"])
        self.car = self.db.add_car(self.client["id"], "Honda", "Fit", "Е111АА125", 2018)
        self.other_car = self.db.add_car(self.other["id"], "Toyota", "Yaris", "А222АА125")
        self.service = self.db.add_service("Диагностика", "Диагностика", 800)
        self.day = local_now().date() + timedelta(days=5)
        self.window = MainWindow(database=self.db)
        self.window.centralWidget().setObjectName("central")
        self.window.show()
        self.window.show_section("calendar")
        self.page = self.window.appointments_page
        self.errors = []
        QTest.qWait(15)

    def tearDown(self):
        self.window.close()
        self.db.close()
        self.temporary.cleanup()
        self.assertFalse(self.errors, self.errors)

    def fill(self, dialog, day=None, slot=time(10), car=None):
        car = car or self.car
        dialog.client_input.setCurrentIndex(dialog.client_input.findData(car["owner_id"]))
        dialog.car_input.setCurrentIndex(dialog.car_input.findData(car["id"]))
        dialog.date_input.setDate(qt_date(day or self.day))
        dialog.time_input.setCurrentIndex(dialog.time_input.findData(slot.strftime("%H:%M")))
        dialog.reason_input.setText("Проверка перед поездкой")
        dialog.note_input.setPlainText("Позвонить при приёмке")

    def create(self, day=None, slot=time(10), car=None):
        def submit(dialog):
            self.fill(dialog, day, slot, car)
            dialog.save_button.click()
        self.modal(submit)
        self.page.add_button.click()
        return self.page.selected_appointment()

    def reopen(self):
        self.window.close()
        self.db.close()
        self.db = Database(self.path)
        self.window = MainWindow(database=self.db)
        self.window.show()
        self.window.show_section("calendar")
        self.page = self.window.appointments_page
        QTest.qWait(15)

    def cancel(self, confirm=True):
        def answer(box):
            self.assertIsInstance(box, QMessageBox)
            next(b for b in box.buttons() if b.text() == ("Отменить запись" if confirm else "Назад")).click()
        self.modal(answer)
        self.page.cancel_button.click()

    @contextmanager
    def reject_commit(self):
        def authorize(action, argument, *unused):
            return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_TRANSACTION and argument == "COMMIT" else sqlite3.SQLITE_OK
        self.db._connection.set_authorizer(authorize)
        try:
            yield
        finally:
            self.db._connection.set_authorizer(None)

    def test_empty_database_and_shared_reference_lists(self):
        self.assertEqual(self.page.appointments, [])
        self.assertEqual(self.page.total.text(), "0")
        self.assertTrue(self.page.empty.isVisible())
        self.assertFalse(self.page.edit_button.isEnabled())
        self.assertFalse(self.page.cancel_button.isEnabled())
        self.assertIsNone(self.page.next_id)
        self.assertIs(self.page.clients, self.window.clients)
        self.assertIs(self.page.cars, self.window.cars)
        with Database(Path(self.temporary.name) / "empty.db") as empty:
            window = MainWindow(database=empty)
            try:
                self.assertEqual(window.clients, [])
                self.assertEqual(window.cars, [])
                self.assertEqual(window.appointments_page.appointments, [])
                self.assertEqual(window.orders_page.orders, [])
            finally:
                window.close()

    def test_create_form_ids_types_note_and_restart(self):
        record = self.create()
        self.assertEqual(record, self.db.get_appointment(record["id"]))
        self.assertEqual(record["id"], 1)
        self.assertEqual(record["car_id"], self.car["id"])
        self.assertIs(type(record["car_id"]), int)
        self.assertEqual(set(record), {"id", "car_id", "date", "time", "reason", "note", "status"})
        self.assertEqual(record["date"], self.day)
        self.assertEqual(record["time"], time(10))
        self.assertEqual(record["note"], "Позвонить при приёмке")
        self.assertEqual(record["status"], PLANNED)
        self.assertEqual(self.page.table.item(0, 0).text(), "ЗП-0001")
        self.reopen()
        self.assertEqual(self.page.appointments, [record])
        second = self.create(slot=time(11))
        self.assertEqual(second["id"], 2)
        self.assertIsNone(self.page.next_id)

    def test_edit_full_fields_preserves_id_and_resets_car_on_client_change(self):
        first = self.create()
        def edit(dialog):
            self.assertEqual(dialog.car_input.currentData(), self.car["id"])
            dialog.client_input.setCurrentIndex(dialog.client_input.findData(self.other["id"]))
            self.assertIsNone(dialog.car_input.currentData())
            self.assertEqual(dialog.car_input.itemData(1), self.other_car["id"])
            dialog.car_input.addItem("Чужой автомобиль", self.car["id"])
            dialog.car_input.setCurrentIndex(dialog.car_input.count() - 1)
            dialog.save_button.click()
            self.assertIn("автомобиль выбранного клиента", dialog.error.text())
            self.fill(dialog, day=self.day + timedelta(days=1), slot=time(18), car=self.other_car)
            dialog.reason_input.setText("Изменённая причина")
            dialog.note_input.setPlainText("Новое примечание")
            dialog.save_button.click()
        self.modal(edit)
        self.page.edit_button.click()
        record = self.page.selected_appointment()
        self.assertEqual(record["id"], first["id"])
        self.assertEqual(record["car_id"], self.other_car["id"])
        self.assertEqual(record["time"], time(18))
        self.assertEqual(record["note"], "Новое примечание")
        self.reopen()
        self.assertEqual(self.page.appointments, [record])

    def test_own_slot_is_available_and_old_active_time_can_be_kept(self):
        record = self.create()
        future = datetime.combine(self.day + timedelta(days=1), time(12))
        def edit(dialog):
            dialog.reason_input.setText("Исправленная причина старой записи")
            dialog.note_input.setPlainText("Исправленное примечание")
            dialog.time_input.setCurrentIndex(dialog.time_input.findData("10:30"))
            dialog.save_button.click()
            self.assertIn("прошедшие", dialog.error.text())
            dialog.time_input.setCurrentIndex(dialog.time_input.findData("10:00"))
            dialog.save_button.click()
        with patch("autoservice.appointments.local_now", return_value=future), patch("autoservice.database.local_now", return_value=future):
            self.modal(edit)
            self.page.edit_button.click()
        changed = self.db.get_appointment(record["id"])
        self.assertEqual(changed["date"], record["date"])
        self.assertEqual(changed["time"], record["time"])
        self.assertEqual(changed["reason"], "Исправленная причина старой записи")
        self.assertEqual(changed["note"], "Исправленное примечание")

    def test_cancel_confirmation_restart_readonly_and_released_slot(self):
        record = self.create()
        self.cancel(confirm=False)
        self.assertEqual(self.db.get_appointment(record["id"]), record)
        self.assertEqual(self.page.selected_appointment(), record)
        self.cancel()
        cancelled = self.page.selected_appointment()
        self.assertEqual(cancelled["status"], CANCELLED)
        self.assertEqual(len(self.page.appointments), 1)
        self.assertFalse(self.page.edit_button.isEnabled())
        self.assertFalse(self.page.cancel_button.isEnabled())
        with patch.object(QMessageBox, "exec") as show:
            self.page.cancel_appointment()
            self.page.edit_appointment()
        show.assert_not_called()
        self.reopen()
        self.assertEqual(self.page.appointments, [cancelled])
        self.choose(self.page.table, cancelled["id"])
        def inspect(dialog):
            self.assertTrue(dialog.read_only)
            self.assertEqual(dialog.note_input.toPlainText(), record["note"])
            self.assertTrue(dialog.note_input.isReadOnly())
            self.assertFalse(dialog.save_button.isVisible())
            dialog.validate_and_accept()
            self.assertNotEqual(dialog.result(), QDialog.DialogCode.Accepted)
            dialog.cancel_button.click()
        QTest.qWait(30)
        point = self.page.table.visualItemRect(self.page.table.item(0, 0)).center()
        QTest.mouseClick(self.page.table.viewport(), Qt.MouseButton.LeftButton, pos=point)
        self.modal(inspect)
        QTest.mouseDClick(self.page.table.viewport(), Qt.MouseButton.LeftButton, pos=point)
        replacement = self.create()
        self.assertGreater(replacement["id"], cancelled["id"])
        self.assertEqual(replacement["time"], cancelled["time"])
        self.reopen()
        self.assertEqual({a["status"] for a in self.page.appointments}, {PLANNED, CANCELLED})

    def test_form_cancel_new_and_edit_changes_nothing(self):
        def abandon(dialog):
            self.fill(dialog)
            dialog.cancel_button.click()
        self.modal(abandon)
        self.page.add_appointment()
        self.assertEqual(self.db.list_appointments(), [])
        record = self.create()
        def abandon_edit(dialog):
            dialog.reason_input.setText("Не сохранять")
            dialog.cancel_button.click()
        self.modal(abandon_edit)
        self.page.edit_button.click()
        self.assertEqual(self.db.list_appointments(), [record])

    def test_duplicate_slot_blocked_by_form_and_database(self):
        record = self.create()
        def duplicate(dialog):
            self.fill(dialog, car=self.other_car)
            dialog.save_button.click()
            self.assertIn("уже занято", dialog.error.text())
            self.assertTrue(dialog.isVisible())
            dialog.cancel_button.click()
        self.modal(duplicate)
        self.page.add_appointment()
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.add_appointment(self.other_car["id"], self.day, time(10), "Дубль")
        self.assertEqual(self.db.list_appointments(), [record])

    def test_second_connection_conflict_preserves_form_and_allows_retry(self):
        def submit(dialog):
            self.fill(dialog)
            before = dialog.values()
            with Database(self.path) as other:
                other.add_appointment(self.other_car["id"], self.day, time(10), "Другое соединение")
            with self.notices() as messages:
                dialog.save_button.click()
            self.assertEqual(len(messages), 1)
            self.assertIn("время уже занято", messages[0][0])
            self.assertEqual(dialog.values(), before)
            self.assertTrue(dialog.isVisible())
            self.assertEqual(self.page.appointments, [])
            self.assertEqual(self.page.total.text(), "0")
            dialog.time_input.setCurrentIndex(dialog.time_input.findData("10:30"))
            dialog.save_button.click()
        self.modal(submit)
        self.page.add_appointment()
        self.assertEqual(self.page.appointments, self.db.list_appointments())
        self.assertEqual(self.page.total.text(), "2")

    def test_past_today_boundaries_and_model_recheck(self):
        now = local_now().replace(hour=12, minute=15, second=0, microsecond=0)
        def validate(dialog):
            for day, slot in ((now.date() - timedelta(days=1), time(18)), (now.date(), time(12))):
                self.fill(dialog, day, slot)
                dialog.save_button.click()
                self.assertIn("прошедшие", dialog.error.text())
            for slot in ("08:30", "18:30", "09:15"):
                self.fill(dialog)
                dialog.time_input.addItem("Неверное время", slot)
                dialog.time_input.setCurrentIndex(dialog.time_input.count() - 1)
                dialog.save_button.click()
                self.assertIn("30 минут", dialog.error.text())
            self.fill(dialog, now.date(), time(12, 30))
            dialog.save_button.click()
        with patch("autoservice.appointments.local_now", return_value=now), patch("autoservice.database.local_now", return_value=now):
            self.modal(validate)
            self.page.add_appointment()
        self.assertEqual(self.db.list_appointments()[0]["time"], time(12, 30))
        self.assertEqual(len(SLOTS), 19)
        self.create(slot=time(9))
        self.create(slot=time(18))
        for invalid in (time(8, 30), time(18, 30), time(9, 15)):
            with self.assertRaises(ValueError):
                self.db.add_appointment(self.car["id"], self.day, invalid, "Неверное время")
        # UI sees an earlier moment; SQLite still rejects a slot that has since passed.
        def stale_clock(dialog):
            self.fill(dialog, now.date(), time(13))
            with patch("autoservice.database.local_now", return_value=now.replace(hour=14)):
                with self.notices() as messages:
                    dialog.save_button.click()
            self.assertEqual(len(messages), 1)
            self.assertIn("прошлом", messages[0][0])
            self.assertTrue(dialog.isVisible())
            dialog.cancel_button.click()
        with patch("autoservice.appointments.local_now", return_value=now):
            self.modal(stale_clock)
            self.page.add_appointment()

    def test_filter_sort_selection_and_successful_reschedule(self):
        later = self.create(day=self.day + timedelta(days=1), slot=time(15))
        early = self.create(slot=time(9))
        mid = self.create(slot=time(11))
        ids = [self.page.table.item(r, 0).data(Qt.ItemDataRole.UserRole) for r in range(3)]
        self.assertEqual(ids, [early["id"], mid["id"], later["id"]])
        self.page.date_filter.setDate(qt_date(self.day))
        self.page.all_dates.setChecked(False)
        self.assertEqual(self.page.table.rowCount(), 2)
        self.choose(self.page.table, mid["id"])
        def edit(dialog):
            dialog.date_input.setDate(qt_date(self.day + timedelta(days=2)))
            dialog.save_button.click()
        self.modal(edit)
        self.page.edit_button.click()
        self.assertFalse(self.page.all_dates.isChecked())
        self.assertEqual(self.page.date_filter.date().toPython(), self.day + timedelta(days=2))
        self.assertEqual(self.page.table.rowCount(), 1)
        self.assertEqual(self.page.selected_appointment()["id"], mid["id"])
        self.cancel()
        self.assertEqual(self.page.selected_appointment()["status"], CANCELLED)
        self.page.all_dates.setChecked(True)
        self.assertEqual(self.page.table.rowCount(), 3)

    def test_reference_rename_car_details_owner_transfer_and_delete_guards(self):
        record = self.create()
        self.choose(self.window.client_table, self.client["id"])
        def rename(dialog):
            dialog.name_input.setText("Вера Переименована")
            dialog.save_button.click()
        self.modal(rename)
        self.window.edit_client()
        self.assertIn("Вера Переименована", self.page.table.item(0, 4).text())
        self.choose(self.window.car_table, self.car["id"])
        def transfer(dialog):
            dialog.owner_input.setCurrentIndex(dialog.owner_input.findData(self.other["id"]))
            dialog.brand_input.setText("Nissan")
            dialog.model_input.setText("Note")
            dialog.plate_input.setText("Н333НН125")
            dialog.save_button.click()
        self.modal(transfer)
        self.window.edit_car()
        self.assertIn("Nissan Note", self.page.table.item(0, 3).text())
        self.assertIn("Н333НН125", self.page.table.item(0, 3).text())
        self.assertIn("Борис Второй", self.page.table.item(0, 4).text())
        for cancelled in (False, True):
            if cancelled:
                self.cancel()
            def dismiss(box):
                self.assertIn("запис", box.text())
                box.buttons()[0].click()
            self.modal(dismiss)
            self.window.delete_car()
            with self.assertRaises(sqlite3.IntegrityError):
                self.db.delete_car(self.car["id"])
        self.reopen()
        self.assertEqual(self.page.appointments[0]["id"], record["id"])
        self.assertIn("Борис Второй", self.page.table.item(0, 4).text())

    def test_owner_changed_in_another_connection_is_rechecked(self):
        def submit(dialog):
            self.fill(dialog)
            with Database(self.path) as other:
                other.update_car(self.car["id"], self.other["id"], self.car["brand"], self.car["model"], self.car["plate"])
            with self.notices() as messages:
                dialog.save_button.click()
            self.assertEqual(len(messages), 1)
            self.assertIn("Владелец автомобиля изменился", messages[0][0])
            self.assertTrue(dialog.isVisible())
            self.assertEqual(self.db.list_appointments(), [])
            dialog.cancel_button.click()
        self.modal(submit)
        self.page.add_appointment()

    def test_failed_insert_preserves_form_and_retry(self):
        self.db._connection.execute("CREATE TRIGGER deny_booking BEFORE INSERT ON appointments BEGIN SELECT RAISE(ABORT,'booking denied'); END")
        def submit(dialog):
            self.fill(dialog)
            before = dialog.values()
            with self.notices() as messages:
                dialog.save_button.click()
            self.assertEqual(len(messages), 1)
            self.assertEqual(dialog.values(), before)
            self.assertTrue(dialog.isVisible())
            self.assertEqual(self.page.appointments, [])
            self.assertEqual(self.db.list_appointments(), [])
            self.db._connection.execute("DROP TRIGGER deny_booking")
            dialog.save_button.click()
        self.modal(submit)
        self.page.add_appointment()
        self.assertEqual(len(self.page.appointments), 1)

    def test_failed_edit_preserves_filter_selection_and_inputs(self):
        record = self.create()
        self.page.date_filter.setDate(qt_date(self.day))
        self.page.all_dates.setChecked(False)
        self.db._connection.execute("CREATE TRIGGER deny_booking_edit BEFORE UPDATE ON appointments BEGIN SELECT RAISE(ABORT,'edit denied'); END")
        def edit(dialog):
            dialog.reason_input.setText("Не потерять причину")
            before = dialog.values()
            with self.notices() as messages:
                dialog.save_button.click()
            self.assertEqual(len(messages), 1)
            self.assertEqual(dialog.values(), before)
            self.assertTrue(dialog.isVisible())
            self.assertEqual(self.page.selected_appointment(), record)
            self.assertEqual(self.page.table.item(0, 5).text(), record["reason"])
            self.assertEqual(self.db.get_appointment(record["id"]), record)
            self.assertFalse(self.page.all_dates.isChecked())
            self.assertEqual(self.page.date_filter.date().toPython(), self.day)
            dialog.cancel_button.click()
        self.modal(edit)
        self.page.edit_button.click()

    def test_failed_cancel_keeps_status_and_actions(self):
        record = self.create()
        self.db._connection.execute("CREATE TRIGGER deny_booking_cancel BEFORE UPDATE ON appointments BEGIN SELECT RAISE(ABORT,'cancel denied'); END")
        with self.notices() as messages:
            self.cancel()
        self.assertEqual(len(messages), 1)
        self.assertEqual(self.page.selected_appointment(), record)
        self.assertEqual(self.page.table.item(0, 6).text(), PLANNED)
        self.assertTrue(self.page.edit_button.isEnabled())
        self.assertTrue(self.page.cancel_button.isEnabled())
        self.assertEqual(self.db.get_appointment(record["id"]), record)

    def test_commit_failure_does_not_create_or_cancel_appointment(self):
        def submit(dialog):
            self.fill(dialog)
            with self.reject_commit(), self.notices() as messages:
                dialog.save_button.click()
            self.assertEqual(len(messages), 1)
            self.assertTrue(dialog.isVisible())
            self.assertEqual(self.page.appointments, [])
            self.assertEqual(self.db.list_appointments(), [])
            dialog.save_button.click()
        self.modal(submit)
        self.page.add_appointment()
        before = copy.deepcopy(self.page.selected_appointment())
        with self.reject_commit(), self.notices() as messages:
            self.cancel()
        self.assertEqual(len(messages), 1)
        self.assertEqual(self.db.get_appointment(before["id"]), before)
        self.assertEqual(self.page.selected_appointment(), before)
        self.assertEqual(self.page.table.item(0, 6).text(), PLANNED)

    def test_refresh_failure_rolls_back_and_locked_database_preserves_form(self):
        def submit(dialog):
            self.fill(dialog)
            before = dialog.values()
            with patch.object(self.db, "list_appointments", side_effect=sqlite3.OperationalError("read failed")):
                with self.notices() as messages:
                    dialog.save_button.click()
            self.assertEqual(len(messages), 1)
            self.assertEqual(self.db.list_appointments(), [])
            self.assertEqual(self.page.appointments, [])
            self.db._connection.execute("PRAGMA busy_timeout=0")
            with Database(self.path) as other:
                with other.transaction():
                    with self.notices() as messages:
                        dialog.save_button.click()
            self.assertEqual(len(messages), 1)
            self.assertIn("SQLite", messages[0][0])
            self.assertEqual(dialog.values(), before)
            self.assertTrue(dialog.isVisible())
            dialog.cancel_button.click()
        self.modal(submit)
        self.page.add_appointment()
        self.assertEqual(self.db.list_appointments(), [])

    def test_all_six_sections_restore_without_regressions(self):
        orders = self.window.orders_page
        def create_order(dialog):
            dialog.client_input.setCurrentIndex(dialog.client_input.findData(self.client["id"]))
            dialog.car_input.setCurrentIndex(dialog.car_input.findData(self.car["id"]))
            dialog.reason_input.setText("Обслуживание")
            dialog.service_input.setCurrentIndex(dialog.service_input.findData(self.service["id"]))
            dialog.add_item_button.click()
            dialog.save_button.click()
        self.modal(create_order)
        orders.add_order()
        def complete(card):
            for _ in range(3):
                card.next_button.click()
            card.close_button.click()
        self.modal(complete)
        orders.open_order()
        before = copy.deepcopy((self.window.clients, self.window.cars, self.window.services_page.services, orders.orders))
        self.create()
        self.cancel()
        self.create(slot=time(11))
        appointments = copy.deepcopy(self.page.appointments)
        self.reopen()
        self.assertEqual((self.window.clients, self.window.cars, self.window.services_page.services, self.window.orders_page.orders), before)
        self.assertEqual(self.page.appointments, appointments)
        self.assertIs(self.window.history_page.orders, self.window.orders_page.orders)
        self.assertEqual(self.window.history_page.total.text(), "1")
        for section in ("clients", "car", "services", "calendar", "orders", "history"):
            self.window.show_section(section)
            QTest.qWait(10)
            self.assertEqual(self.window.nav_buttons[section].objectName(), "activeNav")
            self.assertEqual((self.window.width(), self.window.height()), (1280, 720))
        demo = MainWindow()
        try:
            self.assertIsNone(demo.database)
            self.assertEqual(len(demo.appointments_page.appointments), 7)
        finally:
            demo.close()


if __name__ == "__main__":
    unittest.main()
