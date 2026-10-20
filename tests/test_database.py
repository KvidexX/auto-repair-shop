"""Постоянное хранение проверяется только на изолированных временных базах."""

import copy
from datetime import datetime, time, timedelta
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from autoservice.database import Database, TABLES, default_database_path, load_demo_data
from autoservice.data import CARS, CLIENTS, SERVICES, LOCAL_TIMEZONE, local_now, make_orders


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        temp_root = Path(__file__).resolve().parents[1] / ".tmp"
        temp_root.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="sqlite-test-", dir=temp_root)
        self.path = Path(self.temporary.name) / "nested" / "test.db"
        self.db = Database(self.path)
        self.tomorrow = local_now().date() + timedelta(days=1)

    def tearDown(self):
        self.db.close()
        self.temporary.cleanup()

    def reopen(self):
        self.db.close()
        self.db = Database(self.path)

    def fixtures(self):
        client = self.db.add_client("Тестов Илья Андреевич", "+7 (900) 000-00-99", "Примечание")
        car = self.db.add_car(client["id"], "Toyota", "Corolla", "А123ВС125", 2020, "12345678901234567", 12000)
        service = self.db.add_service("Диагностика", "Диагностика", 1500, 30, "Описание")
        return client, car, service

    def create_document(self):
        client, car, service = self.fixtures()
        order = self.db.add_order(client["id"], car["id"], [service["id"]], "Проверка автомобиля")
        return client, car, service, order

    def test_new_database_schema_and_safe_reinitialization(self):
        self.assertTrue(self.path.is_file())
        self.assertEqual(self.db._connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.assertEqual(self.db._connection.execute("PRAGMA user_version").fetchone()[0], 1)
        names = {r[0] for r in self.db._connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(names - {"sqlite_sequence"}, set(TABLES))
        self.assertNotIn("history", names)
        for table in TABLES:
            self.assertEqual(self.db._connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0], 0)
        self.reopen()
        self.assertEqual(self.db.list_clients(), [])
        self.assertEqual(self.db.list_orders(), [])

    def test_default_windows_location_is_overridable(self):
        with patch.dict("os.environ", {"LOCALAPPDATA": self.temporary.name}):
            expected = Path(self.temporary.name) / "AutoService" / "autoservice.db"
            self.assertEqual(default_database_path(), expected)
            with Database() as working:
                self.assertEqual(working.path, expected)
                self.assertEqual(working.list_clients(), [])
            self.assertTrue(expected.is_file())
        self.assertEqual(self.db.path, self.path)

    def test_clients_crud_and_parameterized_text(self):
        name = "О'Коннор'); DROP TABLE clients;--"
        client = self.db.add_client(name, "123", "Заметка")
        self.assertEqual(self.db.get_client(client["id"])["name"], name)
        changed = self.db.update_client(client["id"], "  Новое ФИО  ", "456", "Новое примечание")
        self.assertEqual(changed, {"id": client["id"], "name": "Новое ФИО", "phone": "456", "note": "Новое примечание"})
        self.reopen()
        self.assertEqual(self.db.list_clients(), [changed])
        self.db.delete_client(client["id"])
        self.assertEqual(self.db.list_clients(), [])

    def test_ids_survive_deletion_restart_and_multiple_connections(self):
        first = self.db.add_client("Первый", "1")
        self.db.delete_client(first["id"])
        self.reopen()
        second = self.db.add_client("Второй", "2")
        self.assertGreater(second["id"], first["id"])
        with Database(self.path) as other:
            third = other.add_client("Третий", "3")
            fourth = self.db.add_client("Четвёртый", "4")
            self.assertGreater(third["id"], second["id"])
            self.assertGreater(fourth["id"], third["id"])

    def test_car_ownership_counts_and_crud(self):
        owner, car, _ = self.fixtures()
        other = self.db.add_client("Другой владелец", "2")
        updated = self.db.update_car(car["id"], other["id"], "Honda", "Fit", "Е222АА125")
        self.assertEqual(updated["owner_id"], other["id"])
        self.assertEqual(self.db.car_count(owner["id"]), 0)
        self.assertEqual(self.db.car_count(other["id"]), 1)
        self.assertEqual(self.db.list_cars(owner["id"]), [])
        self.assertEqual(self.db.list_cars(other["id"]), [updated])
        self.reopen()
        self.assertEqual(self.db.get_car(car["id"]), updated)
        self.db.delete_client(owner["id"])
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.delete_client(other["id"])
        self.db.delete_car(car["id"])
        self.db.delete_client(other["id"])

    def test_car_validation_and_normalized_unique_plate(self):
        client, _, _ = self.fixtures()
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.add_car(client["id"], "Kia", "Rio", "a 123 bc-125")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.add_car(999, "Kia", "Rio", "Е222АА125")
        for kwargs in ({"year": 1899}, {"year": local_now().year + 2}, {"vin": "short"}, {"mileage": -1}, {"mileage": 1.5}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.db.add_car(client["id"], "Kia", "Rio", "Е222АА125", **kwargs)
        self.assertEqual(len(self.db.list_cars()), 1)

    def test_services_crud_unicode_duplicates_and_integer_money(self):
        service = self.db.add_service("  Замена   масла  ", "Техническое обслуживание", 0)
        self.assertEqual(service["name"], "Замена масла")
        self.assertIs(type(service["price"]), int)
        self.assertIsNone(service["duration"])
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.add_service("ЗАМЕНА  МАСЛА", "Ремонт", 100)
        for price in (-1, 100.5, True, "100"):
            with self.subTest(price=price), self.assertRaises(ValueError):
                self.db.add_service("Другая работа", "Ремонт", price)
        with self.assertRaises(ValueError):
            self.db.add_service("Другая работа", "Склад", 100)
        with self.assertRaises(ValueError):
            self.db.add_service("Другая работа", "Ремонт", 100, 0)
        changed = self.db.update_service(service["id"], service["name"], "Ремонт", 2000, 45, "Изменено")
        self.reopen()
        self.assertEqual(self.db.list_services(), [changed])
        self.db.delete_service(service["id"])
        replacement = self.db.add_service("Новая работа", "Ремонт", 1)
        self.assertGreater(replacement["id"], service["id"])

    def test_appointments_roundtrip_edit_cancel_and_retention(self):
        _, car, _ = self.fixtures()
        record = self.db.add_appointment(car["id"], self.tomorrow, time(9), "Причина", "Примечание")
        self.assertEqual(record["status"], "Запланирована")
        updated = self.db.update_appointment(record["id"], car["id"], self.tomorrow, time(10, 30), "Новая причина", "Новое примечание")
        self.reopen()
        self.assertEqual(self.db.list_appointments(), [updated])
        self.assertIs(type(updated["date"]), type(self.tomorrow))
        self.assertIs(type(updated["time"]), time)
        cancelled = self.db.cancel_appointment(record["id"])
        self.assertEqual(cancelled["status"], "Отменена")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.update_appointment(record["id"], car["id"], self.tomorrow, time(11), "Изменение")
        self.assertEqual(self.db.cancel_appointment(record["id"]), cancelled)
        self.reopen()
        self.assertEqual(self.db.get_appointment(record["id"]), cancelled)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.delete_car(car["id"])

    def test_global_booking_conflict_and_released_cancelled_slot(self):
        client, car, _ = self.fixtures()
        other = self.db.add_car(client["id"], "Kia", "Rio", "Е222АА125")
        first = self.db.add_appointment(car["id"], self.tomorrow, time(9), "Первый")
        with Database(self.path) as another:
            with self.assertRaises(sqlite3.IntegrityError):
                another.add_appointment(other["id"], self.tomorrow, time(9), "Второй")
        self.db.cancel_appointment(first["id"])
        second = self.db.add_appointment(other["id"], self.tomorrow, time(9), "Второй")
        self.assertGreater(second["id"], first["id"])
        self.assertEqual(len(self.db.list_appointments()), 2)

    def test_appointment_time_and_past_rules(self):
        _, car, _ = self.fixtures()
        for slot in (time(8, 30), time(18, 30), time(9, 15), time(9, 0, 1)):
            with self.subTest(slot=slot), self.assertRaises(ValueError):
                self.db.add_appointment(car["id"], self.tomorrow, slot, "Причина")
        with self.assertRaises(ValueError):
            self.db.add_appointment(car["id"], self.tomorrow - timedelta(days=2), time(9), "Причина")
        now = local_now().replace(hour=12, minute=15, second=0)
        with patch("autoservice.database.local_now", return_value=now):
            with self.assertRaises(ValueError):
                self.db.add_appointment(car["id"], now.date(), time(12), "Причина")
            self.db.add_appointment(car["id"], now.date(), time(12, 30), "Причина")
        for slot in (time(9), time(18)):
            self.db.add_appointment(car["id"], self.tomorrow, slot, "Причина")

    def test_past_active_appointment_can_keep_its_time_when_editing(self):
        _, car, _ = self.fixtures()
        record = self.db.add_appointment(car["id"], self.tomorrow, time(9), "Причина")
        future = datetime.combine(self.tomorrow + timedelta(days=1), time(12))
        with patch("autoservice.database.local_now", return_value=future):
            changed = self.db.update_appointment(record["id"], car["id"], self.tomorrow, time(9), "Исправлено")
            self.assertEqual(changed["reason"], "Исправлено")
            with self.assertRaises(ValueError):
                self.db.update_appointment(record["id"], car["id"], self.tomorrow, time(10), "Перенос в прошлое")

    def test_orders_and_items_roundtrip_preserves_model_types(self):
        client, car, service = self.fixtures()
        second = self.db.add_service("Проверка тормозов", "Диагностика", 900, 30)
        order = self.db.add_order(client["id"], car["id"], [second["id"], service["id"]], "Обслуживание")
        self.assertEqual(order["total"], 2400)
        self.assertEqual([i["service_id"] for i in order["items"]], [second["id"], service["id"]])
        self.assertEqual(order["car_snapshot"], {k: car[k] for k in ("brand", "model", "plate")})
        self.assertIsNone(order["completed_at"])
        self.reopen()
        self.assertEqual(self.db.get_order(order["id"]), order)
        self.assertEqual(self.db.list_orders(), [order])
        self.assertIs(type(order["total"]), int)
        self.assertIs(type(order["date"]), type(self.tomorrow))

    def test_order_creation_validation_leaves_no_partial_document(self):
        client, car, service = self.fixtures()
        another = self.db.add_client("Другой", "2")
        for owner, services, reason in [(another["id"], [service["id"]], "Причина"),
                                         (client["id"], [], "Причина"),
                                         (client["id"], [service["id"], service["id"]], "Причина"),
                                         (client["id"], [service["id"]], "   ")]:
            with self.subTest(owner=owner, services=services, reason=reason), self.assertRaises(ValueError):
                self.db.add_order(owner, car["id"], services, reason)
        with self.assertRaises(KeyError):
            self.db.add_order(client["id"], car["id"], [999], "Причина")
        self.assertEqual(self.db.list_orders(), [])

    def test_order_snapshots_survive_catalog_deletion_and_reference_updates(self):
        client, car, service, order = self.create_document()
        original = copy.deepcopy(order)
        self.db.update_service(service["id"], "Другое название", "Ремонт", 9999)
        self.db.delete_service(service["id"])
        self.db.update_client(client["id"], "Другое имя", "2")
        other = self.db.add_client("Новый владелец", "3")
        self.db.update_car(car["id"], other["id"], "Honda", "Fit", "Е222АА125")
        self.reopen()
        self.assertEqual(self.db.get_order(order["id"]), original)
        self.assertEqual(original["items"][0]["service_id"], service["id"])
        self.assertEqual(original["items"][0]["price"], 1500)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.delete_client(client["id"])
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.delete_car(car["id"])

    def test_order_status_and_completion_timezone_written_once(self):
        _, _, _, order = self.create_document()
        moment = local_now().replace(microsecond=123456)
        for status in ("В работе", "Готов к выдаче"):
            order = self.db.advance_order(order["id"])
            self.assertEqual(order["status"], status)
            self.assertIsNone(order["completed_at"])
            self.reopen()
        with patch("autoservice.data.local_now", return_value=moment):
            completed = self.db.advance_order(order["id"])
        self.assertEqual(completed["completed_at"], moment.replace(tzinfo=LOCAL_TIMEZONE))
        self.assertEqual(completed["completed_at"].tzname(), "Asia/Vladivostok")
        self.reopen()
        self.assertEqual(self.db.get_order(order["id"]), completed)
        with patch("autoservice.data.local_now", return_value=moment + timedelta(days=10)):
            self.assertEqual(self.db.advance_order(order["id"]), completed)
        self.assertEqual(self.db.list_orders(completed_only=True), [completed])

    def test_history_is_derived_and_filtered_by_car_id(self):
        _, car, _, order = self.create_document()
        self.assertEqual(self.db.list_orders(completed_only=True), [])
        for _ in range(3):
            completed = self.db.advance_order(order["id"])
        self.assertEqual(self.db.list_orders(completed_only=True, car_id=car["id"]), [completed])
        self.assertEqual(self.db.list_orders(completed_only=True, car_id=999), [])
        self.assertEqual(len(self.db.list_orders()), 1)

    def test_transaction_rollback_across_operations(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with self.db.transaction():
                client = self.db.add_client("Не сохранять", "1")
                self.db.add_car(client["id"], "Kia", "Rio", "А123ВС125")
                self.db.add_car(999, "Toyota", "Corolla", "Е222АА125")
        self.assertEqual(self.db.list_clients(), [])
        self.assertEqual(self.db.list_cars(), [])
        self.reopen()
        self.assertEqual(self.db.list_clients(), [])

    def test_nested_failed_operation_can_be_caught_without_losing_outer_changes(self):
        with self.db.transaction():
            owner = self.db.add_client("Сохранить", "1")
            with self.assertRaises(sqlite3.IntegrityError):
                self.db.add_car(999, "Kia", "Rio", "А123ВС125")
            car = self.db.add_car(owner["id"], "Kia", "Rio", "А123ВС125")
        self.reopen()
        self.assertEqual(self.db.get_car(car["id"])["owner_id"], owner["id"])

    def test_mid_order_item_failure_rolls_back_parent_and_all_items(self):
        client, car, first = self.fixtures()
        second = self.db.add_service("Вторая работа", "Ремонт", 100)
        insert = self.db._insert
        def fail(table, values):
            if table == "order_items" and values["position"] == 1:
                raise sqlite3.IntegrityError("Проверка аварийного отката")
            return insert(table, values)
        with patch.object(self.db, "_insert", side_effect=fail), self.assertRaises(sqlite3.IntegrityError):
            self.db.add_order(client["id"], car["id"], [first["id"], second["id"]], "Причина")
        self.assertEqual(self.db.list_orders(), [])
        self.assertEqual(self.db._connection.execute("SELECT count(*) FROM order_items").fetchone()[0], 0)

    def test_schema_rejects_status_skips_snapshot_mutation_and_deletions(self):
        _, car, service, order = self.create_document()
        record = self.db.add_appointment(car["id"], self.tomorrow, time(9), "Причина")
        self.db.cancel_appointment(record["id"])
        for sql, parameters in [
            ("UPDATE orders SET status='Готов к выдаче' WHERE id=?", (order["id"],)),
            ("UPDATE orders SET client_name='Подмена' WHERE id=?", (order["id"],)),
            ("DELETE FROM orders WHERE id=?", (order["id"],)),
            ("UPDATE order_items SET price=1 WHERE order_id=?", (order["id"],)),
            ("DELETE FROM order_items WHERE order_id=?", (order["id"],)),
            ("UPDATE appointments SET status='Запланирована' WHERE id=?", (record["id"],)),
            ("DELETE FROM appointments WHERE id=?", (record["id"],)),
            ("UPDATE services SET price=-1 WHERE id=?", (service["id"],)),
        ]:
            with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError):
                with self.db.transaction():
                    self.db._connection.execute(sql, parameters)
        self.assertEqual(self.db.get_order(order["id"]), order)

    def test_explicit_demo_loading_is_atomic_idempotent_and_not_automatic(self):
        self.assertEqual(self.db.list_clients(), [])
        self.assertTrue(load_demo_data(self.db))
        self.assertEqual(self.db.list_clients(), CLIENTS)
        self.assertEqual(self.db.list_cars(), CARS)
        self.assertEqual(self.db.list_services(), SERVICES)
        self.assertEqual(len(self.db.list_appointments()), 7)
        self.assertEqual(self.db.list_orders(), make_orders(CLIENTS, CARS, SERVICES, local_now().date()))
        before = self.db.list_orders()
        self.assertFalse(load_demo_data(self.db))
        self.reopen()
        self.assertFalse(load_demo_data(self.db))
        self.assertEqual(self.db.list_orders(), before)
        new = self.db.add_client("Дополнительный клиент", "8")
        self.assertEqual(new["id"], 8)

    def test_nonempty_or_previously_used_database_is_not_seeded(self):
        client = self.db.add_client("Пользовательский клиент", "1")
        self.assertFalse(load_demo_data(self.db))
        self.db.delete_client(client["id"])
        self.assertFalse(load_demo_data(self.db))
        self.assertEqual(self.db.list_clients(), [])

    def test_failed_demo_loading_rolls_back_every_table(self):
        insert = self.db._insert
        def fail(table, values):
            if table == "services":
                raise sqlite3.IntegrityError("Проверка отката демо")
            return insert(table, values)
        with patch.object(self.db, "_insert", side_effect=fail), self.assertRaises(sqlite3.IntegrityError):
            load_demo_data(self.db)
        self.assertEqual(self.db.list_clients(), [])
        self.assertEqual(self.db.list_cars(), [])
        self.assertTrue(load_demo_data(self.db))

    def test_missing_records_raise_key_error_and_database_remains_usable(self):
        with self.assertRaises(KeyError):
            self.db.get_client(999)
        with self.assertRaises(KeyError):
            self.db.update_client(999, "Имя", "1")
        with self.assertRaises(KeyError):
            self.db.delete_car(999)
        self.assertEqual(self.db.add_client("После ошибки", "1")["id"], 1)


if __name__ == "__main__":
    unittest.main()
