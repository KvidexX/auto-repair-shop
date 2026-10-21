"""Заказ-наряды: снимки документов, подключаемая SQLite и смена статуса."""

import sqlite3

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QStyledItemDelegate, QTableWidget, QTableWidgetItem, QTextEdit,
    QVBoxLayout, QWidget, QStyle,
)

from .data import ORDER_STATUSES, create_order, edit_order, advance_order, normalize_plate, local_now
from .demo_data import make_orders
from .persistence import save_reference_change
from .ui import OwnerComboBox, configure_table, icon

STATUS_COLORS = {
    "Оформлен": ("#EEF2F6", "#526278"), "В работе": ("#EAF1FE", "#3566B8"),
    "Готов к выдаче": ("#E7F5EF", "#26765A"), "Завершён": ("#F0F2F4", "#747D89"),
}


def money(value):
    return f"{value:,} ₽".replace(",", " ")


def number(order):
    return f"ЗН-{order['id']:04d}"


def fill_items(table, items):
    table.setRowCount(len(items))
    for row, item in enumerate(items):
        table.setRowHeight(row, 36)
        for column, value in enumerate((item["name"], money(item["price"]))):
            cell = QTableWidgetItem(value)
            cell.setToolTip(value)
            table.setItem(row, column, cell)


class StatusDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        painter.save()
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        painter.fillRect(option.rect, QColor("#EBF1FD" if selected else "#FFFFFF"))
        text = index.data()
        background, foreground = STATUS_COLORS[text]
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(option.font)
        width = painter.fontMetrics().horizontalAdvance(text) + 28
        badge = QRectF(option.rect.x() + 16, option.rect.center().y() - 13, width, 27)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(background))
        painter.drawRoundedRect(badge, 6, 6)
        painter.setPen(QColor(foreground))
        painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, text)
        painter.setPen(QColor("#EEF1F5"))
        painter.drawLine(option.rect.bottomLeft(), option.rect.bottomRight())
        painter.restore()


class OrderDialog(QDialog):
    def __init__(self, clients, cars, services, parent=None, *, save_order=None, order=None):
        super().__init__(parent)
        self.clients, self.cars, self.services = clients, cars, services
        self.save_order = save_order
        self.saved_order = None
        self.original_order = order
        self.retained_items = {i["service_id"]: {"id": i["service_id"], "name": i["name"], "price": i["price"]} for i in order["items"]} if order else {}
        self.selected_ids = list(self.retained_items)
        self.setWindowTitle("Редактирование заказ-наряда " + number(order) if order else "Новый заказ-наряд")
        self.setObjectName("orderDialog")
        self.setModal(True)
        self.setFixedSize(760, 630)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(8)
        title = QLabel(self.windowTitle())
        title.setObjectName("dialogTitle")
        layout.addWidget(title)
        hint = QLabel("Клиент, автомобиль и перечень выполняемых работ")
        hint.setObjectName("muted")
        layout.addWidget(hint)
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)
        self.client_input = OwnerComboBox()
        self.client_input.addItem("Выберите клиента", None)
        for client in clients:
            self.client_input.addItem(f"{client['name']} · КЛ-{client['id']:04d}", client["id"])
        self.car_input = OwnerComboBox()
        self.reason_input = QLineEdit()
        self.reason_input.setMaxLength(200)
        self.reason_input.setPlaceholderText("Опишите причину обращения")
        for row, caption, field in [(0, "Клиент *", self.client_input), (2, "Автомобиль *", self.car_input),
                                    (4, "Причина обращения *", self.reason_input)]:
            label = QLabel(caption)
            label.setBuddy(field)
            field.setFixedHeight(36)
            grid.addWidget(label, row, 0)
            grid.addWidget(field, row + 1, 0)
        layout.addLayout(grid)
        service_label = QLabel("Услуги *")
        layout.addWidget(service_label)
        chooser = QHBoxLayout()
        self.service_input = OwnerComboBox()
        self.service_input.setFixedHeight(36)
        service_label.setBuddy(self.service_input)
        self.add_item_button = QPushButton("Добавить")
        self.add_item_button.setObjectName("secondary")
        self.add_item_button.setFixedSize(112, 36)
        self.add_item_button.setAutoDefault(False)
        self.add_item_button.clicked.connect(self.add_item)
        chooser.addWidget(self.service_input, 1)
        chooser.addWidget(self.add_item_button)
        layout.addLayout(chooser)
        self.items_table = QTableWidget(0, 2)
        configure_table(self.items_table, ["Выбранные работы", "Стоимость"])
        self.items_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.items_table.setColumnWidth(1, 140)
        self.items_table.setMinimumHeight(116)
        self.items_table.itemSelectionChanged.connect(self.update_remove_button)
        layout.addWidget(self.items_table, 1)
        summary = QHBoxLayout()
        self.remove_item_button = QPushButton("Убрать выбранную")
        self.remove_item_button.setObjectName("secondary")
        self.remove_item_button.setFixedSize(174, 34)
        self.remove_item_button.setAutoDefault(False)
        self.remove_item_button.clicked.connect(self.remove_item)
        summary.addWidget(self.remove_item_button)
        summary.addStretch()
        self.total_label = QLabel()
        self.total_label.setObjectName("orderTotal")
        summary.addWidget(self.total_label)
        layout.addLayout(summary)
        self.error = QLabel("* Обязательные поля · выберите хотя бы одну услугу")
        self.error.setObjectName("formHint")
        self.error.setWordWrap(True)
        self.error.setMinimumHeight(30)
        layout.addWidget(self.error)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.cancel_button = QPushButton("Отмена")
        self.cancel_button.setObjectName("secondary")
        self.cancel_button.setFixedSize(120, 40)
        self.save_button = QPushButton("Сохранить изменения" if order else "Создать заказ")
        self.save_button.setObjectName("primary")
        self.save_button.setFixedSize(190 if order else 156, 40)
        self.save_button.setDefault(True)
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.validate_and_accept)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.save_button)
        layout.addLayout(buttons)
        self.client_input.currentIndexChanged.connect(self.update_cars)
        self.update_cars()
        if order:
            self.client_input.setCurrentIndex(self.client_input.findData(order["client_id"]))
            self.car_input.setCurrentIndex(self.car_input.findData(order["car_id"]))
            self.reason_input.setText(order["reason"])
        self.refresh_items()
        self.client_input.setFocus()

    def update_cars(self):
        client_id = self.client_input.currentData()
        cars = [c for c in self.cars if c["owner_id"] == client_id]
        self.car_input.clear()
        self.car_input.addItem("Выберите автомобиль" if cars else "У клиента нет автомобилей" if client_id is not None else "Сначала выберите клиента", None)
        for car in cars:
            self.car_input.addItem(f"{car['brand']} {car['model']} · {car['plate']} · АВ-{car['id']:04d}", car["id"])
        self.car_input.setEnabled(bool(cars))

    def selected_services(self):
        by_id = {s["id"]: s for s in self.services}
        by_id.update(self.retained_items)
        return [by_id[sid] for sid in self.selected_ids if sid in by_id]

    def refresh_items(self):
        self.service_input.clear()
        self.service_input.addItem("Выберите услугу" if self.services else "Каталог услуг пуст", None)
        for service in self.services:
            if service["id"] not in self.selected_ids:
                self.service_input.addItem(f"{service['name']} · {money(service['price'])}", service["id"])
        self.add_item_button.setEnabled(self.service_input.count() > 1)
        fill_items(self.items_table, self.selected_services())
        self.total_label.setText("Итого: " + money(sum(s["price"] for s in self.selected_services())))
        self.update_remove_button()

    def update_remove_button(self):
        self.remove_item_button.setEnabled(bool(self.items_table.selectionModel().selectedRows()))

    def add_item(self):
        service_id = self.service_input.currentData()
        if service_id is not None and service_id not in self.selected_ids and any(s["id"] == service_id for s in self.services):
            self.selected_ids.append(service_id)
            self.refresh_items()
            self.items_table.selectRow(len(self.selected_ids) - 1)

    def remove_item(self):
        rows = self.items_table.selectionModel().selectedRows()
        if rows:
            sid = self.selected_ids.pop(rows[0].row())
            self.retained_items.pop(sid, None)
            self.refresh_items()

    def fail(self, field, message):
        self.error.setText(message)
        self.error.setStyleSheet("color: #B34B4B;")
        field.setFocus()

    def validate_and_accept(self):
        client = next((c for c in self.clients if c["id"] == self.client_input.currentData()), None)
        if client is None:
            self.fail(self.client_input, "Выберите существующего клиента.")
            return
        car = next((c for c in self.cars if c["id"] == self.car_input.currentData()), None)
        if car is None or car["owner_id"] != client["id"]:
            self.fail(self.car_input, "Выберите автомобиль выбранного клиента.")
            return
        if not self.reason_input.text().strip():
            self.fail(self.reason_input, "Укажите причину обращения.")
            return
        if not self.selected_ids or len(self.selected_services()) != len(self.selected_ids):
            self.fail(self.service_input, "Выберите хотя бы одну услугу из существующего каталога.")
            return
        if self.save_order is not None:
            try:
                self.saved_order = self.save_order(self.values())
            except ValueError as error:
                self.fail(self.save_button, str(error))
                return
            if self.saved_order is None:
                self.fail(self.save_button, "Заказ не сохранён. Введённые данные остались в форме — повторите попытку.")
                return
        self.accept()

    def values(self):
        values = {"client_id": self.client_input.currentData(), "car_id": self.car_input.currentData(),
                  "reason": self.reason_input.text().strip(), "service_ids": list(self.selected_ids)}
        if self.original_order:
            values["reprice_service_ids"] = [sid for sid in self.selected_ids if sid not in self.retained_items]
        return values


class OrderCard(QDialog):
    status_changed = Signal()

    def __init__(self, order, parent=None, *, advance=None, edit=None):
        super().__init__(parent)
        self.order = order
        self.advance = advance
        self.edit = edit
        self.setWindowTitle("Заказ-наряд " + number(order))
        self.setObjectName("orderCard")
        self.setModal(True)
        self.setFixedSize(760, 600)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)
        title = QLabel("Заказ-наряд " + number(order))
        title.setObjectName("dialogTitle")
        layout.addWidget(title)
        date_label = QLabel("Дата создания: " + order["date"].strftime("%d.%m.%Y"))
        date_label.setObjectName("muted")
        layout.addWidget(date_label)
        self.completed_label = QLabel()
        self.completed_label.setObjectName("muted")
        layout.addWidget(self.completed_label)
        car = order["car_snapshot"]
        details = QGridLayout()
        details.setHorizontalSpacing(18)
        for row, caption, value in [(0, "Клиент", order["client_name"]),
                                     (1, "Автомобиль", f"{car['brand']} {car['model']} · {car['plate']}")]:
            label = QLabel(caption)
            label.setObjectName("muted")
            details.addWidget(label, row, 0)
            field = QLineEdit(value)
            field.setObjectName("documentField")
            field.setReadOnly(True)
            field.setCursorPosition(0)
            field.setToolTip(value)
            field.setMinimumHeight(32)
            details.addWidget(field, row, 1)
            if row == 0:
                self.client_field = field
            else:
                self.car_field = field
        layout.addLayout(details)
        layout.addWidget(QLabel("Причина обращения"))
        self.reason_field = QTextEdit()
        self.reason_field.setObjectName("documentReason")
        self.reason_field.setPlainText(order["reason"])
        self.reason_field.setReadOnly(True)
        self.reason_field.setFixedHeight(66)
        layout.addWidget(self.reason_field)
        self.items_table = QTableWidget(0, 2)
        configure_table(self.items_table, ["Перечень работ", "Стоимость при оформлении"])
        self.items_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.items_table.setColumnWidth(1, 220)
        self.items_table.setMinimumHeight(120)
        fill_items(self.items_table, order["items"])
        layout.addWidget(self.items_table, 1)
        total = QLabel("Итого: " + money(order["total"]))
        total.setObjectName("orderTotal")
        total.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(total)
        self.total_label = total
        status_row = QHBoxLayout()
        self.status_label = QLabel()
        self.status_label.setMinimumHeight(32)
        status_row.addWidget(self.status_label)
        status_row.addStretch()
        self.edit_button = QPushButton("Редактировать")
        self.edit_button.setObjectName("secondary")
        self.edit_button.setFixedSize(150, 40)
        self.edit_button.clicked.connect(self.edit_document)
        status_row.addWidget(self.edit_button)
        self.next_button = QPushButton()
        self.next_button.setObjectName("primary")
        self.next_button.setFixedSize(230, 40)
        self.next_button.setAutoDefault(False)
        self.next_button.clicked.connect(self.next_stage)
        status_row.addWidget(self.next_button)
        layout.addLayout(status_row)
        footer = QHBoxLayout()
        hint = QLabel("Сведения завершённого заказа зафиксированы")
        self.document_hint = hint
        hint.setObjectName("muted")
        footer.addWidget(hint)
        footer.addStretch()
        self.close_button = QPushButton("Закрыть")
        self.close_button.setObjectName("secondary")
        self.close_button.setFixedSize(120, 38)
        self.close_button.clicked.connect(self.reject)
        footer.addWidget(self.close_button)
        layout.addLayout(footer)
        self.update_status()

    def edit_document(self):
        if self.edit is None or self.order["status"] == ORDER_STATUSES[-1]:
            return
        saved = self.edit(self.order["id"], self)
        if saved is not None:
            self.order = saved
            self.client_field.setText(saved["client_name"])
            car = saved["car_snapshot"]
            self.car_field.setText(f"{car['brand']} {car['model']} · {car['plate']}")
            for field in (self.client_field, self.car_field):
                field.setToolTip(field.text())
                field.setCursorPosition(0)
            self.reason_field.setPlainText(saved["reason"])
            fill_items(self.items_table, saved["items"])
            self.total_label.setText("Итого: " + money(saved["total"]))
            self.update_status()
            self.status_changed.emit()

    def next_stage(self):
        if self.order["status"] == ORDER_STATUSES[-1]:
            return
        if self.advance is not None:
            saved = self.advance(self.order["id"], self)
            if saved is None:
                return
            self.order = saved
        elif not advance_order(self.order):
            return
        self.update_status()
        self.status_changed.emit()

    def update_status(self):
        status = self.order["status"]
        self.edit_button.setVisible(self.edit is not None and status != ORDER_STATUSES[-1])
        self.document_hint.setVisible(status == ORDER_STATUSES[-1])
        completed = self.order["completed_at"]
        self.completed_label.setText("Дата завершения: " + completed.strftime("%d.%m.%Y · %H:%M") + " (Владивосток, UTC+10)" if completed else "")
        self.completed_label.setVisible(completed is not None)
        background, foreground = STATUS_COLORS[status]
        self.status_label.setText(status)
        self.status_label.setStyleSheet(f"background: {background}; color: {foreground}; border-radius: 6px; padding: 6px 12px;")
        index = ORDER_STATUSES.index(status)
        self.next_button.setEnabled(index < len(ORDER_STATUSES) - 1)
        self.next_button.setText(("Начать работу", "Подготовить к выдаче", "Завершить заказ", "Заказ завершён")[index])
        self.next_button.setToolTip("Следующий этап: " + ORDER_STATUSES[index + 1] if index < len(ORDER_STATUSES) - 1 else "Все этапы завершены")


class OrdersPage(QWidget):
    orders_changed = Signal()

    def __init__(self, clients, cars, services, parent=None, *, demo=True, database=None):
        super().__init__(parent)
        self.clients, self.cars, self.services = clients, cars, services
        self.database = database
        self.orders = (database.list_orders() if database is not None else
                       make_orders(clients, cars, services, local_now().date()) if demo else [])
        self.next_id = None if database is not None else max((o["id"] for o in self.orders), default=0) + 1
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 20)
        layout.setSpacing(0)
        heading = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(6)
        title = QLabel("Заказ-наряды")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Учёт и состояние заказ-нарядов")
        subtitle.setObjectName("muted")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        heading.addLayout(titles)
        heading.addStretch()
        self.add_button = QPushButton("Новый заказ")
        self.add_button.setIcon(icon("plus", "#FFFFFF"))
        self.add_button.setObjectName("primary")
        self.add_button.setFixedSize(163, 42)
        self.add_button.clicked.connect(self.add_order)
        heading.addWidget(self.add_button)
        layout.addLayout(heading)
        layout.addSpacing(26)
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(20, 18, 20, 18)
        toolbar.setSpacing(8)
        caption = QLabel("Все заказы")
        caption.setObjectName("sectionTitle")
        toolbar.addWidget(caption)
        self.total = QLabel()
        self.total.setObjectName("count")
        self.total.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.total.setMinimumWidth(25)
        self.total.setFixedHeight(24)
        toolbar.addWidget(self.total)
        toolbar.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск заказов")
        self.search.setAccessibleName("Поиск заказов")
        self.search.setFixedSize(300, 38)
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icon("search"), QLineEdit.ActionPosition.LeadingPosition)
        self.search.textChanged.connect(lambda: self.refresh())
        toolbar.addWidget(self.search)
        card_layout.addLayout(toolbar)
        self.table = QTableWidget(0, 6)
        configure_table(self.table, ["Номер", "Дата", "Автомобиль", "Клиент", "Стоимость", "Статус"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        for column, width in enumerate([110, 110, 172, 184, 114, 166]):
            self.table.setColumnWidth(column, width)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setItemDelegateForColumn(5, StatusDelegate(self.table))
        self.table.itemSelectionChanged.connect(self.update_actions)
        self.table.cellDoubleClicked.connect(lambda row, column: self.open_order())
        card_layout.addWidget(self.table, 1)
        self.empty = QLabel("Заказы не найдены. Измените запрос или создайте заказ.")
        self.empty.setObjectName("muted")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setMinimumHeight(90)
        card_layout.addWidget(self.empty)
        actions = QHBoxLayout()
        actions.setContentsMargins(20, 12, 20, 12)
        actions.setSpacing(8)
        self.selection_hint = QLabel()
        self.selection_hint.setObjectName("muted")
        actions.addWidget(self.selection_hint)
        actions.addStretch()
        self.open_button = QPushButton("Открыть заказ")
        self.open_button.setObjectName("secondary")
        self.open_button.setFixedSize(150, 38)
        self.open_button.clicked.connect(self.open_order)
        actions.addWidget(self.open_button)
        card_layout.addLayout(actions)
        layout.addWidget(card, 1)
        layout.addSpacing(14)
        self.footer = QLabel()
        self.footer.setObjectName("muted")
        layout.addWidget(self.footer)
        self.refresh()

    def selected_order(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        order_id = self.table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        return next((o for o in self.orders if o["id"] == order_id), None)

    def update_actions(self):
        order = self.selected_order()
        self.open_button.setEnabled(order is not None)
        self.selection_hint.setText("Выбран заказ · " + number(order) if order else "Выберите заказ для просмотра")

    def refresh(self, selected_id=None):
        if selected_id is None:
            selected = self.selected_order()
            selected_id = selected["id"] if selected else None
        query = " ".join(self.search.text().split()).casefold()
        plate_query = normalize_plate(query)
        visible = []
        for order in sorted(self.orders, key=lambda o: (o["date"], o["id"]), reverse=True):
            car = order["car_snapshot"]
            text = f"{number(order)} {order['client_name']} {car['brand']} {car['model']} {car['plate']}".casefold()
            if not query or query in text or (plate_query and plate_query in normalize_plate(car["plate"])):
                visible.append(order)
        self.table.blockSignals(True)
        self.table.clearSelection()
        # Qt удаляет заменённые cellWidget отложенно: скрываем их до изменения строк.
        for row in range(self.table.rowCount()):
            old_widget = self.table.cellWidget(row, 2)
            if old_widget is not None:
                old_widget.hide()
                self.table.removeCellWidget(row, 2)
        self.table.setRowCount(len(visible))
        for row, order in enumerate(visible):
            self.table.setRowHeight(row, 51)
            car = order["car_snapshot"]
            values = [number(order), order["date"].strftime("%d.%m.%Y"), "", order["client_name"],
                      money(order["total"]), order["status"]]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, order["id"])
                    item.setForeground(QColor("#3767B2"))
                if column in (0, 4):
                    font = QFont(self.table.font())
                    font.setWeight(QFont.Weight.DemiBold)
                    item.setFont(font)
                self.table.setItem(row, column, item)
            car_widget = QWidget()
            car_layout = QVBoxLayout(car_widget)
            car_layout.setContentsMargins(16, 9, 4, 8)
            car_layout.setSpacing(2)
            car_label = QLabel(f"{car['brand']} {car['model']}")
            car_label.setToolTip(car_label.text())
            car_layout.addWidget(car_label)
            plate = QLabel(car["plate"])
            plate.setObjectName("plate")
            car_layout.addWidget(plate)
            # Прозрачность для событий сохраняет выделение и двойной щелчок в столбце автомобиля.
            car_widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self.table.setCellWidget(row, 2, car_widget)
            if order["id"] == selected_id:
                self.table.selectRow(row)
        self.table.blockSignals(False)
        self.total.setText(str(len(self.orders)))
        self.footer.setText(f"Найдено: {len(visible)} из {len(self.orders)}")
        self.empty.setVisible(not visible)
        self.table.setVisible(bool(visible))
        self.update_actions()

    def add_order(self):
        dialog = OrderDialog(self.clients, self.cars, self.services, self)
        if self.database is not None:
            dialog.save_order = lambda values: self.create_saved_order(values, dialog)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if self.database is not None:
                order = dialog.saved_order
            else:
                values = dialog.values()
                client = next(c for c in self.clients if c["id"] == values["client_id"])
                car = next(c for c in self.cars if c["id"] == values["car_id"])
                service_by_id = {s["id"]: s for s in self.services}
                order = create_order(self.next_id, local_now().date(), client, car,
                                     [service_by_id[s] for s in values["service_ids"]], values["reason"])
                self.orders.append(order)
                self.next_id += 1
            self.search.clear()
            self.refresh(order["id"])
            self.table.scrollToTop()
            self.orders_changed.emit()

    def save_document(self, operation, parent, *, read_only=False):
        saved, order = save_reference_change(parent, self.database, operation, [
            (self.orders, self.database.list_orders),
        ], read_only=read_only)
        # Карточка и история используют объект из единой загруженной коллекции.
        return next(o for o in self.orders if o["id"] == order["id"]) if saved else None

    def create_saved_order(self, values, parent):
        return self.save_document(lambda: self.database.add_order(**values), parent)

    def advance_saved_order(self, order_id, parent):
        return self.save_document(lambda: self.database.advance_order(order_id), parent)

    def document_changed(self, order_id):
        self.refresh(order_id)
        self.orders_changed.emit()

    def edit_order(self, order_id, parent=None):
        order = next(o for o in self.orders if o["id"] == order_id)
        if self.database is not None:
            order = self.save_document(lambda: self.database.get_order(order_id), parent or self, read_only=True)
        if order is None or order["status"] == ORDER_STATUSES[-1]:
            return None
        dialog = OrderDialog(self.clients, self.cars, self.services, parent or self, order=order)
        def save(values):
            if self.database is not None:
                saved = self.save_document(lambda: self.database.update_order(order_id, **values), dialog)
                if saved is not None:
                    # После COMMIT перечитываем документ. Если повторное чтение
                    # временно недоступно, используем уже проверенный снимок
                    # зафиксированной транзакции: запись действительно сохранена.
                    try:
                        saved.update(self.database.get_order(order_id))
                    except sqlite3.Error:
                        pass
                return saved
            client = next(c for c in self.clients if c["id"] == values["client_id"])
            car = next(c for c in self.cars if c["id"] == values["car_id"])
            updated = edit_order(order, client, car, dialog.selected_services(), values["reason"],
                                 reprice_service_ids=values["reprice_service_ids"])
            order.update(updated)
            return order
        dialog.save_order = save
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.document_changed(order_id)
            return dialog.saved_order
        return None

    def open_order(self):
        order = self.selected_order()
        if order is not None:
            if self.database is not None:
                order = self.save_document(lambda: self.database.get_order(order["id"]), self, read_only=True)
                if order is None:
                    return
                self.document_changed(order["id"])
            dialog = OrderCard(order, self, advance=self.advance_saved_order if self.database is not None else None, edit=self.edit_order)
            dialog.status_changed.connect(lambda: self.document_changed(order["id"]))
            dialog.exec()
            self.refresh(order["id"])

