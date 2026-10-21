"""Реальный main(), QApplication и отдельные процессы с временным LOCALAPPDATA."""

from contextlib import closing
from datetime import timedelta
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from tests.support import SCREENSHOTS


ROOT = Path(__file__).resolve().parents[1]


def launch_worker(scenario, report_path, arguments):
    import main as entry
    from autoservice.appointments import qt_date
    from autoservice.data import local_now
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox

    report = {"database_calls": 0, "window_calls": 0, "errors": [], "messages": []}
    connections, windows = [], []
    real_database, real_window = entry.Database, entry.MainWindow
    real_connect, real_message_exec = sqlite3.connect, QMessageBox.exec

    def connect(*args, **kwargs):
        connection = real_connect(*args, **kwargs)
        connections.append(connection)
        return connection

    def database(*args, **kwargs):
        report["database_calls"] += 1
        if scenario.startswith("screenshot") or scenario == "demo":
            raise AssertionError("Скриншоты не должны открывать SQLite")
        assert not args and not kwargs, "Обычный запуск должен использовать Database()"
        db = real_database()
        report["database_path"] = str(db.path)
        return db

    def modal(action, invoke):
        failures = []
        def fill():
            dialog = QApplication.activeModalWidget()
            try:
                assert dialog is not None
                action(dialog)
                assert not dialog.isVisible(), "Форма не закрылась"
            except Exception as error:
                failures.append(repr(error))
                if dialog:
                    dialog.reject()
        QTimer.singleShot(20, fill)
        invoke()
        assert not failures, failures

    def exercise(window):
        try:
            if scenario == "create":
                assert window.clients == window.cars == window.services_page.services == []
                def client(d):
                    d.name_input.setText("Вера Постоянная")
                    d.phone_input.setText("89991112233")
                    d.note_input.setPlainText("Тест повторного запуска")
                    d.save_button.click()
                modal(client, window.add_client)
                def car(d):
                    d.owner_input.setCurrentIndex(d.owner_input.findData(window.clients[0]["id"]))
                    d.brand_input.setText("Honda")
                    d.model_input.setText("Fit")
                    d.plate_input.setText("Е111АА125")
                    d.year_input.setText("2018")
                    d.mileage_input.setText("75000")
                    d.save_button.click()
                modal(car, window.add_car)
                def service(d):
                    d.name_input.setText("Замена масла")
                    d.category_input.setCurrentIndex(2)
                    d.price_input.setText("800")
                    d.duration_input.setText("30")
                    d.save_button.click()
                modal(service, window.services_page.add_service)
                def appointment(d):
                    d.client_input.setCurrentIndex(d.client_input.findData(window.clients[0]["id"]))
                    d.car_input.setCurrentIndex(d.car_input.findData(window.cars[0]["id"]))
                    d.date_input.setDate(qt_date(local_now().date() + timedelta(days=5)))
                    d.time_input.setCurrentIndex(d.time_input.findData("10:00"))
                    d.reason_input.setText("Плановое обслуживание")
                    d.note_input.setPlainText("Примечание записи")
                    d.save_button.click()
                appointments = window.appointments_page
                modal(appointment, appointments.add_appointment)
                def confirm(box):
                    next(b for b in box.buttons() if b.text() == "Отменить запись").click()
                modal(confirm, appointments.cancel_appointment)
                modal(appointment, appointments.add_appointment)
                def order(d):
                    d.client_input.setCurrentIndex(d.client_input.findData(window.clients[0]["id"]))
                    d.car_input.setCurrentIndex(d.car_input.findData(window.cars[0]["id"]))
                    d.reason_input.setText("Плановое обслуживание")
                    d.service_input.setCurrentIndex(d.service_input.findData(window.services_page.services[0]["id"]))
                    d.add_item_button.click()
                    d.save_button.click()
                modal(order, window.orders_page.add_order)
                created_order = dict(window.orders_page.selected_order())
                def edit_order(d):
                    assert d.reason_input.text() == "Плановое обслуживание"
                    d.reason_input.setText("Обслуживание: уточнённый состав обращения")
                    d.save_button.click()
                modal(edit_order, lambda: window.orders_page.edit_order(created_order["id"]))
                edited = window.orders_page.selected_order()
                assert edited["id"] == created_order["id"] and edited["date"] == created_order["date"]
                assert edited["status"] == created_order["status"]
                assert edited["reason"] == "Обслуживание: уточнённый состав обращения"
                def complete(card):
                    for _ in range(3):
                        card.next_button.click()
                    assert card.order["status"] == "Завершён"
                    card.close_button.click()
                modal(complete, window.orders_page.open_order)
                def reprice(d):
                    d.price_input.setText("1200")
                    d.save_button.click()
                modal(reprice, window.services_page.edit_service)
            report["snapshot"] = {
                "clients": window.clients, "cars": window.cars,
                "services": window.services_page.services,
                "appointments": window.appointments_page.appointments,
                "orders": window.orders_page.orders,
                "history": window.history_page.completed_orders(),
            }
            assert window.history_page.orders is window.orders_page.orders
        except Exception as error:
            report["errors"].append(repr(error))
        finally:
            window.close()
            QApplication.instance().quit()

    def window(*args, **kwargs):
        report["window_calls"] += 1
        db = kwargs.get("database")
        report["database_passed"] = db is not None
        widget = real_window(*args, **kwargs)
        windows.append(widget)
        if scenario == "fail-window":
            raise RuntimeError("Тестовая ошибка подготовки окна")
        if scenario.startswith("screenshot"):
            report["demo_counts"] = [len(widget.clients), len(widget.cars), len(widget.orders_page.orders)]
        else:
            QTimer.singleShot(0, lambda: exercise(widget))
        return widget

    def message(box):
        if box.windowTitle() == "Ошибка запуска":
            report["messages"].append({"text": box.text(), "details": box.detailedText()})
            return 0
        return real_message_exec(box)

    if scenario == "screenshot-bare":
        entry.__file__ = str(Path(report_path).parent / "launcher.py")
    sys.argv = [str(ROOT / "main.py"), *arguments]
    with patch.object(entry, "Database", database), patch.object(entry, "MainWindow", window), \
            patch.object(QMessageBox, "exec", message), patch("autoservice.database.sqlite3.connect", connect):
        code = entry.main()
    report["exit_code"] = code
    report["connections_closed"] = True
    for connection in connections:
        try:
            connection.execute("SELECT 1")
        except sqlite3.ProgrammingError:
            pass
        else:
            report["connections_closed"] = False
    report["windows_closed"] = all(not widget.isVisible() for widget in windows)
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, default=str), encoding="utf-8")
    return code


class LaunchTests(unittest.TestCase):
    def setUp(self):
        (ROOT / ".tmp").mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="launch-test-", dir=ROOT / ".tmp")
        self.folder = Path(self.temporary.name)
        self.local = self.folder / "LocalAppData"
        self.database_path = self.local / "AutoService" / "autoservice.db"
        self.images = []
        self.sequence = 0

    def tearDown(self):
        for image in self.images:
            image.unlink(missing_ok=True)
        self.temporary.cleanup()

    def run_launch(self, scenario="empty", arguments=(), expected=0, cwd=None):
        self.sequence += 1
        report_path = self.folder / f"report-{self.sequence}.json"
        environment = dict(os.environ, LOCALAPPDATA=str(self.local), QT_QPA_PLATFORM="offscreen", PYTHONPATH=str(ROOT))
        result = subprocess.run([sys.executable, "-m", "tests.test_launch", "--worker", scenario,
                                 str(report_path), *map(str, arguments)], cwd=cwd or ROOT,
                                env=environment, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=40)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["errors"], [], report)
        self.assertEqual(report["exit_code"], expected)
        self.assertTrue(report["connections_closed"], report)
        self.assertTrue(report["windows_closed"], report)
        return report

    def image_path(self):
        image = SCREENSHOTS / f"{self.folder.name}-{len(self.images)}.png"
        self.images.append(image)
        return image

    def test_demo_never_opens_database_and_resets_between_launches(self):
        first = self.run_launch("demo", ("--demo",))
        second = self.run_launch("demo", ("--demo",))
        self.assertEqual(first["database_calls"], 0)
        self.assertFalse(first["database_passed"])
        self.assertEqual(len(first["snapshot"]["clients"]), 7)
        self.assertEqual(first["snapshot"], second["snapshot"])
        self.assertFalse(self.database_path.exists())

    def test_normal_launch_creates_empty_database_and_passes_it_to_window(self):
        self.assertFalse(self.database_path.exists())
        report = self.run_launch()
        self.assertEqual(report["database_calls"], 1)
        self.assertEqual(report["window_calls"], 1)
        self.assertTrue(report["database_passed"])
        self.assertEqual(Path(report["database_path"]), self.database_path)
        self.assertTrue(self.database_path.exists())
        self.assertTrue(all(records == [] for records in report["snapshot"].values()))
        with closing(sqlite3.connect(self.database_path)) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 2)
            self.assertEqual(connection.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name!='sqlite_sequence'").fetchone()[0], 6)

    def test_full_gui_workflow_survives_complete_process_restart(self):
        created = self.run_launch("create")
        restored = self.run_launch("restore")
        self.assertEqual(created["snapshot"], restored["snapshot"])
        saved = restored["snapshot"]
        self.assertEqual([len(saved[key]) for key in ("clients", "cars", "services", "appointments", "orders", "history")], [1, 1, 1, 2, 1, 1])
        self.assertEqual({a["status"] for a in saved["appointments"]}, {"Запланирована", "Отменена"})
        self.assertTrue(all(a["note"] == "Примечание записи" for a in saved["appointments"]))
        self.assertEqual(saved["services"][0]["price"], 1200)
        self.assertEqual(saved["orders"][0]["items"][0]["price"], 800)
        self.assertEqual(saved["orders"][0]["total"], 800)
        self.assertTrue(saved["orders"][0]["completed_at"].endswith("+10:00"))
        self.assertEqual(saved["orders"], saved["history"])

    def test_database_location_is_independent_of_working_directory(self):
        first = self.run_launch(cwd=self.folder)
        second = self.run_launch(cwd=ROOT)
        self.assertEqual(first["database_path"], second["database_path"])
        self.assertEqual(first["snapshot"], second["snapshot"])
        self.assertFalse((self.folder / "autoservice.db").exists())

    def test_unavailable_path_reports_error_without_demo_fallback(self):
        self.local.write_text("Это файл, а не каталог", encoding="utf-8")
        before = self.local.read_bytes()
        report = self.run_launch(expected=1)
        self.assertEqual(report["window_calls"], 0)
        self.assertEqual(len(report["messages"]), 1)
        self.assertIn("Не удалось запустить", report["messages"][0]["text"])
        self.assertEqual(self.local.read_bytes(), before)

    def test_corrupt_database_is_preserved_and_connection_is_closed(self):
        self.database_path.parent.mkdir(parents=True)
        self.database_path.write_bytes(b"Not a SQLite database. Preserve these bytes.")
        before = self.database_path.read_bytes()
        report = self.run_launch(expected=1)
        self.assertEqual(report["window_calls"], 0)
        self.assertEqual(len(report["messages"]), 1)
        self.assertIn("database", report["messages"][0]["details"])
        self.assertEqual(self.database_path.read_bytes(), before)

    def test_window_initialization_error_closes_database_and_partial_window(self):
        report = self.run_launch("fail-window", expected=1)
        self.assertEqual(report["window_calls"], 1)
        self.assertTrue(report["database_passed"])
        self.assertEqual(len(report["messages"]), 1)
        restored = self.run_launch()
        self.assertTrue(all(records == [] for records in restored["snapshot"].values()))

    def test_screenshot_modes_never_open_even_a_corrupt_database(self):
        self.database_path.parent.mkdir(parents=True)
        self.database_path.write_bytes(b"Do not read or write this database")
        before = (self.database_path.read_bytes(), self.database_path.stat().st_mtime_ns)
        variants = (("--screen", "calendar"), ("--screen", "clients", "--dialog"), ("--order-card", "23"))
        for arguments in variants:
            with self.subTest(arguments=arguments):
                image = self.image_path()
                report = self.run_launch("screenshot", ("--screenshot", image, *arguments))
                self.assertEqual(report["database_calls"], 0)
                self.assertFalse(report["database_passed"])
                self.assertEqual(report["demo_counts"], [7, 9, 7])
                self.assertEqual(image.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
                self.assertEqual((self.database_path.read_bytes(), self.database_path.stat().st_mtime_ns), before)

    def test_bare_screenshot_name_uses_launcher_screenshots_directory(self):
        report = self.run_launch("screenshot-bare", ("--screenshot", "example.png"))
        image = self.folder / "screenshots" / "example.png"
        self.assertEqual(image.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(report["database_calls"], 0)
        self.assertFalse(self.database_path.exists())

    def test_actual_cli_screenshot_creates_no_database(self):
        image = self.image_path()
        environment = dict(os.environ, LOCALAPPDATA=str(self.local), QT_QPA_PLATFORM="offscreen")
        result = subprocess.run([sys.executable, str(ROOT / "main.py"), "--screenshot", str(image), "--screen", "services"],
                                cwd=self.folder, env=environment, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(image.exists())
        self.assertFalse(self.local.exists())


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        sys.exit(launch_worker(sys.argv[2], sys.argv[3], sys.argv[4:]))
    unittest.main()
