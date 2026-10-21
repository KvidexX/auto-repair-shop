"""Главное окно, навигация и связанные справочники клиентов и автомобилей."""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QStackedWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from .demo_data import CLIENTS, CARS
from .data import normalize_plate
from .ui import icon, configure_table
from .services import ServicesPage
from .appointments import AppointmentsPage, PLANNED
from .orders import OrdersPage
from .history import HistoryPage
from .persistence import save_reference_change
from .dialogs import ClientDialog, CarDialog


class MainWindow(QMainWindow):
    def __init__(self, database=None):
        super().__init__()
        self.database = database
        self.clients = database.list_clients() if database is not None else [dict(client) for client in CLIENTS]
        self.cars = database.list_cars() if database is not None else [dict(car) for car in CARS]
        self.next_car_id = max((car["id"] for car in self.cars), default=0) + 1
        self.next_client_id = max((client["id"] for client in self.clients), default=0) + 1
        self.nav_buttons = {}
        self.setWindowTitle("АвтоСервис — Заказ-наряды")
        self.resize(1280, 720)
        self.setMinimumSize(1080, 640)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.build_sidebar())
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        self.pages = QStackedWidget()
        self.services_page = ServicesPage(database=database)
        self.orders_page = OrdersPage(self.clients, self.cars, self.services_page.services, database=database, demo=database is None)
        self.pages.addWidget(self.orders_page)
        self.pages.addWidget(self.build_clients())
        self.pages.addWidget(self.build_cars())
        self.pages.addWidget(self.services_page)
        self.appointments_page = AppointmentsPage(self.clients, self.cars, database=database, demo=database is None)
        self.pages.addWidget(self.appointments_page)
        self.history_page = HistoryPage(self.orders_page.orders)
        self.pages.addWidget(self.history_page)
        self.orders_page.orders_changed.connect(self.history_page.refresh)
        right_layout.addWidget(self.pages, 1)
        layout.addWidget(right, 1)
        self.show_section("orders")

    def show_section(self, name):
        if name == "history":
            self.history_page.refresh()
        self.pages.setCurrentIndex({"orders": 0, "clients": 1, "car": 2, "services": 3, "calendar": 4, "history": 5}[name])
        self.setWindowTitle("АвтоСервис — " + {"clients": "Клиенты", "car": "Автомобили", "orders": "Заказ-наряды", "services": "Каталог услуг", "calendar": "Запись на обслуживание", "history": "История обслуживания"}[name])
        for key, button in self.nav_buttons.items():
            active = key == name
            button.setObjectName("activeNav" if active else "nav")
            button.setIcon(icon(key, "#386BD6" if active else "#8B96A7"))
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()

    def build_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(228)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 25, 16, 20)
        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(10, 0, 0, 0)
        mark = QLabel()
        mark.setPixmap(icon("car", "#386BD6").pixmap(30, 30))
        brand_row.addWidget(mark)
        brand = QLabel("АвтоСервис")
        brand.setObjectName("brand")
        brand_row.addWidget(brand)
        brand_row.addStretch()
        layout.addLayout(brand_row)
        subtitle = QLabel("УЧЁТ И ОБСЛУЖИВАНИЕ")
        subtitle.setObjectName("subtitle")
        subtitle.setContentsMargins(10, 5, 0, 28)
        layout.addWidget(subtitle)
        for label, name in [
            ("Заказ-наряды", "orders"), ("Клиенты", "clients"),
            ("Автомобили", "car"), ("Запись на обслуживание", "calendar"),
            ("Каталог услуг", "services"), ("История обслуживания", "history"),
        ]:
            button = QPushButton(label)
            button.setIcon(icon(name, "#386BD6" if name == "orders" else "#8B96A7"))
            button.setIconSize(QSize(21, 21))
            button.setFixedHeight(46)
            button.setObjectName("activeNav" if name == "orders" else "nav")
            self.nav_buttons[name] = button
            button.clicked.connect(lambda checked=False, section=name: self.show_section(section))
            layout.addWidget(button)
        layout.addStretch()
        return sidebar

    def build_clients(self):
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 28, 32, 20)
        layout.setSpacing(0)
        title_row = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(6)
        title = QLabel("Клиенты")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Контактные данные клиентов и их автомобили")
        subtitle.setObjectName("muted")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        title_row.addLayout(titles)
        title_row.addStretch()
        self.add_client_button = QPushButton("Добавить клиента")
        self.add_client_button.setIcon(icon("plus", "#FFFFFF"))
        self.add_client_button.setObjectName("primary")
        self.add_client_button.setFixedSize(187, 42)
        self.add_client_button.clicked.connect(self.add_client)
        title_row.addWidget(self.add_client_button)
        layout.addLayout(title_row)
        layout.addSpacing(26)
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(20, 18, 20, 18)
        caption = QLabel("Все клиенты")
        toolbar.setSpacing(8)
        caption.setObjectName("sectionTitle")
        toolbar.addWidget(caption)
        self.client_count = QLabel()
        self.client_count.setObjectName("count")
        self.client_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.client_count.setFixedSize(25, 24)
        toolbar.addWidget(self.client_count)
        toolbar.addStretch()
        self.client_search = QLineEdit()
        self.client_search.setPlaceholderText("Поиск по ФИО или телефону")
        self.client_search.setAccessibleName("Поиск клиентов")
        self.client_search.addAction(icon("search"), QLineEdit.ActionPosition.LeadingPosition)
        self.client_search.setFixedSize(300, 38)
        self.client_search.setClearButtonEnabled(True)
        self.client_search.textChanged.connect(lambda: self.refresh_clients())
        toolbar.addWidget(self.client_search)
        card_layout.addLayout(toolbar)
        self.client_table = QTableWidget(0, 4)
        table = self.client_table
        configure_table(table, ["ID", "ФИО", "Телефон", "Количество автомобилей"], minimum=70)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(0, 80)
        table.setColumnWidth(2, 200)
        table.setColumnWidth(3, 205)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setMinimumSectionSize(70)
        table.itemSelectionChanged.connect(self.update_client_actions)
        table.cellDoubleClicked.connect(lambda row, column: self.edit_client())
        card_layout.addWidget(table, 1)
        self.empty_clients = QLabel("Клиенты не найдены. Измените запрос или добавьте клиента.")
        self.empty_clients.setObjectName("muted")
        self.empty_clients.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_clients.setMinimumHeight(90)
        card_layout.addWidget(self.empty_clients)
        actions = QHBoxLayout()
        actions.setContentsMargins(20, 12, 20, 12)
        actions.setSpacing(8)
        self.selection_hint = QLabel("Выберите клиента в таблице")
        self.selection_hint.setObjectName("muted")
        actions.addWidget(self.selection_hint)
        actions.addStretch()
        self.edit_client_button = QPushButton("Редактировать")
        self.edit_client_button.setObjectName("secondary")
        self.edit_client_button.setFixedSize(142, 38)
        self.edit_client_button.clicked.connect(self.edit_client)
        self.delete_client_button = QPushButton("Удалить")
        self.delete_client_button.setObjectName("danger")
        self.delete_client_button.setFixedSize(100, 38)
        self.delete_client_button.clicked.connect(self.delete_client)
        actions.addWidget(self.edit_client_button)
        actions.addWidget(self.delete_client_button)
        card_layout.addLayout(actions)
        layout.addWidget(card, 1)
        layout.addSpacing(14)
        self.clients_footer = QLabel()
        self.clients_footer.setObjectName("muted")
        layout.addWidget(self.clients_footer)
        self.refresh_clients()
        return content

    def selected_client(self):
        rows = self.client_table.selectionModel().selectedRows()
        if not rows:
            return None
        client_id = self.client_table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        return next((client for client in self.clients if client["id"] == client_id), None)

    def update_client_actions(self):
        client = self.selected_client()
        self.edit_client_button.setEnabled(client is not None)
        self.delete_client_button.setEnabled(client is not None)
        self.selection_hint.setText(f"Выбран клиент · КЛ-{client['id']:04d}" if client else "Выберите клиента в таблице")

    def refresh_clients(self, selected_id=None):
        if selected_id is None:
            selected = self.selected_client()
            selected_id = selected["id"] if selected else None
        query = self.client_search.text().strip().casefold()
        digits = "".join(char for char in query if char.isdigit())
        phone_query = bool(digits) and all(char.isdigit() or char in "+()- " for char in query)
        visible = [client for client in self.clients if
                   not query or query in client["name"].casefold() or query in client["phone"] or
                   (phone_query and digits in "".join(c for c in client["phone"] if c.isdigit()))]
        table = self.client_table
        table.blockSignals(True)
        table.clearSelection()
        table.setRowCount(len(visible))
        for row, client in enumerate(visible):
            table.setRowHeight(row, 43)
            values = [f"КЛ-{client['id']:04d}", client["name"], client["phone"], str(self.car_count(client["id"]))]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, client["id"])
                    item.setForeground(QColor("#3767B2"))
                table.setItem(row, column, item)
            if client["id"] == selected_id:
                table.selectRow(row)
        table.blockSignals(False)
        self.client_count.setText(str(len(self.clients)))
        self.clients_footer.setText(f"Показано: {len(visible)} из {len(self.clients)}")
        self.empty_clients.setVisible(not visible)
        table.setVisible(bool(visible))
        self.update_client_actions()

    def add_client(self):
        dialog = ClientDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if self.database is not None:
                saved, client = self.save_references(lambda: self.database.add_client(**dialog.values()))
                if not saved:
                    return
            else:
                client = {"id": self.next_client_id, **dialog.values()}
                self.clients.append(client)
                self.next_client_id += 1
            self.client_search.clear()
            self.refresh_clients(client["id"])
            self.client_table.scrollToItem(self.client_table.item(len(self.clients) - 1, 0))

    def edit_client(self):
        client = self.selected_client()
        if client is None:
            return
        dialog = ClientDialog(self, client)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if self.database is not None:
                saved, _ = self.save_references(lambda: self.database.update_client(client["id"], **dialog.values()))
                if not saved:
                    return
            else:
                client.update(dialog.values())
            self.refresh_clients(client["id"])
            self.refresh_cars()
            self.appointments_page.refresh()

    def delete_client(self):
        client = self.selected_client()
        if client is None:
            return
        if any(order["client_id"] == client["id"] for order in self.orders_page.orders):
            notice = QMessageBox(self)
            notice.setWindowTitle("Невозможно удалить клиента")
            notice.setIcon(QMessageBox.Icon.Information)
            notice.setText("Клиент указан в существующем заказ-наряде. "
                           "Удаление заблокировано для сохранения связей оформленного документа.")
            notice.addButton("Понятно", QMessageBox.ButtonRole.AcceptRole)
            notice.exec()
            return
        if self.car_count(client["id"]):
            notice = QMessageBox(self)
            notice.setWindowTitle("Невозможно удалить клиента")
            notice.setIcon(QMessageBox.Icon.Information)
            notice.setText("У клиента есть зарегистрированные автомобили.\n"
                           "Сначала удалите их или укажите другого владельца.")
            notice.addButton("Понятно", QMessageBox.ButtonRole.AcceptRole)
            notice.exec()
            return
        question = QMessageBox(self)
        question.setWindowTitle("Удалить клиента")
        question.setIcon(QMessageBox.Icon.Question)
        question.setTextFormat(Qt.TextFormat.PlainText)
        question.setText(f"Удалить клиента «{client['name']}»?" if self.database is not None else
                         f"Удалить клиента «{client['name']}» из демонстрационного списка?")
        confirm = question.addButton("Удалить", QMessageBox.ButtonRole.DestructiveRole)
        cancel = question.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)
        question.setDefaultButton(cancel)
        question.setEscapeButton(cancel)
        question.exec()
        if question.clickedButton() == confirm:
            if self.database is not None:
                saved, _ = self.save_references(lambda: self.database.delete_client(client["id"]))
                if not saved:
                    return
                self.refresh_cars()
            else:
                self.clients.remove(client)
            self.refresh_clients()

    def save_references(self, operation):
        return save_reference_change(self, self.database, operation, [
            (self.clients, self.database.list_clients),
            (self.cars, self.database.list_cars),
        ])

    def car_count(self, client_id):
        return sum(car["owner_id"] == client_id for car in self.cars)

    def build_cars(self):
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 28, 32, 20)
        layout.setSpacing(0)
        heading = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(6)
        title = QLabel("Автомобили")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Автомобили клиентов автосервиса")
        subtitle.setObjectName("muted")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        heading.addLayout(titles)
        heading.addStretch()
        self.add_car_button = QPushButton("Добавить автомобиль")
        self.add_car_button.setIcon(icon("plus", "#FFFFFF"))
        self.add_car_button.setObjectName("primary")
        self.add_car_button.setFixedSize(210, 42)
        self.add_car_button.clicked.connect(self.add_car)
        heading.addWidget(self.add_car_button)
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
        caption = QLabel("Все автомобили")
        caption.setObjectName("sectionTitle")
        toolbar.addWidget(caption)
        self.car_total = QLabel()
        self.car_total.setObjectName("count")
        self.car_total.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.car_total.setFixedSize(25, 24)
        toolbar.addWidget(self.car_total)
        toolbar.addStretch()
        self.car_search = QLineEdit()
        self.car_search.setPlaceholderText("Марка, модель, госномер, владелец")
        self.car_search.setAccessibleName("Поиск автомобилей")
        self.car_search.setFixedSize(320, 38)
        self.car_search.setClearButtonEnabled(True)
        self.car_search.addAction(icon("search"), QLineEdit.ActionPosition.LeadingPosition)
        self.car_search.textChanged.connect(lambda: self.refresh_cars())
        toolbar.addWidget(self.car_search)
        card_layout.addLayout(toolbar)
        self.car_table = QTableWidget(0, 6)
        table = self.car_table
        configure_table(table, ["ID автомобиля", "Марка и модель", "Госномер", "Год выпуска", "Владелец", "Пробег"], minimum=90)
        header = table.horizontalHeader()
        header.setMinimumSectionSize(90)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        for column, width in [(0, 110), (2, 124), (3, 106), (5, 102)]:
            table.setColumnWidth(column, width)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        table.itemSelectionChanged.connect(self.update_car_actions)
        table.cellDoubleClicked.connect(lambda row, column: self.edit_car())
        card_layout.addWidget(table, 1)
        self.empty_cars = QLabel("Автомобили не найдены. Измените запрос или добавьте автомобиль.")
        self.empty_cars.setObjectName("muted")
        self.empty_cars.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_cars.setMinimumHeight(90)
        card_layout.addWidget(self.empty_cars)
        actions = QHBoxLayout()
        actions.setContentsMargins(20, 12, 20, 12)
        actions.setSpacing(8)
        self.car_selection_hint = QLabel()
        self.car_selection_hint.setObjectName("muted")
        actions.addWidget(self.car_selection_hint)
        actions.addStretch()
        self.edit_car_button = QPushButton("Редактировать")
        self.edit_car_button.setObjectName("secondary")
        self.edit_car_button.setFixedSize(142, 38)
        self.edit_car_button.clicked.connect(self.edit_car)
        self.delete_car_button = QPushButton("Удалить")
        self.delete_car_button.setObjectName("danger")
        self.delete_car_button.setFixedSize(100, 38)
        self.delete_car_button.clicked.connect(self.delete_car)
        actions.addWidget(self.edit_car_button)
        actions.addWidget(self.delete_car_button)
        card_layout.addLayout(actions)
        layout.addWidget(card, 1)
        layout.addSpacing(14)
        self.cars_footer = QLabel()
        self.cars_footer.setObjectName("muted")
        layout.addWidget(self.cars_footer)
        self.refresh_cars()
        return content

    def selected_car(self):
        rows = self.car_table.selectionModel().selectedRows()
        if not rows:
            return None
        car_id = self.car_table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        return next((car for car in self.cars if car["id"] == car_id), None)

    def update_car_actions(self):
        car = self.selected_car()
        self.edit_car_button.setEnabled(car is not None)
        self.delete_car_button.setEnabled(car is not None)
        self.car_selection_hint.setText(f"Выбран автомобиль · АВ-{car['id']:04d}" if car else "Выберите автомобиль в таблице")

    def refresh_cars(self, selected_id=None):
        if selected_id is None:
            selected = self.selected_car()
            selected_id = selected["id"] if selected else None
        owners = {client["id"]: client["name"] for client in self.clients}
        query = self.car_search.text().strip().casefold()
        plate_query = normalize_plate(query)
        visible = [car for car in self.cars if not query
                   or query in f"{car['brand']} {car['model']} {car['plate']} {owners[car['owner_id']]}".casefold()
                   or (plate_query and plate_query in normalize_plate(car["plate"]))]
        table = self.car_table
        table.blockSignals(True)
        table.clearSelection()
        table.setRowCount(len(visible))
        for row, car in enumerate(visible):
            table.setRowHeight(row, 43)
            values = [f"АВ-{car['id']:04d}", f"{car['brand']} {car['model']}", car["plate"],
                      str(car["year"]) if car["year"] is not None else "—", owners[car["owner_id"]],
                      f"{car['mileage']:,} км".replace(",", " ") if car["mileage"] is not None else "—"]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, car["id"])
                    item.setForeground(QColor("#3767B2"))
                table.setItem(row, column, item)
            if car["id"] == selected_id:
                table.selectRow(row)
        table.blockSignals(False)
        self.car_total.setText(str(len(self.cars)))
        self.cars_footer.setText(f"Найдено: {len(visible)} из {len(self.cars)}")
        self.empty_cars.setVisible(not visible)
        table.setVisible(bool(visible))
        self.update_car_actions()

    def add_car(self):
        dialog = CarDialog(self.clients, self.cars, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if self.database is not None:
                saved, car = self.save_references(lambda: self.database.add_car(**dialog.values()))
                if not saved:
                    return
            else:
                car = {"id": self.next_car_id, **dialog.values()}
                self.cars.append(car)
                self.next_car_id += 1
            self.car_search.clear()
            self.refresh_cars(car["id"])
            self.refresh_clients()
            self.car_table.scrollToItem(self.car_table.item(len(self.cars) - 1, 0))

    def edit_car(self):
        car = self.selected_car()
        if car is None:
            return
        dialog = CarDialog(self.clients, self.cars, self, car)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if self.database is not None:
                saved, _ = self.save_references(lambda: self.database.update_car(car["id"], **dialog.values()))
                if not saved:
                    return
            else:
                car.update(dialog.values())
            self.refresh_cars(car["id"])
            self.refresh_clients()
            self.appointments_page.refresh()

    def delete_car(self):
        car = self.selected_car()
        if car is None:
            return
        related = [a for a in self.appointments_page.appointments if a["car_id"] == car["id"]]
        if related:
            notice = QMessageBox(self)
            notice.setWindowTitle("Невозможно удалить автомобиль")
            notice.setIcon(QMessageBox.Icon.Information)
            notice.setText("У автомобиля есть активные записи на обслуживание. Удаление заблокировано."
                           if any(a["status"] == PLANNED for a in related) else
                           "У автомобиля есть отменённые записи. Удаление заблокировано, чтобы сохранить их для просмотра.")
            notice.addButton("Понятно", QMessageBox.ButtonRole.AcceptRole)
            notice.exec()
            return
        if any(order["car_id"] == car["id"] for order in self.orders_page.orders):
            notice = QMessageBox(self)
            notice.setWindowTitle("Невозможно удалить автомобиль")
            notice.setIcon(QMessageBox.Icon.Information)
            notice.setText("Автомобиль указан в существующем заказ-наряде. "
                           "Удаление заблокировано для сохранения связей оформленного документа.")
            notice.addButton("Понятно", QMessageBox.ButtonRole.AcceptRole)
            notice.exec()
            return
        question = QMessageBox(self)
        question.setWindowTitle("Удалить автомобиль")
        question.setIcon(QMessageBox.Icon.Question)
        question.setTextFormat(Qt.TextFormat.PlainText)
        question.setText(f"Удалить автомобиль «{car['brand']} {car['model']} · {car['plate']}»?")
        confirm = question.addButton("Удалить", QMessageBox.ButtonRole.DestructiveRole)
        cancel = question.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)
        question.setDefaultButton(cancel)
        question.setEscapeButton(cancel)
        question.exec()
        if question.clickedButton() == confirm:
            if self.database is not None:
                saved, _ = self.save_references(lambda: self.database.delete_car(car["id"]))
                if not saved:
                    return
                self.appointments_page.refresh()
            else:
                self.cars.remove(car)
            self.refresh_cars()
            self.refresh_clients()
