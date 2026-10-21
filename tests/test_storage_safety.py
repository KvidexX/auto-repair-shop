"""Регрессия сохранности миграций, транзакций и согласованных чтений SQLite."""
from contextlib import closing
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from autoservice.database import Database, SCHEMA
from autoservice.demo_data import load_demo_data
from tests import test_database as helpers


def create_v1(path):
    """Реальный формат v1 без запуска современной миграции."""
    legacy = Database.__new__(Database)
    legacy.path = path
    legacy._connection = sqlite3.connect(path, isolation_level=None)
    legacy._connection.row_factory = sqlite3.Row
    legacy._savepoint = 0
    legacy._connection.executescript(SCHEMA + 'PRAGMA user_version=1;')
    try:
        load_demo_data(legacy)
    finally:
        legacy.close()


class StorageSafetyTests(unittest.TestCase):
    setUp = helpers.DatabaseTests.setUp
    tearDown = helpers.DatabaseTests.tearDown
    fixtures = helpers.DatabaseTests.fixtures
    create_document = helpers.DatabaseTests.create_document

    def legacy_path(self):
        path = Path(self.temporary.name) / 'legacy.db'
        create_v1(path)
        return path

    def version(self, path):
        with closing(sqlite3.connect(path)) as connection:
            return connection.execute('PRAGMA user_version').fetchone()[0]

    def test_backup_is_valid_v1_copy_and_current_database_preserves_every_table(self):
        path = self.legacy_path()
        with closing(sqlite3.connect(path)) as raw:
            before = {table: raw.execute(f'SELECT * FROM {table} ORDER BY id').fetchall()
                      for table in helpers.TABLES}
        with Database(path) as migrated:
            backup = migrated.backup_path
            self.assertTrue(backup.is_file())
            self.assertEqual(self.version(backup), 1)
            with closing(sqlite3.connect(backup)) as copy:
                self.assertEqual(copy.execute('PRAGMA integrity_check').fetchall(), [('ok',)])
                self.assertEqual(copy.execute('PRAGMA foreign_key_check').fetchall(), [])
                for table, rows in before.items():
                    self.assertEqual(copy.execute(f'SELECT * FROM {table} ORDER BY id').fetchall(), rows)
                    self.assertEqual([tuple(r) for r in migrated._connection.execute(f'SELECT * FROM {table} ORDER BY id')], rows)
            self.assertEqual(self.version(path), 2)
        with Database(path) as reopened:
            self.assertIsNone(reopened.backup_path)
        self.assertEqual(list((path.parent / 'backups').glob('*.sqlite3')), [backup])

    def test_unwritable_backup_location_prevents_migration_and_retry_succeeds(self):
        path = self.legacy_path()
        directory = path.parent / 'backups'
        directory.write_text('Не каталог', encoding='utf-8')
        before = path.read_bytes()
        with self.assertRaises(OSError):
            Database(path)
        self.assertEqual(self.version(path), 1)
        self.assertEqual(path.read_bytes(), before)
        directory.unlink()
        with Database(path) as migrated:
            self.assertEqual(self.version(path), 2)
            self.assertTrue(migrated.backup_path.exists())

    def test_failed_online_backup_cleans_partial_copy_and_never_migrates(self):
        path = self.legacy_path()
        original_connect = sqlite3.connect
        class Failure(sqlite3.Connection):
            def backup(self, *args, **kwargs):
                raise sqlite3.OperationalError('Имитируем ошибку копирования')
        def connect(*args, **kwargs):
            return original_connect(*args, factory=Failure, **kwargs)
        with patch('autoservice.database.sqlite3.connect', connect), self.assertRaises(sqlite3.OperationalError):
            Database(path)
        self.assertEqual(self.version(path), 1)
        self.assertEqual(list((path.parent / 'backups').glob('*')), [])
        with Database(path) as migrated:
            self.assertTrue(migrated.backup_path.exists())
            self.assertEqual(len(migrated.list_orders()), 7)

    def test_migration_failure_keeps_backup_and_retry_does_not_overwrite_it(self):
        path = self.legacy_path()
        import autoservice.database as module
        with patch.object(module, 'MIGRATION_2', module.MIGRATION_2 + 'INVALID SQL;'):
            with self.assertRaises(sqlite3.Error):
                Database(path)
        backup = next((path.parent / 'backups').glob('*.sqlite3'))
        original = (backup.read_bytes(), backup.stat().st_mtime_ns)
        self.assertEqual(self.version(path), 1)
        with Database(path) as migrated:
            self.assertNotEqual(backup, migrated.backup_path)
            self.assertEqual(len(migrated.list_orders(completed_only=True)), 2)
        self.assertEqual((backup.read_bytes(), backup.stat().st_mtime_ns), original)
        self.assertEqual(len(list((path.parent / 'backups').glob('*.sqlite3'))), 2)

    def test_backup_includes_committed_wal_data(self):
        path = self.legacy_path()
        with closing(sqlite3.connect(path, isolation_level=None)) as writer:
            self.assertEqual(writer.execute('PRAGMA journal_mode=WAL').fetchone()[0], 'wal')
            writer.execute("INSERT INTO clients(name,phone,note) VALUES('Клиент в WAL','1','')")
            self.assertTrue(Path(str(path) + '-wal').exists())
            with Database(path) as migrated:
                with closing(sqlite3.connect(migrated.backup_path)) as backup:
                    self.assertEqual(backup.execute('SELECT name FROM clients ORDER BY id DESC LIMIT 1').fetchone()[0], 'Клиент в WAL')
                self.assertEqual(migrated.list_clients()[-1]['name'], 'Клиент в WAL')

    def test_new_or_current_database_does_not_create_migration_backups(self):
        self.assertIsNone(self.db.backup_path)
        with Database(self.path) as reopened:
            self.assertIsNone(reopened.backup_path)
        self.assertFalse((self.path.parent / 'backups').exists())

    def test_order_reads_work_while_another_connection_reserves_writer(self):
        _, _, _, order = self.create_document()
        self.db._connection.execute('PRAGMA busy_timeout=0')
        with Database(self.path) as writer:
            with writer.transaction():
                writer._connection.execute("UPDATE orders SET reason='Ещё не сохранено' WHERE id=?", (order['id'],))
                self.assertEqual(self.db.get_order(order['id']), order)
                self.assertEqual(self.db.list_orders(), [order])
        self.assertEqual(self.db.get_order(order['id'])['reason'], 'Ещё не сохранено')

    def test_header_and_items_use_same_read_snapshot_during_concurrent_commit(self):
        client, car, service, order = self.create_document()
        self.db._connection.execute('PRAGMA journal_mode=WAL')
        second = self.db.add_service('Дополнительная работа', 'Ремонт', 300)
        get = self.db._get
        with Database(self.path) as writer:
            def concurrent_get(table, record_id):
                record = get(table, record_id)
                if table == 'orders':
                    writer.update_order(order['id'], client['id'], car['id'], [service['id'], second['id']], 'Изменено')
                return record
            with patch.object(self.db, '_get', concurrent_get):
                self.assertEqual(self.db.get_order(order['id']), order)
        current = self.db.get_order(order['id'])
        self.assertEqual(current['total'], 1800)
        self.assertEqual(len(current['items']), 2)

    def test_list_ids_and_documents_share_a_snapshot(self):
        client, car, service, order = self.create_document()
        self.db._connection.execute('PRAGMA journal_mode=WAL')
        get = self.db.get_order
        with Database(self.path) as writer:
            def concurrent_get(record_id):
                writer.add_order(client['id'], car['id'], [service['id']], 'Новый параллельный заказ')
                return get(record_id)
            with patch.object(self.db, 'get_order', concurrent_get):
                self.assertEqual(self.db.list_orders(), [order])
        self.assertEqual(len(self.db.list_orders()), 2)

    def test_commit_rejects_total_count_and_missing_items_and_rolls_back(self):
        _, _, _, order = self.create_document()
        for sql in ['UPDATE orders SET total=1 WHERE id=?', 'UPDATE orders SET item_count=2 WHERE id=?',
                    'DELETE FROM order_items WHERE order_id=?']:
            with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError):
                with self.db.transaction():
                    self.db._connection.execute(sql, (order['id'],))
            self.assertEqual(self.db.get_order(order['id']), order)

    def test_read_transaction_cannot_commit_inconsistent_write(self):
        _, _, _, order = self.create_document()
        with self.assertRaises(sqlite3.IntegrityError):
            with self.db.transaction(write=False):
                self.db._connection.execute('UPDATE orders SET total=0 WHERE id=?', (order['id'],))
        self.assertEqual(self.db.get_order(order['id']), order)

    def test_silently_missing_item_rolls_back_creation_and_edit(self):
        client, car, service, order = self.create_document()
        second = self.db.add_service('Дополнительная работа', 'Ремонт', 300)
        insert = self.db._insert
        def omit(table, values):
            if table == 'order_items' and values['position'] == 1:
                return None
            return insert(table, values)
        with patch.object(self.db, '_insert', omit):
            with self.assertRaises(sqlite3.IntegrityError):
                self.db.add_order(client['id'], car['id'], [service['id'], second['id']], 'Создание')
            with self.assertRaises(sqlite3.IntegrityError):
                self.db.update_order(order['id'], client['id'], car['id'], [service['id'], second['id']], 'Изменение')
        self.assertEqual(self.db.list_orders(), [order])


if __name__ == '__main__':
    unittest.main()
