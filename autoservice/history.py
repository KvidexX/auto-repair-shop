"""Представление завершённых документов из общей коллекции заказ-нарядов."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .data import normalize_plate, normalize_service_name
from .orders import OrderCard, configure_table, money, number
from .ui import icon


class HistoryPage(QWidget):
    def __init__(self, orders, parent=None):
        super().__init__(parent)
        self.orders = orders  # Та же коллекция и те же объекты; отдельного архива нет.
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 20)
        layout.setSpacing(0)
        titles = QVBoxLayout()
        titles.setSpacing(6)
        title = QLabel("История обслуживания")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Архив выполненных ремонтных работ")
        subtitle.setObjectName("muted")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        layout.addLayout(titles)
        layout.addSpacing(26)
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(20, 18, 20, 18)
        toolbar.setSpacing(8)
        caption = QLabel("Завершённые заказы")
        caption.setObjectName("sectionTitle")
        toolbar.addWidget(caption)
        self.total = QLabel()
        self.total.setObjectName("count")
        self.total.setMinimumWidth(25)
        self.total.setFixedHeight(24)
        self.total.setAlignment(Qt.AlignmentFlag.AlignCenter)
        toolbar.addWidget(self.total)
        toolbar.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Номер, клиент, автомобиль, услуга")
        self.search.setAccessibleName("Поиск в истории обслуживания")
        self.search.setFixedSize(320, 38)
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icon("search"), QLineEdit.ActionPosition.LeadingPosition)
        self.search.textChanged.connect(lambda: self.refresh())
        toolbar.addWidget(self.search)
        card_layout.addLayout(toolbar)
        self.table = QTableWidget(0, 6)
        configure_table(self.table, ["Номер заказ-наряда", "Дата завершения", "Автомобиль", "Клиент", "Выполненные работы", "Итоговая стоимость"])
        header = self.table.horizontalHeader()
        header.setMinimumSectionSize(110)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        for column, width in [(0, 145), (1, 138), (2, 150), (3, 166), (5, 150)]:
            self.table.setColumnWidth(column, width)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self.update_actions)
        self.table.cellDoubleClicked.connect(lambda row, column: self.open_order())
        card_layout.addWidget(self.table, 1)
        self.empty = QLabel()
        self.empty.setObjectName("muted")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setMinimumHeight(100)
        card_layout.addWidget(self.empty)
        actions = QHBoxLayout()
        actions.setContentsMargins(20, 12, 20, 12)
        actions.setSpacing(8)
        self.selection_hint = QLabel()
        self.selection_hint.setObjectName("muted")
        actions.addWidget(self.selection_hint)
        actions.addStretch()
        self.open_button = QPushButton("Просмотреть заказ")
        self.open_button.setObjectName("secondary")
        self.open_button.setFixedSize(184, 38)
        self.open_button.clicked.connect(self.open_order)
        actions.addWidget(self.open_button)
        card_layout.addLayout(actions)
        layout.addWidget(card, 1)
        layout.addSpacing(14)
        self.footer = QLabel()
        self.footer.setObjectName("muted")
        layout.addWidget(self.footer)
        self.refresh()

    def completed_orders(self, car_id=None):
        """История конкретной машины определяется ID, независимо от её реквизитов."""
        return sorted((o for o in self.orders if o["status"] == "Завершён"
                       and (car_id is None or o["car_id"] == car_id)),
                      key=lambda o: (o["completed_at"], o["id"]), reverse=True)

    def selected_order(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        order_id = self.table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        return next((o for o in self.orders if o["id"] == order_id and o["status"] == "Завершён"), None)

    def update_actions(self):
        order = self.selected_order()
        self.open_button.setEnabled(order is not None)
        self.selection_hint.setText("Выбран заказ · " + number(order) if order else "Выберите завершённый заказ для просмотра")

    def refresh(self):
        selected = self.selected_order()
        selected_id = selected["id"] if selected else None
        completed = self.completed_orders()
        query = normalize_service_name(self.search.text())
        plate_query = normalize_plate(query)
        visible = []
        for order in completed:
            car = order["car_snapshot"]
            text = normalize_service_name(f"{number(order)} {order['client_name']} {car['brand']} {car['model']} {car['plate']} "
                                          + " ".join(i["name"] for i in order["items"]))
            if not query or query in text or (plate_query and plate_query in normalize_plate(car["plate"])):
                visible.append(order)
        self.table.blockSignals(True)
        self.table.clearSelection()
        self.table.setRowCount(len(visible))
        for row, order in enumerate(visible):
            self.table.setRowHeight(row, 61)
            car = order["car_snapshot"]
            full_works = "; ".join(i["name"] for i in order["items"])
            parts = order["client_name"].split()
            name = " ".join(parts[:2]) + ("\n" + " ".join(parts[2:]) if len(parts) > 2 else "")
            values = [number(order), order["completed_at"].strftime("%d.%m.%Y\n%H:%M"),
                      f"{car['brand']} {car['model']}\n{car['plate']}", name,
                      "; ".join(i["name"] for i in order["items"][:2]) + (f"; ещё {len(order['items']) - 2}" if len(order["items"]) > 2 else ""),
                      money(order["total"])]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(full_works if column == 4 else value.replace("\n", " "))
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, order["id"])
                    item.setForeground(QColor("#3767B2"))
                elif column == 1:
                    item.setToolTip(order["completed_at"].strftime("%d.%m.%Y %H:%M:%S") + " · Владивосток, UTC+10")
                self.table.setItem(row, column, item)
            if order["id"] == selected_id:
                self.table.selectRow(row)
        self.table.blockSignals(False)
        self.total.setText(str(len(completed)))
        self.footer.setText(f"Найдено: {len(visible)} из {len(completed)} завершённых заказов  ·  Сведения на момент оформления")
        self.empty.setText("Завершённых заказов пока нет. Они появятся здесь после завершения работ."
                           if not completed else "Заказы не найдены. Измените или очистите поисковый запрос.")
        self.empty.setVisible(not visible)
        self.table.setVisible(bool(visible))
        self.update_actions()

    def open_order(self):
        order = self.selected_order()
        if order is not None:
            OrderCard(order, self).exec()
            self.refresh()
