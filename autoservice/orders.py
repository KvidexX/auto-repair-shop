"""Заказ-наряды: снимки документов в памяти и последовательная смена статуса."""

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QStyledItemDelegate, QTableWidget, QTableWidgetItem, QTextEdit,
    QVBoxLayout, QWidget, QStyle,
)

from .data import ORDER_STATUSES, create_order, advance_order, make_orders, normalize_plate, local_now
from .ui import OwnerComboBox, RowSelectionDelegate, icon

STATUS_COLORS = {
    "Оформлен": ("#EEF2F6", "#526278"), "В работе": ("#EAF1FE", "#3566B8"),
    "Готов к выдаче": ("#E7F5EF", "#26765A"), "Завершён": ("#F0F2F4", "#747D89"),
}


def money(value):
    return f"{value:,} ₽".replace(",", " ")


def number(order):
    return f"ЗН-{order['id']:04d}"


def configure_table(table, headers):
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().hide()
    table.setShowGrid(False)
    table.setWordWrap(False)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setItemDelegate(RowSelectionDelegate(table))
    table.setFrameShape(QFrame.Shape.NoFrame)
    table.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
    header = table.horizontalHeader()
    header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    header.setFixedHeight(42)
    header.setHighlightSections(False)
    header.setMinimumSectionSize(80)
    header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)


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
    def __init__(self, clients, cars, services, parent=None):
        super().__init__(parent)
        self.clients, self.cars, self.services = clients, cars, services
        self.selected_ids = []
        self.setWindowTitle("Новый заказ-наряд")
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
        self.save_button = QPushButton("Создать заказ")
        self.save_button.setObjectName("primary")
        self.save_button.setFixedSize(156, 40)
        self.save_button.setDefault(True)
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.validate_and_accept)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.save_button)
        layout.addLayout(buttons)
        self.client_input.currentIndexChanged.connect(self.update_cars)
        self.update_cars()
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
            del self.selected_ids[rows[0].row()]
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
        self.accept()

    def values(self):
        return {"client_id": self.client_input.currentData(), "car_id": self.car_input.currentData(),
                "reason": self.reason_input.text().strip(), "service_ids": list(self.selected_ids)}


class OrderCard(QDialog):
    status_changed = Signal()

    def __init__(self, order, parent=None):
        super().__init__(parent)
        self.order = order
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
        status_row = QHBoxLayout()
        self.status_label = QLabel()
        self.status_label.setMinimumHeight(32)
        status_row.addWidget(self.status_label)
        status_row.addStretch()
        self.next_button = QPushButton()
        self.next_button.setObjectName("primary")
        self.next_button.setFixedSize(230, 40)
        self.next_button.setAutoDefault(False)
        self.next_button.clicked.connect(self.next_stage)
        status_row.addWidget(self.next_button)
        layout.addLayout(status_row)
        footer = QHBoxLayout()
        hint = QLabel("Состав работ и сведения документа зафиксированы")
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

    def next_stage(self):
        if advance_order(self.order):
            self.update_status()
            self.status_changed.emit()

    def update_status(self):
        status = self.order["status"]
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

    def __init__(self, clients, cars, services, parent=None):
        super().__init__(parent)
        self.clients, self.cars, self.services = clients, cars, services
        self.orders = make_orders(clients, cars, services, local_now().date())
        self.next_id = max(o["id"] for o in self.orders) + 1
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
        self.footer.setText(f"Найдено: {len(visible)} из {len(self.orders)}  ·  Изменения хранятся только до закрытия приложения")
        self.empty.setVisible(not visible)
        self.table.setVisible(bool(visible))
        self.update_actions()

    def add_order(self):
        dialog = OrderDialog(self.clients, self.cars, self.services, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
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

    def open_order(self):
        order = self.selected_order()
        if order is not None:
            dialog = OrderCard(order, self)
            dialog.status_changed.connect(self.orders_changed.emit)
            dialog.exec()
            self.refresh(order["id"])

