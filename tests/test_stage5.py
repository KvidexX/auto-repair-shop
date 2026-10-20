"""Проверки расписания, бронирования и ссылок на единые справочники."""

import copy
from datetime import datetime, timedelta, time
from pathlib import Path
from unittest.mock import patch
import unittest

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QMessageBox

from autoservice.appointments import AppointmentDialog, PLANNED, CANCELLED, SLOTS, local_now, qt_date
from main import ClientDialog, CarDialog
from tests import test_stage4 as helpers


# Переиспользуем только тестовые помощники, а не сценарии прошлых этапов.
class AppointmentsTests(unittest.TestCase):
    setUpClass = classmethod(helpers.ServicesTests.setUpClass.__func__)
    setUp = helpers.ServicesTests.setUp
    tearDown = helpers.ServicesTests.tearDown
    modal = helpers.ServicesTests.modal
    read_orders = helpers.ServicesTests.read_orders

    def setup_page(self):
        self.window.show_section("calendar")
        return self.window.appointments_page

    def fill(self, dialog, car_id=1, day=None, slot=time(16, 0)):
        car = next(c for c in self.window.cars if c["id"] == car_id)
        dialog.client_input.setCurrentIndex(dialog.client_input.findData(car["owner_id"]))
        dialog.car_input.setCurrentIndex(dialog.car_input.findData(car_id))
        dialog.date_input.setDate(qt_date(day or (local_now().date() + timedelta(days=5))))
        dialog.time_input.setCurrentIndex(dialog.time_input.findData(slot.strftime("%H:%M")))
        dialog.reason_input.setText("Проверка перед поездкой")

    def choose(self, page, appointment_id):
        row = next(r for r in range(page.table.rowCount())
                   if page.table.item(r, 0).data(Qt.ItemDataRole.UserRole) == appointment_id)
        page.table.selectRow(row)

    def test_owner_car_picker_and_validation(self):
        p = self.setup_page()
        dialog = AppointmentDialog(self.window.clients, self.window.cars, p.appointments, self.window)
        self.assertFalse(dialog.car_input.isEnabled())
        dialog.client_input.setCurrentIndex(dialog.client_input.findData(2))
        self.assertEqual([dialog.car_input.itemData(i) for i in range(1, dialog.car_input.count())], [2, 8])
        dialog.car_input.setCurrentIndex(1)
        dialog.client_input.setCurrentIndex(dialog.client_input.findData(1))
        self.assertIsNone(dialog.car_input.currentData())
        self.assertEqual(dialog.car_input.count(), 2)
        self.fill(dialog)
        # Проверка не ограничивается содержимым списка: чужой ID отклоняется.
        dialog.car_input.addItem("Чужой автомобиль", 2)
        dialog.car_input.setCurrentIndex(dialog.car_input.count() - 1)
        dialog.save_button.click()
        self.assertIn("автомобиль выбранного", dialog.error.text())
        for field, value, error in [("reason_input", "   ", "причину"),
                                    ("client_input", 0, "клиента"),
                                    ("time_input", 0, "30 минут")]:
            self.fill(dialog)
            if isinstance(value, int):
                getattr(dialog, field).setCurrentIndex(value)
            else:
                getattr(dialog, field).setText(value)
            dialog.save_button.click()
            self.assertIn(error, dialog.error.text())
        self.fill(dialog)
        dialog.date_input.setDate(qt_date(local_now().date() - timedelta(days=1)))
        dialog.save_button.click()
        self.assertIn("прошедшие", dialog.error.text())
        for invalid in (time(8, 30), time(18, 30), time(9, 15)):
            self.fill(dialog)
            dialog.time_input.addItem("Неверное время", invalid.strftime("%H:%M"))
            dialog.time_input.setCurrentIndex(dialog.time_input.count() - 1)
            dialog.save_button.click()
            self.assertIn("30 минут", dialog.error.text())
        self.assertEqual(len(SLOTS), 19)
        for valid in (time(9, 0), time(18, 0)):
            self.fill(dialog, slot=valid)
            dialog.save_button.click()
            self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)

    def test_past_today_and_booking_conflicts(self):
        p = self.setup_page()
        now = local_now().replace(hour=12, minute=15, second=0, microsecond=0)
        dialog = AppointmentDialog(self.window.clients, self.window.cars, p.appointments, self.window)
        with patch("autoservice.appointments.local_now", return_value=now):
            self.fill(dialog, day=now.date(), slot=time(12, 0))
            dialog.save_button.click()
            self.assertIn("прошедшие", dialog.error.text())
            self.fill(dialog, day=now.date(), slot=time(12, 30))
            dialog.save_button.click()
            self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        occupied = p.appointments[0]
        self.fill(dialog, car_id=2, day=occupied["date"], slot=occupied["time"])
        dialog.save_button.click()
        self.assertIn("уже занято", dialog.error.text())
        self.assertNotEqual(dialog.error.text(), "")
        unchanged = AppointmentDialog(self.window.clients, self.window.cars, p.appointments, self.window, occupied)
        unchanged.save_button.click()
        self.assertEqual(unchanged.result(), QDialog.DialogCode.Accepted)
        canceled = next(a for a in p.appointments if a["status"] == CANCELLED)
        fresh = AppointmentDialog(self.window.clients, self.window.cars, p.appointments, self.window)
        self.fill(fresh, day=canceled["date"], slot=canceled["time"])
        fresh.save_button.click()
        self.assertEqual(fresh.result(), QDialog.DialogCode.Accepted)

    def test_create_edit_cancel_release_slot_and_view(self):
        p = self.setup_page()
        day = local_now().date() + timedelta(days=5)
        def create(dialog):
            self.fill(dialog, day=day)
            dialog.note_input.setPlainText("Примечание для просмотра")
            dialog.save_button.click()
        self.modal(create)
        p.add_button.click()
        record = p.selected_appointment()
        self.assertEqual(record["id"], 8)
        self.assertEqual(record["status"], PLANNED)
        self.assertEqual(record["car_id"], 1)
        self.assertNotIn("client_id", record)
        self.assertNotIn("name", record)
        def edit(dialog):
            self.fill(dialog, car_id=2, day=day, slot=time(16, 30))
            dialog.reason_input.setText("Новая причина")
            dialog.save_button.click()
        self.modal(edit)
        p.edit_button.click()
        self.assertEqual(record["id"], 8)
        self.assertEqual(record["car_id"], 2)
        self.assertEqual(record["reason"], "Новая причина")
        before = copy.deepcopy(p.appointments)
        self.modal(lambda d: d.cancel_button.click())
        p.add_button.click()
        def cancel_form(dialog):
            dialog.reason_input.setText("Не сохранять")
            QTest.keyClick(dialog, Qt.Key.Key_Escape)
        self.modal(cancel_form)
        p.edit_button.click()
        self.assertEqual(p.appointments, before)
        def answer(dialog, text):
            self.assertIsInstance(dialog, QMessageBox)
            next(b for b in dialog.buttons() if b.text() == text).click()
        self.modal(lambda d: answer(d, "Назад"))
        p.cancel_button.click()
        self.assertEqual(record["status"], PLANNED)
        self.modal(lambda d: answer(d, "Отменить запись"))
        p.cancel_button.click()
        self.assertEqual(record["status"], CANCELLED)
        self.assertEqual(len(p.appointments), 8)
        self.assertFalse(p.edit_button.isEnabled())
        self.assertFalse(p.cancel_button.isEnabled())
        def view(dialog):
            self.assertTrue(dialog.read_only)
            self.assertTrue(dialog.note_input.isReadOnly())
            self.assertEqual(dialog.note_input.toPlainText(), "Примечание для просмотра")
            self.assertFalse(dialog.save_button.isVisible())
            dialog.cancel_button.click()
        self.modal(view)
        p.open_appointment()
        def reuse(dialog):
            self.fill(dialog, car_id=3, day=day, slot=time(16, 30))
            dialog.save_button.click()
        self.modal(reuse)
        p.add_button.click()
        self.assertEqual(p.selected_appointment()["id"], 9)
        self.assertEqual(p.selected_appointment()["status"], PLANNED)

    def test_filter_sort_layout_and_screenshots(self):
        p = self.setup_page()
        self.assertIs(p.clients, self.window.clients)
        self.assertIs(p.cars, self.window.cars)
        self.assertEqual({a["status"] for a in p.appointments}, {PLANNED, CANCELLED})
        self.assertTrue(all(a["date"] > local_now().date() for a in p.appointments))
        self.assertEqual(p.table.horizontalScrollBar().maximum(), 0)
        self.assertEqual((self.window.width(), self.window.height()), (1280, 720))
        p.appointments.reverse()
        p.refresh()
        ids = [p.table.item(r, 0).data(Qt.ItemDataRole.UserRole) for r in range(p.table.rowCount())]
        self.assertEqual(ids, [a["id"] for a in sorted(p.appointments, key=lambda a: (a["date"], a["time"], a["id"]))])
        p.all_dates.setChecked(False)
        p.date_filter.setDate(qt_date(local_now().date() + timedelta(days=1)))
        self.assertEqual(p.table.rowCount(), 3)
        p.date_filter.setDate(qt_date(local_now().date() + timedelta(days=100)))
        self.assertEqual(p.table.rowCount(), 0)
        self.assertTrue(p.empty.isVisible())
        p.all_dates.setChecked(True)
        self.assertEqual(p.table.rowCount(), 7)
        p.date_filter.setDate(qt_date(local_now().date() + timedelta(days=1)))
        self.choose(p, 2)
        self.window.nav_buttons["services"].click()
        self.window.nav_buttons["calendar"].click()
        self.assertEqual(self.window.pages.currentIndex(), 4)
        self.assertEqual(p.selected_appointment()["id"], 2)
        self.assertEqual(self.window.nav_buttons["calendar"].objectName(), "activeNav")
        self.assertTrue(self.window.nav_buttons["history"].isEnabled())
        output = Path(__file__).resolve().parents[1] / "screenshots"
        self.assertTrue(self.window.grab().save(str(output / "appointments.png"), "PNG"))
        dialog = AppointmentDialog(self.window.clients, self.window.cars, p.appointments, self.window)
        dialog.show()
        QTest.qWait(50)
        self.assertTrue(self.window.frameGeometry().contains(dialog.frameGeometry()))
        self.assertLess(dialog.frameGeometry().height(), 680)
        self.assertTrue(dialog.rect().contains(dialog.save_button.geometry()))
        self.assertTrue(dialog.grab().save(str(output / "new_appointment.png"), "PNG"))
        dialog.reject()

    def test_live_links_and_car_deletion_guards(self):
        p, w = self.setup_page(), self.window
        before_cars, before_clients = copy.deepcopy(w.cars), copy.deepcopy(w.clients)
        w.show_section("clients")
        w.client_table.selectRow(0)
        def rename(dialog):
            self.assertIsInstance(dialog, ClientDialog)
            dialog.name_input.setText("Переименован Новый Владелец")
            dialog.save_button.click()
        self.modal(rename)
        w.edit_client_button.click()
        self.assertIn("Переименован", p.table.item(0, 4).text())
        w.show_section("car")
        w.car_table.selectRow(0)
        def transfer(dialog):
            self.assertIsInstance(dialog, CarDialog)
            dialog.owner_input.setCurrentIndex(dialog.owner_input.findData(2))
            dialog.brand_input.setText("Honda")
            dialog.plate_input.setText("Е111АА125")
            dialog.save_button.click()
        self.modal(transfer)
        w.edit_car_button.click()
        self.assertIn("Honda", p.table.item(0, 3).text())
        self.assertIn("Е111АА125", p.table.item(0, 3).text())
        self.assertIn("Соколова", p.table.item(0, 4).text())
        self.assertEqual(p.appointments[0]["car_id"], 1)
        for car_id, message in [(1, "активные"), (3, "отменённые")]:
            row = next(r for r in range(w.car_table.rowCount()) if w.car_table.item(r, 0).data(Qt.ItemDataRole.UserRole) == car_id)
            w.car_table.selectRow(row)
            def blocked(dialog, expected=message):
                self.assertIn(expected, dialog.text())
                dialog.buttons()[0].click()
            self.modal(blocked)
            w.delete_car_button.click()
            self.assertEqual(len(w.cars), 9)
        # Восстанавливаем справочники перед общими проверками неизменности заказов.
        w.cars[:] = before_cars
        w.clients[:] = before_clients
        self.previous = copy.deepcopy((w.clients, w.cars, w.orders_page.orders))


if __name__ == "__main__":
    unittest.main()
