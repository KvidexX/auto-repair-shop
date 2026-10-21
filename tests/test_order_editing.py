"""Целевые проверки этапа 9.2: редактирование, миграция и светлая тема."""
import copy
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from autoservice.data import edit_order
from autoservice.database import Database, SCHEMA, load_demo_data
from autoservice.orders import OrderDialog, OrderCard
from autoservice.ui import apply_light_theme, light_palette
from main import MainWindow, STYLE
from tests.test_ui_style import capture

ROOT = Path(__file__).resolve().parents[1]


class OrderEditingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyleSheet(STYLE)

    def setUp(self):
        (ROOT / '.tmp').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / '.tmp')
        self.path = Path(self.temp.name) / 'editing.db'
        self.db = Database(self.path)
        load_demo_data(self.db)
        self.order = self.db.get_order(27)

    def tearDown(self):
        self.app.closeAllWindows()
        self.db.close()
        self.temp.cleanup()

    def update(self, **overrides):
        values = dict(client_id=self.order['client_id'], car_id=self.order['car_id'],
                      service_ids=[i['service_id'] for i in self.order['items']], reason='Уточнённая причина')
        values.update(overrides)
        return self.db.update_order(self.order['id'], **values)

    def test_edit_all_three_active_statuses_preserves_identity(self):
        for status in ('В работе', 'Готов к выдаче'):
            result = self.update()
            self.assertEqual((result['id'], result['date'], result['status']),
                             (self.order['id'], self.order['date'], status))
            self.assertEqual(result['reason'], 'Уточнённая причина')
            self.db.advance_order(self.order['id'])
        self.order = self.db.get_order(26)
        self.assertEqual(self.update()['status'], 'Оформлен')

    def test_add_remove_total_and_retained_historical_price(self):
        self.db._connection.execute("UPDATE services SET price=1200,name='Новое название' WHERE id=3")
        updated = self.update(service_ids=[3, 4, 1])
        self.assertEqual(updated['items'][0], self.order['items'][0])
        self.assertEqual(updated['total'], 2600)
        self.assertEqual(self.update(service_ids=[3])['total'], 800)

    def test_new_service_uses_current_database_price_not_stale_form(self):
        self.db._connection.execute('UPDATE services SET price=1700 WHERE id=1')
        self.assertEqual(self.update(service_ids=[3, 1])['total'], 2500)

    def test_deleted_catalog_entry_can_be_retained(self):
        self.db.delete_service(3)
        self.assertEqual(self.update()['items'], self.order['items'])

    def test_removed_and_readded_service_uses_current_price(self):
        self.db._connection.execute('UPDATE services SET price=1200 WHERE id=3')
        self.assertEqual(self.update(reprice_service_ids=[3])['total'], 1500)

    def test_change_client_and_owned_car(self):
        updated = self.update(client_id=2, car_id=8)
        self.assertEqual(updated['client_name'], self.db.get_client(2)['name'])
        self.assertEqual(updated['car_snapshot']['model'], 'Note')

    def test_invalid_owner_empty_duplicate_or_missing_service_rolls_back(self):
        for values, error in [({'client_id': 2}, ValueError), ({'service_ids': []}, ValueError),
                              ({'service_ids': [3, 3]}, ValueError), ({'service_ids': [999]}, KeyError),
                              ({'reason': '   '}, ValueError)]:
            with self.subTest(values=values), self.assertRaises(error):
                self.update(**values)
            self.assertEqual(self.db.get_order(27), self.order)

    def test_completed_api_and_sql_are_immutable(self):
        self.order = self.db.get_order(23)
        with self.assertRaises(ValueError):
            self.update()
        for sql in ["UPDATE orders SET reason='Нельзя' WHERE id=23",
                    "DELETE FROM order_items WHERE order_id=23",
                    "UPDATE order_items SET price=1 WHERE order_id=23",
                    "DELETE FROM orders WHERE id=23",
                    "INSERT INTO order_items(order_id,position,service_id,name,price) VALUES(23,0,88,'Нельзя',1)"]:
            with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError):
                self.db._connection.execute(sql)
        self.assertEqual(self.db.get_order(23), self.order)

    def test_other_connection_finishes_stale_form_order(self):
        with Database(self.path) as other:
            other.advance_order(27)
            completed = other.advance_order(27)
        with self.assertRaises(ValueError):
            self.update()
        self.assertEqual(self.db.get_order(27), completed)

    def test_partial_insert_failure_rolls_back_document_and_items(self):
        insert = self.db._insert
        def fail(table, values):
            if table == 'order_items' and values['position'] == 1:
                raise sqlite3.OperationalError('Ошибка второй позиции')
            return insert(table, values)
        with patch.object(self.db, '_insert', fail), self.assertRaises(sqlite3.OperationalError):
            self.update(service_ids=[1, 2, 3])
        self.assertEqual(self.db.get_order(27), self.order)

    def test_restart_preserves_edit_and_existing_history(self):
        history = self.db.list_orders(completed_only=True)
        updated = self.update(service_ids=[3, 4, 1])
        self.db.close()
        self.db = Database(self.path)
        self.assertEqual(self.db.get_order(27), updated)
        self.assertEqual(self.db.list_orders(completed_only=True), history)

    def legacy_database(self):
        self.db.close()
        # Отдельная v1-база со всеми шестью таблицами и завершёнными документами.
        legacy_path = Path(self.temp.name) / 'legacy.db'
        legacy = Database.__new__(Database)
        legacy.path = legacy_path
        legacy._connection = sqlite3.connect(legacy_path, isolation_level=None)
        legacy._connection.row_factory = sqlite3.Row
        legacy._savepoint = 0
        legacy._connection.executescript(SCHEMA + 'PRAGMA user_version=1;')
        # v1 допускала первичную вставку сразу завершённого документа.
        load_demo_data(legacy)
        snapshot = [legacy.list_clients(), legacy.list_cars(), legacy.list_services(),
                    legacy.list_appointments(), legacy.list_orders()]
        legacy.close()
        self.path = legacy_path
        return snapshot

    def test_migration_v1_preserves_all_data_and_completed_dates(self):
        before = self.legacy_database()
        self.db = Database(self.path)
        self.assertEqual(self.db._connection.execute('PRAGMA user_version').fetchone()[0], 2)
        self.assertEqual([self.db.list_clients(), self.db.list_cars(), self.db.list_services(),
                          self.db.list_appointments(), self.db.list_orders()], before)
        self.assertEqual(self.update()['reason'], 'Уточнённая причина')

    def test_failed_migration_rolls_back_version_triggers_and_data(self):
        before = self.legacy_database()
        import autoservice.database as module
        with patch.object(module, 'MIGRATION_2', module.MIGRATION_2 + 'INVALID SQL;'):
            with self.assertRaises(sqlite3.Error):
                Database(self.path)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute('PRAGMA user_version').fetchone()[0], 1)
            self.assertIn('Only the next order status', connection.execute(
                "SELECT sql FROM sqlite_master WHERE name='orders_readonly'").fetchone()[0])
        self.db = Database(self.path)
        self.assertEqual(self.db.list_orders(), before[-1])

    def window(self):
        window = MainWindow(database=self.db)
        window.centralWidget().setObjectName('central')
        window.show()
        QTest.qWait(20)
        return window

    def test_dialog_prefill_cancel_and_removed_readded_snapshot(self):
        window = self.window()
        dialog = OrderDialog(window.clients, window.cars, window.services_page.services, window, order=self.order)
        dialog.show()
        self.assertEqual(dialog.client_input.currentData(), self.order['client_id'])
        self.assertEqual(dialog.car_input.currentData(), self.order['car_id'])
        self.assertEqual(dialog.reason_input.text(), self.order['reason'])
        dialog.items_table.selectRow(0)
        dialog.remove_item()
        dialog.service_input.setCurrentIndex(dialog.service_input.findData(3))
        dialog.add_item()
        self.assertIn(3, dialog.values()['reprice_service_ids'])
        dialog.reason_input.setText('Отменённое изменение')
        dialog.reject()
        self.assertEqual(self.db.get_order(27), self.order)

    def test_card_edit_refreshes_table_total_and_search(self):
        window = self.window()
        page = window.orders_page
        card = OrderCard(self.order, window, edit=page.edit_order)
        card.show()
        errors = []
        def submit():
            try:
                dialog = QApplication.activeModalWidget()
                self.assertIsInstance(dialog, OrderDialog)
                dialog.reason_input.setText('Обновлённое обращение')
                dialog.client_input.setCurrentIndex(dialog.client_input.findData(2))
                self.assertEqual({dialog.car_input.itemData(i) for i in range(1, dialog.car_input.count())}, {2, 8})
                dialog.car_input.setCurrentIndex(dialog.car_input.findData(8))
                dialog.service_input.setCurrentIndex(dialog.service_input.findData(1))
                dialog.add_item()
                dialog.save_button.click()
            except Exception as error:
                errors.append(error)
                QApplication.activeModalWidget().reject()
        QTimer.singleShot(20, submit)
        card.edit_button.click()
        self.assertEqual(errors, [])
        self.assertEqual(card.reason_field.toPlainText(), 'Обновлённое обращение')
        self.assertIn('Note', card.car_field.text())
        self.assertIn('2 600', card.total_label.text())
        page.search.setText('Note')
        self.assertEqual(page.table.rowCount(), 1)
        self.assertEqual(page.table.item(0, 4).text(), '2 600 ₽')
        self.assertIs(window.history_page.orders, page.orders)

    def test_sql_error_keeps_edit_form_and_shared_collection_for_retry(self):
        window = self.window()
        page = window.orders_page
        previous = copy.deepcopy(page.orders)
        dialog = OrderDialog(window.clients, window.cars, window.services_page.services, window, order=self.order)
        dialog.save_order = lambda values: page.save_document(lambda: self.db.update_order(27, **values), dialog)
        dialog.show()
        dialog.reason_input.setText('Повторить после ошибки')
        with patch.object(self.db, '_insert', side_effect=sqlite3.OperationalError('Ошибка записи')), patch.object(QMessageBox, 'exec', return_value=0):
            dialog.save_button.click()
        self.assertTrue(dialog.isVisible())
        self.assertEqual(dialog.reason_input.text(), 'Повторить после ошибки')
        self.assertEqual(page.orders, previous)
        self.assertEqual(self.db.get_order(27), self.order)
        dialog.save_button.click()
        self.assertFalse(dialog.isVisible())
        self.assertEqual(self.db.get_order(27)['reason'], 'Повторить после ошибки')

    def test_commit_and_refresh_failure_keep_form_and_previous_data(self):
        window = self.window()
        page = window.orders_page
        before = copy.deepcopy(page.orders)
        dialog = OrderDialog(window.clients, window.cars, page.services, window, order=self.order)
        dialog.save_order = lambda values: page.save_document(lambda: self.db.update_order(27, **values), dialog)
        dialog.show()
        dialog.reason_input.setText("Не должно сохраниться")
        def authorize(action, argument, *unused):
            return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_TRANSACTION and argument == 'COMMIT' else sqlite3.SQLITE_OK
        self.db._connection.set_authorizer(authorize)
        try:
            with patch.object(QMessageBox, 'exec', return_value=0):
                dialog.save_button.click()
        finally:
            self.db._connection.set_authorizer(None)
        self.assertTrue(dialog.isVisible())
        self.assertEqual(page.orders, before)
        self.assertEqual(self.db.get_order(27), self.order)
        with patch.object(self.db, 'list_orders', side_effect=sqlite3.OperationalError('Ошибка обновления')), patch.object(QMessageBox, 'exec', return_value=0):
            dialog.save_button.click()
        self.assertTrue(dialog.isVisible())
        self.assertEqual(page.orders, before)
        self.assertEqual(self.db.get_order(27), self.order)

    def test_completed_card_has_no_edit_action_and_memory_api_rejects(self):
        window = self.window()
        completed = self.db.get_order(23)
        card = OrderCard(completed, window, edit=window.orders_page.edit_order)
        card.show()
        self.assertFalse(card.edit_button.isVisible())
        self.assertFalse(card.next_button.isEnabled())
        self.assertIsNone(window.orders_page.edit_order(23))
        with self.assertRaises(ValueError):
            edit_order(completed, window.clients[4], window.cars[4], [window.services_page.services[0]], 'Нельзя')
        self.assertEqual(self.db.get_order(23), completed)

    def test_demo_form_edits_only_memory_and_new_window_restores_examples(self):
        window = MainWindow()
        window.show()
        page = window.orders_page
        original = copy.deepcopy(page.orders[0])
        errors = []
        def submit():
            try:
                dialog = QApplication.activeModalWidget()
                dialog.reason_input.setText('Только в demo')
                dialog.save_button.click()
            except Exception as error:
                errors.append(error)
                QApplication.activeModalWidget().reject()
        QTimer.singleShot(20, submit)
        saved = page.edit_order(original['id'])
        self.assertEqual(errors, [])
        self.assertEqual(saved['reason'], 'Только в demo')
        window.close()
        reopened = MainWindow()
        self.assertEqual(reopened.orders_page.orders[0], original)
        self.assertEqual(self.db.get_order(27), self.order)

    def test_memory_demo_edit_does_not_mutate_reference_data(self):
        window = MainWindow()
        page = window.orders_page
        order = page.orders[0]
        original = copy.deepcopy(order)
        refs = copy.deepcopy((window.clients, window.cars, page.services))
        updated = edit_order(order, window.clients[0], window.cars[0], [page.services[0]], 'В памяти')
        order.update(updated)
        self.assertEqual(order['total'], 1500)
        self.assertEqual((window.clients, window.cars, page.services), refs)
        self.assertEqual(self.db.get_order(27), self.order)
        self.assertNotEqual(order, original)

    def test_light_theme_survives_dark_palette_and_controls(self):
        apply_light_theme(self.app)
        dark = QPalette()
        for role in (QPalette.ColorRole.Window, QPalette.ColorRole.Base, QPalette.ColorRole.Button):
            dark.setColor(role, QColor('#111111'))
        self.app.setPalette(dark)
        self.assertEqual(self.app.palette(), light_palette())
        self.assertEqual(self.app.styleHints().colorScheme(), Qt.ColorScheme.Light)
        window = self.window()
        dialog = OrderDialog(window.clients, window.cars, window.services_page.services, window, order=self.order)
        for widget in (window, dialog, dialog.client_input, dialog.client_input.view()):
            self.assertGreater(widget.palette().color(QPalette.ColorRole.Base).lightness(), 235)

    def test_edit_popup_and_calendar_screenshots_1280x720(self):
        apply_light_theme(self.app)
        window = self.window()
        dialog = OrderDialog(window.clients, window.cars, window.services_page.services, window, order=self.order)
        dialog.show()
        QTest.qWait(30)
        self.assertLessEqual(dialog.frameGeometry().height(), 720)
        capture(window, 'stage92_edit_order.png', dialog)
        dialog.client_input.showPopup()
        QTest.qWait(30)
        popup = dialog.client_input.view().window()
        self.assertTrue(popup.isVisible())
        self.assertLessEqual(popup.height(), 248)
        self.assertTrue(popup.screen().availableGeometry().contains(popup.frameGeometry()))
        capture(window, 'stage92_compact_clients.png', dialog, popup)
        dialog.client_input.hidePopup()
        dialog.service_input.showPopup()
        QTest.qWait(30)
        capture(window, 'stage92_compact_services.png', dialog, dialog.service_input.view().window())
        dialog.service_input.hidePopup()
        dialog.close()
        from autoservice.appointments import AppointmentDialog
        appointment = AppointmentDialog(window.clients, window.cars, window.appointments_page.appointments, window)
        window.show_section('calendar')
        appointment.show()
        QTest.qWait(30)
        field = appointment.date_input
        QTest.mouseClick(field, Qt.MouseButton.LeftButton, pos=field.rect().topRight() + QPoint(-15, 18))
        QTest.qWait(30)
        popup = field.calendarWidget().window()
        self.assertTrue(field.calendarWidget().isVisible())
        capture(window, 'stage92_calendar.png', appointment, popup)


if __name__ == '__main__':
    unittest.main()
