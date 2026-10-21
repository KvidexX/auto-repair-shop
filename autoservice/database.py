"""SQLite-хранилище. Используется справочниками при явной передаче зависимости."""

from contextlib import contextmanager
from datetime import date, datetime, time
import os
from pathlib import Path
import sqlite3

from .data import (
    CARS, CATEGORIES, CLIENTS, LOCAL_TIMEZONE, SERVICES, advance_order, create_order, edit_order,
    local_now, make_appointments, make_orders, normalize_plate, normalize_service_name,
)


SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL CHECK(length(trim(name)) > 0),
    phone TEXT NOT NULL CHECK(length(trim(phone)) > 0),
    note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS cars (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
    brand TEXT NOT NULL CHECK(length(trim(brand)) > 0),
    model TEXT NOT NULL CHECK(length(trim(model)) > 0),
    plate TEXT NOT NULL CHECK(length(plate) > 0),
    plate_key TEXT NOT NULL UNIQUE,
    year INTEGER CHECK(year IS NULL OR (typeof(year) = 'integer' AND year >= 1900)),
    vin TEXT NOT NULL DEFAULT '' CHECK(vin = '' OR length(vin) = 17),
    mileage INTEGER CHECK(mileage IS NULL OR (typeof(mileage) = 'integer' AND mileage BETWEEN 0 AND 2147483647))
);
CREATE INDEX IF NOT EXISTS cars_owner ON cars(owner_id);
CREATE TABLE IF NOT EXISTS services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL CHECK(length(trim(name)) > 0),
    name_key TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL CHECK(category IN ('Диагностика','Техническое обслуживание','Ремонт')),
    price INTEGER NOT NULL CHECK(typeof(price) = 'integer' AND price BETWEEN 0 AND 2147483647),
    duration INTEGER CHECK(duration IS NULL OR (typeof(duration) = 'integer' AND duration BETWEEN 1 AND 2147483647)),
    description TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    car_id INTEGER NOT NULL REFERENCES cars(id) ON DELETE RESTRICT,
    date TEXT NOT NULL CHECK(length(date) = 10),
    time TEXT NOT NULL CHECK(time IN ('09:00','09:30','10:00','10:30','11:00','11:30',
        '12:00','12:30','13:00','13:30','14:00','14:30','15:00','15:30','16:00','16:30','17:00','17:30','18:00')),
    reason TEXT NOT NULL CHECK(length(trim(reason)) > 0),
    note TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL CHECK(status IN ('Запланирована','Отменена'))
);
CREATE UNIQUE INDEX IF NOT EXISTS appointments_active_slot ON appointments(date,time) WHERE status = 'Запланирована';
CREATE INDEX IF NOT EXISTS appointments_car ON appointments(car_id);
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL CHECK(length(date) = 10),
    client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
    client_name TEXT NOT NULL CHECK(length(trim(client_name)) > 0),
    car_id INTEGER NOT NULL REFERENCES cars(id) ON DELETE RESTRICT,
    car_brand TEXT NOT NULL,
    car_model TEXT NOT NULL,
    car_plate TEXT NOT NULL,
    reason TEXT NOT NULL CHECK(length(trim(reason)) > 0),
    total INTEGER NOT NULL CHECK(typeof(total) = 'integer' AND total >= 0),
    item_count INTEGER NOT NULL CHECK(item_count > 0),
    status TEXT NOT NULL CHECK(status IN ('Оформлен','В работе','Готов к выдаче','Завершён')),
    completed_at TEXT,
    CHECK((status = 'Завершён' AND completed_at IS NOT NULL AND substr(completed_at,-6) = '+10:00')
        OR (status != 'Завершён' AND completed_at IS NULL))
);
CREATE INDEX IF NOT EXISTS orders_client ON orders(client_id);
CREATE INDEX IF NOT EXISTS orders_car ON orders(car_id);
CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE RESTRICT,
    position INTEGER NOT NULL CHECK(position >= 0),
    service_id INTEGER NOT NULL CHECK(service_id > 0),
    name TEXT NOT NULL CHECK(length(trim(name)) > 0),
    price INTEGER NOT NULL CHECK(typeof(price) = 'integer' AND price >= 0),
    UNIQUE(order_id,position),
    UNIQUE(order_id,service_id)
);
CREATE TRIGGER IF NOT EXISTS appointments_readonly BEFORE UPDATE ON appointments
WHEN OLD.status = 'Отменена' OR NEW.id != OLD.id OR NEW.status NOT IN ('Запланирована','Отменена')
BEGIN SELECT RAISE(ABORT,'Cancelled appointments are read only'); END;
CREATE TRIGGER IF NOT EXISTS appointments_keep BEFORE DELETE ON appointments
BEGIN SELECT RAISE(ABORT,'Appointments must be cancelled, not deleted'); END;
CREATE TRIGGER IF NOT EXISTS orders_readonly BEFORE UPDATE ON orders
WHEN NEW.id IS NOT OLD.id OR NEW.date IS NOT OLD.date OR NEW.client_id IS NOT OLD.client_id
    OR NEW.client_name IS NOT OLD.client_name OR NEW.car_id IS NOT OLD.car_id
    OR NEW.car_brand IS NOT OLD.car_brand OR NEW.car_model IS NOT OLD.car_model OR NEW.car_plate IS NOT OLD.car_plate
    OR NEW.reason IS NOT OLD.reason OR NEW.total IS NOT OLD.total OR NEW.item_count IS NOT OLD.item_count
    OR NOT ((OLD.status = 'Оформлен' AND NEW.status = 'В работе' AND NEW.completed_at IS NULL)
        OR (OLD.status = 'В работе' AND NEW.status = 'Готов к выдаче' AND NEW.completed_at IS NULL)
        OR (OLD.status = 'Готов к выдаче' AND NEW.status = 'Завершён' AND NEW.completed_at IS NOT NULL))
BEGIN SELECT RAISE(ABORT,'Only the next order status is allowed'); END;
CREATE TRIGGER IF NOT EXISTS orders_keep BEFORE DELETE ON orders
BEGIN SELECT RAISE(ABORT,'Orders cannot be deleted'); END;
CREATE TRIGGER IF NOT EXISTS items_readonly BEFORE UPDATE ON order_items
BEGIN SELECT RAISE(ABORT,'Order items are immutable'); END;
CREATE TRIGGER IF NOT EXISTS items_keep BEFORE DELETE ON order_items
BEGIN SELECT RAISE(ABORT,'Order items cannot be deleted'); END;
CREATE TRIGGER IF NOT EXISTS items_count BEFORE INSERT ON order_items
WHEN NEW.position >= (SELECT item_count FROM orders WHERE id = NEW.order_id)
BEGIN SELECT RAISE(ABORT,'Order composition is fixed'); END;
"""


MIGRATION_2 = """
DROP TRIGGER orders_readonly;
CREATE TRIGGER orders_readonly BEFORE UPDATE ON orders
WHEN OLD.status = 'Завершён' OR NEW.id IS NOT OLD.id OR NEW.date IS NOT OLD.date
 OR (NEW.status = OLD.status AND NEW.completed_at IS NOT OLD.completed_at)
 OR (NEW.status != OLD.status AND (
    NEW.client_id IS NOT OLD.client_id OR NEW.client_name IS NOT OLD.client_name
    OR NEW.car_id IS NOT OLD.car_id OR NEW.car_brand IS NOT OLD.car_brand
    OR NEW.car_model IS NOT OLD.car_model OR NEW.car_plate IS NOT OLD.car_plate
    OR NEW.reason IS NOT OLD.reason OR NEW.total IS NOT OLD.total OR NEW.item_count IS NOT OLD.item_count
    OR NOT ((OLD.status = 'Оформлен' AND NEW.status = 'В работе' AND NEW.completed_at IS NULL)
        OR (OLD.status = 'В работе' AND NEW.status = 'Готов к выдаче' AND NEW.completed_at IS NULL)
        OR (OLD.status = 'Готов к выдаче' AND NEW.status = 'Завершён' AND NEW.completed_at IS NOT NULL))))
BEGIN SELECT RAISE(ABORT,'Completed orders are read only; use the next status'); END;
DROP TRIGGER items_keep;
CREATE TRIGGER items_keep BEFORE DELETE ON order_items
WHEN (SELECT status FROM orders WHERE id = OLD.order_id) = 'Завершён'
BEGIN SELECT RAISE(ABORT,'Completed order items cannot be deleted'); END;
DROP TRIGGER items_count;
CREATE TRIGGER items_count BEFORE INSERT ON order_items
WHEN (SELECT status FROM orders WHERE id = NEW.order_id) = 'Завершён'
 OR NEW.position >= (SELECT item_count FROM orders WHERE id = NEW.order_id)
BEGIN SELECT RAISE(ABORT,'Invalid order composition'); END;
"""

TABLES = ("clients", "cars", "services", "appointments", "orders", "order_items")


def default_database_path():
    base = Path(os.environ["LOCALAPPDATA"]) if os.environ.get("LOCALAPPDATA") else Path.home() / "AppData" / "Local"
    return base / "AutoService" / "autoservice.db"


def _text(value, field, required=False):
    if not isinstance(value, str) or (required and not value.strip()):
        raise ValueError(f"Некорректное поле: {field}.")
    return value.strip()


def _integer(value, field, minimum=0, maximum=2147483647, optional=False):
    if value is None and optional:
        return None
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"Некорректное целое число: {field}.")
    return value


def _day(value):
    if type(value) is not date:
        raise ValueError("Ожидается дата типа datetime.date.")
    return value.isoformat()


class Database:
    """Синхронный API; записи имеют те же словари и типы, что у прототипа."""

    def __init__(self, path=None):
        self.path = Path(path) if path is not None else default_database_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path, isolation_level=None, timeout=5)
        self._connection.row_factory = sqlite3.Row
        self._savepoint = 0
        try:
            self._connection.execute("PRAGMA foreign_keys = ON")
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2):
                raise ValueError("Неподдерживаемая версия базы данных.")
            if version < 2:
                self._connection.executescript("BEGIN IMMEDIATE;\n" + (SCHEMA if version == 0 else "") + MIGRATION_2 + "\nPRAGMA user_version=2;\nCOMMIT;")
        except BaseException:
            self._connection.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        self._connection.close()

    @contextmanager
    def transaction(self):
        """Методы атомарны сами по себе и поддерживают общую внешнюю транзакцию."""
        nested = self._connection.in_transaction
        self._savepoint += 1
        name = f"operation_{self._savepoint}"
        self._connection.execute(f"SAVEPOINT {name}" if nested else "BEGIN IMMEDIATE")
        try:
            yield self
            self._connection.execute(f"RELEASE SAVEPOINT {name}" if nested else "COMMIT")
        except BaseException:
            if nested:
                self._connection.execute(f"ROLLBACK TO SAVEPOINT {name}")
                self._connection.execute(f"RELEASE SAVEPOINT {name}")
            else:
                self._connection.execute("ROLLBACK")
            raise

    def _insert(self, table, values):
        # Имена таблиц/полей задаёт только код ниже; пользовательские значения — параметры.
        if table not in TABLES:
            raise ValueError("Неизвестная таблица")
        columns = ",".join(values)
        placeholders = ",".join("?" for _ in values)
        return self._connection.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", tuple(values.values())).lastrowid

    def _get(self, table, record_id):
        if table not in TABLES:
            raise ValueError("Неизвестная таблица")
        row = self._connection.execute(f"SELECT * FROM {table} WHERE id=?", (record_id,)).fetchone()
        if row is None:
            raise KeyError(record_id)
        return dict(row)

    def _update(self, table, record_id, values):
        self._get(table, record_id)
        assignments = ",".join(f"{column}=?" for column in values)
        self._connection.execute(f"UPDATE {table} SET {assignments} WHERE id=?", (*values.values(), record_id))

    def _delete(self, table, record_id):
        with self.transaction():
            self._get(table, record_id)
            self._connection.execute(f"DELETE FROM {table} WHERE id=?", (record_id,))

    def get_client(self, client_id):
        return self._get("clients", client_id)

    def list_clients(self):
        return [dict(row) for row in self._connection.execute("SELECT * FROM clients ORDER BY id")]

    def add_client(self, name, phone, note=""):
        values = {"name": _text(name, "ФИО", True), "phone": _text(phone, "Телефон", True), "note": _text(note, "Примечание")}
        with self.transaction():
            record_id = self._insert("clients", values)
        return self.get_client(record_id)

    def update_client(self, client_id, name, phone, note=""):
        values = {"name": _text(name, "ФИО", True), "phone": _text(phone, "Телефон", True), "note": _text(note, "Примечание")}
        with self.transaction():
            self._update("clients", client_id, values)
        return self.get_client(client_id)

    def delete_client(self, client_id):
        self._delete("clients", client_id)

    def car_count(self, client_id):
        return self._connection.execute("SELECT count(*) FROM cars WHERE owner_id=?", (client_id,)).fetchone()[0]

    def get_car(self, car_id):
        car = self._get("cars", car_id)
        del car["plate_key"]
        return car

    def list_cars(self, owner_id=None):
        rows = self._connection.execute("SELECT id FROM cars ORDER BY id" if owner_id is None else
                                        "SELECT id FROM cars WHERE owner_id=? ORDER BY id", () if owner_id is None else (owner_id,))
        return [self.get_car(row[0]) for row in rows]

    def _car_values(self, owner_id, brand, model, plate, year, vin, mileage):
        plate = normalize_plate(_text(plate, "Госномер", True))
        if not plate:
            raise ValueError("Укажите госномер.")
        vin = _text(vin, "VIN").upper()
        if vin and len(vin) != 17:
            raise ValueError("VIN должен содержать 17 символов.")
        return {"owner_id": _integer(owner_id, "Владелец", 1), "brand": _text(brand, "Марка", True),
                "model": _text(model, "Модель", True), "plate": plate, "plate_key": plate,
                "year": _integer(year, "Год", 1900, local_now().year + 1, True), "vin": vin,
                "mileage": _integer(mileage, "Пробег", optional=True)}

    def add_car(self, owner_id, brand, model, plate, year=None, vin="", mileage=None):
        values = self._car_values(owner_id, brand, model, plate, year, vin, mileage)
        with self.transaction():
            record_id = self._insert("cars", values)
        return self.get_car(record_id)

    def update_car(self, car_id, owner_id, brand, model, plate, year=None, vin="", mileage=None):
        values = self._car_values(owner_id, brand, model, plate, year, vin, mileage)
        with self.transaction():
            self._update("cars", car_id, values)
        return self.get_car(car_id)

    def delete_car(self, car_id):
        self._delete("cars", car_id)

    def get_service(self, service_id):
        service = self._get("services", service_id)
        del service["name_key"]
        return service

    def list_services(self):
        return [self.get_service(row[0]) for row in self._connection.execute("SELECT id FROM services ORDER BY id")]

    def _service_values(self, name, category, price, duration, description):
        if category not in CATEGORIES:
            raise ValueError("Выберите категорию услуги.")
        name = " ".join(_text(name, "Наименование", True).split())
        return {"name": name, "name_key": normalize_service_name(name), "category": category,
                "price": _integer(price, "Стоимость"), "duration": _integer(duration, "Время", 1, optional=True),
                "description": _text(description, "Описание")}

    def add_service(self, name, category, price, duration=None, description=""):
        values = self._service_values(name, category, price, duration, description)
        with self.transaction():
            record_id = self._insert("services", values)
        return self.get_service(record_id)

    def update_service(self, service_id, name, category, price, duration=None, description=""):
        values = self._service_values(name, category, price, duration, description)
        with self.transaction():
            self._update("services", service_id, values)
        return self.get_service(service_id)

    def delete_service(self, service_id):
        self._delete("services", service_id)

    def get_appointment(self, appointment_id):
        record = self._get("appointments", appointment_id)
        record["date"] = date.fromisoformat(record["date"])
        record["time"] = time.fromisoformat(record["time"])
        return record

    def list_appointments(self):
        return [self.get_appointment(row[0]) for row in self._connection.execute("SELECT id FROM appointments ORDER BY date,time,id")]

    def _appointment_values(self, car_id, day, slot, reason, note, previous=None):
        _day(day)
        if type(slot) is not time or slot.tzinfo is not None or slot.second or slot.microsecond or slot.minute not in (0, 30) or not time(9) <= slot <= time(18):
            raise ValueError("Время: с 09:00 до 18:00 с шагом 30 минут.")
        timestamp = datetime.combine(day, slot)
        old_timestamp = datetime.combine(previous["date"], previous["time"]) if previous else None
        if timestamp < local_now() and timestamp != old_timestamp:
            raise ValueError("Нельзя назначить посещение в прошлом.")
        return {"car_id": _integer(car_id, "Автомобиль", 1), "date": day.isoformat(), "time": slot.strftime("%H:%M"),
                "reason": _text(reason, "Причина", True), "note": _text(note, "Примечание")}

    def add_appointment(self, car_id, day, slot, reason, note=""):
        values = self._appointment_values(car_id, day, slot, reason, note)
        with self.transaction():
            record_id = self._insert("appointments", {**values, "status": "Запланирована"})
        return self.get_appointment(record_id)

    def update_appointment(self, appointment_id, car_id, day, slot, reason, note=""):
        with self.transaction():
            previous = self.get_appointment(appointment_id)
            values = self._appointment_values(car_id, day, slot, reason, note, previous)
            self._update("appointments", appointment_id, values)
        return self.get_appointment(appointment_id)

    def cancel_appointment(self, appointment_id):
        with self.transaction():
            record = self.get_appointment(appointment_id)
            if record["status"] != "Отменена":
                self._update("appointments", appointment_id, {"status": "Отменена"})
        return self.get_appointment(appointment_id)

    def _store_order(self, order):
        car = order["car_snapshot"]
        order_id = self._insert("orders", {"id": order["id"], "date": _day(order["date"]), "client_id": order["client_id"],
                    "client_name": order["client_name"], "car_id": order["car_id"], "car_brand": car["brand"],
                    "car_model": car["model"], "car_plate": car["plate"], "reason": order["reason"],
                    "total": order["total"], "item_count": len(order["items"]), "status": "Готов к выдаче" if order["status"] == "Завершён" else order["status"],
                    "completed_at": None})
        for position, item in enumerate(order["items"]):
            self._insert("order_items", {"order_id": order_id, "position": position, **item})
        if order["status"] == "Завершён":
            self._update("orders", order_id, {"status": "Завершён", "completed_at": order["completed_at"].isoformat()})
        return order_id

    def add_order(self, client_id, car_id, service_ids, reason):
        with self.transaction():
            client, car = self.get_client(client_id), self.get_car(car_id)
            services = [self.get_service(sid) for sid in service_ids]
            # SQLite назначает ID, не переиспользуя ранее сохранённые значения.
            order = create_order(None, local_now().date(), client, car, services, reason)
            order_id = self._store_order(order)
        return self.get_order(order_id)

    def update_order(self, order_id, client_id, car_id, service_ids, reason, *, reprice_service_ids=()):
        with self.transaction():
            previous = self.get_order(order_id)
            if previous["status"] == "Завершён":
                raise ValueError("Завершённый заказ-наряд нельзя редактировать.")
            retained = {item["service_id"]: item for item in previous["items"]}
            services = [({"id": sid, "name": retained[sid]["name"], "price": retained[sid]["price"]}
                         if sid in retained and sid not in reprice_service_ids else self.get_service(sid))
                        for sid in service_ids]
            order = edit_order(previous, self.get_client(client_id), self.get_car(car_id), services, reason,
                               reprice_service_ids=reprice_service_ids)
            car = order["car_snapshot"]
            self._connection.execute("DELETE FROM order_items WHERE order_id=?", (order_id,))
            self._update("orders", order_id, {"client_id": client_id, "client_name": order["client_name"],
                         "car_id": car_id, "car_brand": car["brand"], "car_model": car["model"], "car_plate": car["plate"],
                         "reason": order["reason"], "total": order["total"], "item_count": len(order["items"])})
            for position, item in enumerate(order["items"]):
                self._insert("order_items", {"order_id": order_id, "position": position, **item})
        return self.get_order(order_id)

    def get_order(self, order_id):
        with self.transaction():
            record = self._get("orders", order_id)
            record.pop("item_count")
            record["date"] = date.fromisoformat(record["date"])
            if record["completed_at"]:
                record["completed_at"] = datetime.fromisoformat(record["completed_at"]).astimezone(LOCAL_TIMEZONE)
            record["car_snapshot"] = {key: record.pop("car_" + key) for key in ("brand", "model", "plate")}
            record["items"] = [dict(row) for row in self._connection.execute(
                "SELECT service_id,name,price FROM order_items WHERE order_id=? ORDER BY position", (order_id,))]
        return record

    def list_orders(self, completed_only=False, car_id=None):
        conditions, parameters = [], []
        if completed_only:
            conditions.append("status=?")
            parameters.append("Завершён")
        if car_id is not None:
            conditions.append("car_id=?")
            parameters.append(car_id)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        sorting = "completed_at DESC,id DESC" if completed_only else "date DESC,id DESC"
        with self.transaction():
            ids = [row[0] for row in self._connection.execute("SELECT id FROM orders" + where + " ORDER BY " + sorting, parameters)]
            return [self.get_order(order_id) for order_id in ids]

    def advance_order(self, order_id):
        with self.transaction():
            order = self.get_order(order_id)
            if advance_order(order):
                self._update("orders", order_id, {"status": order["status"],
                             "completed_at": order["completed_at"].isoformat() if order["completed_at"] else None})
        return self.get_order(order_id)


def load_demo_data(database):
    """Явная тестовая загрузка; не вызывается конструктором или интерфейсом."""
    with database.transaction():
        if any(database._connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone() for table in TABLES):
            return False
        if database._connection.execute("SELECT 1 FROM sqlite_sequence LIMIT 1").fetchone():
            return False
        for client in CLIENTS:
            database._insert("clients", client)
        for car in CARS:
            database._insert("cars", {**car, "plate_key": normalize_plate(car["plate"])})
        for service in SERVICES:
            database._insert("services", {**service, "name_key": normalize_service_name(service["name"])})
        today = local_now().date()
        for record in make_appointments(today):
            database._insert("appointments", {**record, "date": record["date"].isoformat(), "time": record["time"].strftime("%H:%M")})
        for order in make_orders(CLIENTS, CARS, SERVICES, today):
            database._store_order(order)
    return True
