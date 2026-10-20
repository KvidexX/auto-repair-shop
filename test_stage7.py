"""История — завершённые документы общей коллекции, без отдельного хранилища."""

import copy
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
import unittest

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QTableWidget

import test_stage6 as helpers
from data import LOCAL_TIMEZONE, advance_order, local_now
from orders import OrderCard, number


class HistoryTests(unittest.TestCase):
    setUpClass = classmethod(helpers.OrdersTests.setUpClass.__func__)
    setUp = helpers.OrdersTests.setUp
    tearDown = helpers.OrdersTests.tearDown
    reference_data = helpers.OrdersTests.reference_data
    modal = helpers.OrdersTests.modal
    choose = helpers.OrdersTests.choose

    def history(self):
        self.window.show_section("history")
        return self.window.history_page

    def test_shared_source_completed_only_and_dates(self):
        h, p = self.history(), self.page
        self.assertIs(h.orders, p.orders)
        self.assertEqual(len(p.orders), 7)
        self.assertEqual(h.table.rowCount(), 2)
        self.assertEqual(h.total.text(), "2")
        self.assertEqual([o["id"] for o in h.completed_orders()], [23, 21])
        for order in p.orders:
            if order["status"] == "Завершён":
                self.assertIsInstance(order["completed_at"], datetime)
                self.assertEqual(order["completed_at"].utcoffset(), timedelta(hours=10))
                self.assertEqual(order["completed_at"].tzname(), "Asia/Vladivostok")
                self.assertGreaterEqual(order["completed_at"].date(), order["date"])
                self.assertLess(order["completed_at"], local_now().replace(tzinfo=LOCAL_TIMEZONE))
                self.assertIs(next(o for o in h.completed_orders() if o["id"] == order["id"]), order)
            else:
                self.assertIsNone(order["completed_at"])

    def test_completion_auto_appears_and_timestamp_is_written_once(self):
        h, p = self.history(), self.page
        self.window.show_section("orders")
        self.choose(p.table, 27)
        order = p.selected_order()
        created_on = order["date"]
        now = local_now().replace(microsecond=123456)
        def complete(card):
            self.assertIsInstance(card, OrderCard)
            self.assertIsNone(order["completed_at"])
            card.next_button.click()
            self.assertEqual(order["status"], "Готов к выдаче")
            self.assertIsNone(order["completed_at"])
            self.assertEqual(h.table.rowCount(), 2)
            with patch("data.local_now", return_value=now):
                card.next_button.click()
            self.assertEqual(order["completed_at"], now.replace(tzinfo=LOCAL_TIMEZONE))
            self.assertEqual(h.table.rowCount(), 3)  # Обновление по сигналу ещё до закрытия карточки.
            self.assertIn(now.strftime("%d.%m.%Y"), card.completed_label.text())
            card.close_button.click()
        self.modal(complete)
        p.open_button.click()
        self.assertEqual(order["date"], created_on)
        self.assertEqual(len(p.orders), 7)
        self.assertEqual(self.history().total.text(), "3")
        self.assertEqual(h.table.item(0, 0).text(), number(order))
        snapshot = copy.deepcopy(order)
        self.choose(h.table, order["id"])
        def inspect(card):
            self.assertFalse(card.next_button.isEnabled())
            with patch("data.local_now", return_value=now + timedelta(days=10)):
                card.next_stage()
                self.assertFalse(advance_order(order))
            card.close_button.click()
        self.modal(inspect)
        h.open_button.click()
        self.assertEqual(order, snapshot)
        self.window.show_section("orders")
        self.window.show_section("history")
        self.assertEqual(order["completed_at"], snapshot["completed_at"])

    def test_search_all_historical_fields_and_empty_result(self):
        h = self.history()
        for query, count in [("ЗН-0023", 1), ("ЛЕБЕДЕВ", 1), ("Volkswagen Polo", 1),
                             ("b 567 yc 125", 1), ("Замена   ремня", 1),
                             ("Проверка тормозов", 0), ("", 2)]:
            h.search.setText(query)
            self.assertEqual(h.table.rowCount(), count, query)
            self.assertEqual(h.total.text(), "2")
        h.search.setText("Нет такой записи")
        self.assertTrue(h.empty.isVisible())
        self.assertFalse(h.open_button.isEnabled())
        self.assertIn("не найдены", h.empty.text())
        h.search.clear()
        self.assertFalse(h.empty.isVisible())
        self.assertIn("Замена ремня привода", h.table.item(0, 4).toolTip())

    def test_card_button_double_click_and_readonly(self):
        h = self.history()
        self.choose(h.table, 23)
        order = h.selected_order()
        before = copy.deepcopy(order)
        def inspect(card):
            self.assertIsInstance(card, OrderCard)
            self.assertIs(card.order, order)
            self.assertTrue(card.client_field.isReadOnly())
            self.assertTrue(card.car_field.isReadOnly())
            self.assertTrue(card.reason_field.isReadOnly())
            self.assertEqual(card.items_table.editTriggers(), QTableWidget.EditTrigger.NoEditTriggers)
            self.assertFalse(card.next_button.isEnabled())
            self.assertIn(order["completed_at"].strftime("%d.%m.%Y"), card.completed_label.text())
            self.assertEqual(card.items_table.rowCount(), len(order["items"]))
            self.assertEqual(card.reason_field.toPlainText(), order["reason"])
            card.close_button.click()
        self.modal(inspect)
        h.open_button.click()
        pos = h.table.visualItemRect(h.table.item(0, 0)).center()
        self.modal(inspect)
        QTest.mouseClick(h.table.viewport(), Qt.MouseButton.LeftButton, pos=pos)
        QTest.mouseDClick(h.table.viewport(), Qt.MouseButton.LeftButton, pos=pos)
        self.assertEqual(order, before)

    def test_snapshots_survive_actual_reference_edits(self):
        w, p = self.window, self.page
        before = copy.deepcopy(p.orders)
        w.show_section("clients")
        self.choose(w.client_table, 5)
        def rename(d):
            d.name_input.setText("Другое Имя Клиента")
            d.save_button.click()
        self.modal(rename)
        w.edit_client_button.click()
        w.show_section("car")
        self.choose(w.car_table, 5)
        def transfer(d):
            d.brand_input.setText("Honda")
            d.model_input.setText("Fit")
            d.plate_input.setText("Е111АА125")
            d.owner_input.setCurrentIndex(d.owner_input.findData(2))
            d.save_button.click()
        self.modal(transfer)
        w.edit_car_button.click()
        sp = w.services_page
        w.show_section("services")
        self.choose(sp.table, 9)
        def reprice(d):
            d.name_input.setText("Другое название работы")
            d.price_input.setText("9900")
            d.save_button.click()
        self.modal(reprice)
        sp.edit_button.click()
        h = self.history()
        self.assertEqual(p.orders, before)
        for query in ("Лебедев", "Volkswagen Polo", "В567УС125", "Замена ремня привода"):
            h.search.setText(query)
            self.assertEqual(h.table.rowCount(), 1)
            self.assertEqual(h.table.item(0, 0).text(), "ЗН-0023")
        for query in ("Другое Имя Клиента", "Honda Fit", "Е111АА125", "Другое название работы"):
            h.search.setText(query)
            self.assertEqual(h.table.rowCount(), 0)
        document = next(o for o in h.orders if o["id"] == 23)
        self.assertEqual(document["car_id"], 5)
        self.assertEqual(document["client_id"], 5)
        self.assertEqual(document["items"][1]["price"], 2000)
        self.references = copy.deepcopy(self.reference_data())

    def test_car_id_filter_sorting_and_no_archive_storage(self):
        h = self.history()
        first, second = h.completed_orders()
        # Совпавший исторический госномер не объединяет историю разных ID машин.
        second["car_snapshot"]["plate"] = first["car_snapshot"]["plate"]
        self.assertEqual(h.completed_orders(car_id=first["car_id"]), [first])
        self.assertEqual(h.completed_orders(car_id=second["car_id"]), [second])
        self.assertEqual(h.completed_orders(car_id=999), [])
        second["completed_at"] = first["completed_at"] + timedelta(minutes=1)
        h.refresh()
        self.assertEqual(h.table.item(0, 0).text(), number(second))
        self.assertEqual(len(self.page.orders), 7)
        self.assertIs(h.orders, self.page.orders)
        # Отдельный сценарий пустой истории, без удаления самих документов.
        for order in h.orders:
            if order["status"] == "Завершён":
                order["status"] = "Готов к выдаче"
                order["completed_at"] = None
        h.refresh()
        self.assertEqual(h.table.rowCount(), 0)
        self.assertEqual(h.total.text(), "0")
        self.assertIn("пока нет", h.empty.text())

    def test_navigation_layout_and_screenshots(self):
        w, h = self.window, self.history()
        for key, index in [("orders", 0), ("clients", 1), ("car", 2), ("services", 3), ("calendar", 4), ("history", 5)]:
            self.assertTrue(w.nav_buttons[key].isEnabled())
            w.nav_buttons[key].click()
            self.assertEqual(w.pages.currentIndex(), index)
            self.assertEqual(w.nav_buttons[key].objectName(), "activeNav")
        self.assertEqual((w.width(), w.height()), (1280, 720))
        self.assertEqual(h.table.horizontalScrollBar().maximum(), 0)
        self.choose(h.table, 23)
        QTest.qWait(30)
        output = Path(__file__).resolve().parent / "screenshots"
        self.assertTrue(w.grab().save(str(output / "history.png"), "PNG"))
        card = OrderCard(h.selected_order(), w)
        card.show()
        QTest.qWait(40)
        self.assertTrue(w.frameGeometry().contains(card.frameGeometry()))
        self.assertLess(card.frameGeometry().height(), 680)
        self.assertTrue(card.rect().contains(card.close_button.geometry()))
        self.assertTrue(card.grab().save(str(output / "completed_order.png"), "PNG"))
        card.reject()


if __name__ == "__main__":
    unittest.main()
