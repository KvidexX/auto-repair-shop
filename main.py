"""Графический прототип «АвтоСервис». SQLite-хранилище и демонстрационные скриншоты."""

import argparse
from contextlib import nullcontext
import sys
from datetime import date
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QIntValidator
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMainWindow, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QDialog, QTextEdit,
    QStackedWidget, QMessageBox, QGridLayout,
)


from autoservice.database import Database
from autoservice.data import CLIENTS, CARS, normalize_plate
from autoservice.ui import icon, RowSelectionDelegate, OwnerComboBox, apply_light_theme
from autoservice.services import ServicesPage, ServiceDialog
from autoservice.appointments import AppointmentsPage, AppointmentDialog, PLANNED
from autoservice.orders import OrdersPage, OrderDialog, OrderCard
from autoservice.history import HistoryPage
from autoservice.persistence import save_reference_change


class ClientDialog(QDialog):
    """Общая форма добавления и редактирования; исходные данные не изменяет."""

    def __init__(self, parent=None, client=None):
        super().__init__(parent)
        self.setWindowTitle("Редактировать клиента" if client else "Добавить клиента")
        self.setObjectName("clientDialog")
        self.setModal(True)
        self.setFixedSize(480, 480)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)
        title = QLabel(self.windowTitle())
        title.setObjectName("dialogTitle")
        layout.addWidget(title)
        hint = QLabel("Контактные данные клиента автосервиса")
        hint.setObjectName("muted")
        layout.addWidget(hint)
        layout.addSpacing(8)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Фамилия Имя Отчество")
        self.name_input.setMaxLength(120)
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("+7 (900) 000-00-00")
        self.phone_input.setMaxLength(40)
        self.note_input = QTextEdit()
        self.note_input.setAcceptRichText(False)
        self.note_input.setPlaceholderText("Дополнительная информация")
        self.note_input.setFixedHeight(76)
        for caption, field in [("ФИО *", self.name_input), ("Телефон *", self.phone_input),
                               ("Примечание", self.note_input)]:
            label = QLabel(caption)
            label.setBuddy(field)
            layout.addWidget(label)
            layout.addWidget(field)
        self.error = QLabel("* Обязательные поля")
        self.error.setObjectName("formHint")
        layout.addWidget(self.error)
        layout.addStretch()
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.cancel_button = QPushButton("Отмена")
        self.cancel_button.setObjectName("secondary")
        self.save_button = QPushButton("Сохранить")
        self.save_button.setObjectName("primary")
        for button in (self.cancel_button, self.save_button):
            button.setFixedSize(120, 40)
            buttons.addWidget(button)
        self.save_button.setDefault(True)
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.validate_and_accept)
        layout.addLayout(buttons)
        if client:
            self.name_input.setText(client["name"])
            self.phone_input.setText(client["phone"])
            self.note_input.setPlainText(client["note"])
        self.name_input.setFocus()

    def validate_and_accept(self):
        for field, message in [(self.name_input, "Введите ФИО клиента."),
                               (self.phone_input, "Введите телефон клиента.")]:
            if not field.text().strip():
                self.error.setText(message)
                self.error.setStyleSheet("color: #B34B4B;")
                field.setFocus()
                return
        self.accept()

    def values(self):
        return {"name": self.name_input.text().strip(),
                "phone": self.phone_input.text().strip(),
                "note": self.note_input.toPlainText().strip()}


class CarDialog(QDialog):
    """Форма автомобиля. В списке владельцев сохраняются ID клиентов."""

    def __init__(self, clients, cars, parent=None, car=None):
        super().__init__(parent)
        self.clients = clients
        self.cars = cars
        self.car_id = car["id"] if car else None
        self.setWindowTitle("Редактировать автомобиль" if car else "Добавить автомобиль")
        self.setObjectName("carDialog")
        self.setModal(True)
        self.setFixedSize(620, 542)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(12)
        title = QLabel(self.windowTitle())
        title.setObjectName("dialogTitle")
        layout.addWidget(title)
        hint = QLabel("Данные автомобиля и его текущего владельца")
        hint.setObjectName("muted")
        layout.addWidget(hint)
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        self.owner_input = OwnerComboBox()
        self.owner_input.addItem("Выберите клиента", None)
        for client in clients:
            self.owner_input.addItem(f"{client['name']} · КЛ-{client['id']:04d}", client["id"])
        self.brand_input = QLineEdit()
        self.brand_input.setPlaceholderText("Например, Toyota")
        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText("Например, Corolla")
        self.plate_input = QLineEdit()
        self.plate_input.setPlaceholderText("А123ВС125")
        self.year_input = QLineEdit()
        self.year_input.setPlaceholderText("Не указан")
        self.year_input.setValidator(QIntValidator(0, 9999, self))
        self.vin_input = QLineEdit()
        self.vin_input.setPlaceholderText("17 символов, если известен")
        self.mileage_input = QLineEdit()
        self.mileage_input.setPlaceholderText("Не указан")
        self.mileage_input.setValidator(QIntValidator(0, 2_147_483_647, self))
        for field in (self.brand_input, self.model_input):
            field.setMaxLength(80)
        self.plate_input.setMaxLength(30)
        self.vin_input.setMaxLength(40)
        fields = [("Владелец *", self.owner_input, 0, 0, 2),
                  ("Марка *", self.brand_input, 2, 0, 1),
                  ("Модель *", self.model_input, 2, 1, 1),
                  ("Госномер *", self.plate_input, 4, 0, 1),
                  ("Год выпуска", self.year_input, 4, 1, 1),
                  ("VIN", self.vin_input, 6, 0, 1),
                  ("Пробег, км", self.mileage_input, 6, 1, 1)]
        for caption, field, row, column, span in fields:
            label = QLabel(caption)
            label.setBuddy(field)
            field.setFixedHeight(38)
            grid.addWidget(label, row, column, 1, span)
            grid.addWidget(field, row + 1, column, 1, span)
        layout.addLayout(grid)
        self.error = QLabel("* Обязательные поля")
        self.error.setObjectName("formHint")
        self.error.setWordWrap(True)
        self.error.setMinimumHeight(34)
        layout.addWidget(self.error)
        layout.addStretch()
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.cancel_button = QPushButton("Отмена")
        self.cancel_button.setObjectName("secondary")
        self.save_button = QPushButton("Сохранить")
        self.save_button.setObjectName("primary")
        for button in (self.cancel_button, self.save_button):
            button.setFixedSize(120, 40)
            buttons.addWidget(button)
        self.save_button.setDefault(True)
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.validate_and_accept)
        layout.addLayout(buttons)
        if car:
            self.owner_input.setCurrentIndex(self.owner_input.findData(car["owner_id"]))
            for key, field in [("brand", self.brand_input), ("model", self.model_input),
                               ("plate", self.plate_input), ("year", self.year_input),
                               ("vin", self.vin_input), ("mileage", self.mileage_input)]:
                field.setText(str(car[key]) if car[key] is not None else "")
        self.owner_input.setFocus()

    def show_error(self, field, message):
        self.error.setText(message)
        self.error.setStyleSheet("color: #B34B4B;")
        field.setFocus()

    def validate_and_accept(self):
        if not any(c["id"] == self.owner_input.currentData() for c in self.clients):
            self.show_error(self.owner_input, "Выберите существующего клиента-владельца.")
            return
        for field, caption in [(self.brand_input, "марку"), (self.model_input, "модель"),
                               (self.plate_input, "госномер")]:
            if not field.text().strip():
                self.show_error(field, f"Укажите {caption} автомобиля.")
                return
        plate = normalize_plate(self.plate_input.text())
        if not plate:
            self.show_error(self.plate_input, "Укажите госномер автомобиля.")
            return
        if any(c["id"] != self.car_id and normalize_plate(c["plate"]) == plate for c in self.cars):
            self.show_error(self.plate_input, "Автомобиль с таким госномером уже зарегистрирован.")
            return
        for field, minimum, maximum, message in [
            (self.year_input, 1900, date.today().year + 1,
             f"Год выпуска: целое число от 1900 до {date.today().year + 1}."),
            (self.mileage_input, 0, 2_147_483_647, "Пробег: целое неотрицательное число километров."),
        ]:
            value = field.text().strip()
            if value and (not value.isascii() or not value.isdigit() or not minimum <= int(value) <= maximum):
                self.show_error(field, message)
                return
        if self.vin_input.text().strip() and len(self.vin_input.text().strip()) != 17:
            self.show_error(self.vin_input, "VIN должен содержать ровно 17 символов.")
            return
        self.accept()

    def values(self):
        return {"owner_id": self.owner_input.currentData(),
                "brand": self.brand_input.text().strip(), "model": self.model_input.text().strip(),
                "plate": normalize_plate(self.plate_input.text()), "vin": self.vin_input.text().strip().upper(),
                "year": int(self.year_input.text()) if self.year_input.text().strip() else None,
                "mileage": int(self.mileage_input.text()) if self.mileage_input.text().strip() else None}


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
            button.setEnabled(True)
            self.nav_buttons[name] = button
            if button.isEnabled():
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
        table.setItemDelegate(RowSelectionDelegate(table))
        table.setHorizontalHeaderLabels(["ID", "ФИО", "Телефон", "Количество автомобилей"])
        table.verticalHeader().hide()
        table.setShowGrid(False)
        table.setWordWrap(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setFrameShape(QFrame.Shape.NoFrame)
        table.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        header = table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setFixedHeight(42)
        header.setHighlightSections(False)
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
        table.setItemDelegate(RowSelectionDelegate(table))
        table.setHorizontalHeaderLabels(["ID автомобиля", "Марка и модель", "Госномер", "Год выпуска", "Владелец", "Пробег"])
        table.verticalHeader().hide()
        table.setShowGrid(False)
        table.setWordWrap(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setFrameShape(QFrame.Shape.NoFrame)
        table.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        header = table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setFixedHeight(42)
        header.setHighlightSections(False)
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


STYLE = """
QWidget { font-family: 'Segoe UI'; font-size: 13px; color: #344054; }
QMainWindow, QWidget#central { background: #F5F7FA; }
QFrame#sidebar { background: #FFFFFF; border-right: 1px solid #E5E9F0; }
QLabel#brand { font-size: 22px; font-weight: 700; color: #24334B; }
QLabel#subtitle { font-size: 10px; color: #8A94A5; letter-spacing: 1px; }
QPushButton#nav, QPushButton#activeNav { text-align: left; padding-left: 12px;
    border: none; border-radius: 7px; }
QPushButton#nav:disabled { color: #7C8798; background: transparent; }
QPushButton#nav { color: #7C8798; background: transparent; }
QPushButton#nav:hover { background: #F5F7FA; }
QPushButton#activeNav { background: #EBF1FD; color: #3567C4; font-weight: 600; }
QLabel#pageTitle { font-size: 28px; font-weight: 650; color: #24334B; }
QLabel#muted { color: #8690A0; font-size: 12px; }
QPushButton#primary { background: #386BD6; border: 1px solid #386BD6;
    color: white; border-radius: 7px; font-weight: 600; }
QPushButton#primary:hover { background: #3060C5; }
QPushButton#primary:disabled { background: #F0F2F4; border-color: #E5E9F0; color: #929CAB; }
QPushButton#secondary, QPushButton#danger { background: white; border: 1px solid #DDE3EC;
    border-radius: 6px; padding: 6px 12px; }
QPushButton#secondary:hover { background: #F5F7FA; }
QPushButton#danger { color: #AD5353; border-color: #E9D6D6; }
QPushButton#danger:hover { background: #FDF2F2; }
QPushButton#secondary:disabled, QPushButton#danger:disabled { color: #A4ADBA;
    border-color: #EBEEF3; background: #FAFBFC; }
QDialog#clientDialog, QDialog#carDialog, QDialog#serviceDialog, QDialog#appointmentDialog, QDialog#orderDialog, QDialog#orderCard { background: #FFFFFF; }
QDateEdit { background: white; border: 1px solid #DDE3EC; border-radius: 6px; padding: 6px 9px; }
QDateEdit:focus { border-color: #7396DF; }
QDateEdit:disabled { background: #F8FAFC; color: #929CAB; }
QDateEdit::drop-down { border: none; width: 26px; }
QDateEdit::down-arrow { width: 0; height: 0; }
QCheckBox { spacing: 8px; }
QComboBox { background: white; border: 1px solid #DDE3EC; border-radius: 6px; padding: 6px 9px; }
QComboBox:focus { border-color: #7396DF; }
QComboBox:disabled { background: #F8FAFC; color: #929CAB; }
QComboBox::drop-down { width: 26px; border: none; }
QComboBox::down-arrow { width: 0; height: 0; }
QComboBox QAbstractItemView { background: white; selection-background-color: #EBF1FD;
    selection-color: #294F91; border: 1px solid #DDE3EC; }
QLabel#orderTotal { font-size: 19px; font-weight: 650; color: #24334B; }
QLabel#dialogTitle { font-size: 23px; font-weight: 650; color: #24334B; }
QLabel#formHint { color: #8690A0; font-size: 12px; }
QTextEdit { background: white; border: 1px solid #DDE3EC; border-radius: 6px; padding: 8px; }
QTextEdit:focus { border-color: #7396DF; }
QLineEdit#documentField, QLineEdit#documentField:focus,
QTextEdit#documentReason, QTextEdit#documentReason:focus {
    background: #F8FAFC; color: #344054; border: none; border-radius: 6px; padding: 6px 9px;
}
QFrame#card { background: white; border: 1px solid #E3E8F0; border-radius: 9px; }
QLabel#sectionTitle { font-size: 14px; font-weight: 600; color: #344054; }
QLabel#count { background: #F0F3F7; color: #778397; border-radius: 6px; font-size: 11px; }
QLineEdit { background: #FFFFFF; border: 1px solid #DDE3EC; border-radius: 6px;
    padding: 6px 9px; selection-background-color: #DFE9FF; }
QLineEdit:focus { border-color: #7396DF; }
QTableWidget { background: #FFFFFF; border: none; }
QTableWidget::item { padding-left: 16px; padding-right: 8px; border-bottom: 1px solid #EEF1F5; }
QTableWidget::item:selected { background: #EBF1FD; color: #294F91; }
QHeaderView::section { background: #F8FAFC; color: #818B9C; font-size: 11px;
    font-weight: 600; border: none; border-top: 1px solid #EBEEF3;
    border-bottom: 1px solid #EBEEF3; padding-left: 16px; }
QLabel#plate { color: #909AAA; font-size: 11px; }
QScrollBar:vertical { width: 8px; background: #F8FAFC; }
QScrollBar::handle:vertical { background: #CDD5E1; min-height: 24px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="Интерактивные демонстрационные данные без SQLite")
    parser.add_argument("--screenshot", type=Path,
                        help="Сохранить PNG и завершить работу; имя без пути сохраняется в screenshots/")
    parser.add_argument("--screen", choices=("orders", "clients", "car", "services", "calendar", "history"), default="orders",
                        help="Раздел при запуске")
    parser.add_argument("--dialog", action="store_true", help="Снять форму добавления выбранного раздела (с --screenshot)")
    parser.add_argument("--order-card", type=int, help="Снять карточку заказа по ID (с --screenshot)")
    args = parser.parse_args()
    if args.order_card is not None and (not args.screenshot or args.dialog):
        parser.error("--order-card используется с --screenshot и без --dialog")
    if args.dialog and not args.screenshot:
        parser.error("--dialog используется вместе с --screenshot")
    if args.dialog and args.screen == "history":
        parser.error("В истории нет формы создания; используйте --order-card ID")
    if args.screenshot:
        if args.screenshot.parent == Path("."):
            args.screenshot = Path(__file__).resolve().parent / "screenshots" / args.screenshot.name
        args.screenshot.parent.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv[:1])
    apply_light_theme(app)
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(STYLE)
    try:
        # Снимки используют прежние данные в памяти, не открывая рабочую БД.
        with (nullcontext() if args.screenshot or args.demo else Database()) as database:
            try:
                window = MainWindow(database=database)
                window.centralWidget().setObjectName("central")
                window.show_section("orders" if args.order_card is not None else args.screen)
                window.show()
                dialog = None
                if args.dialog:
                    if args.screen == "calendar":
                        dialog = AppointmentDialog(window.clients, window.cars, window.appointments_page.appointments, window)
                    elif args.screen == "services":
                        dialog = ServiceDialog(window.services_page.services, window)
                    elif args.screen == "car":
                        dialog = CarDialog(window.clients, window.cars, window)
                    elif args.screen == "orders":
                        dialog = OrderDialog(window.clients, window.cars, window.services_page.services, window)
                    else:
                        dialog = ClientDialog(window)
                    dialog.show()
                elif args.order_card is not None:
                    order = next((o for o in window.orders_page.orders if o["id"] == args.order_card), None)
                    if order is None:
                        parser.error("Заказ с указанным ID не найден")
                    dialog = OrderCard(order, window)
                    dialog.show()
                result = {"code": 0}
                if args.screenshot:
                    def capture():
                        target = dialog if dialog else window
                        if not target.grab().save(str(args.screenshot), "PNG"):
                            print(f"Не удалось сохранить скриншот: {args.screenshot}", file=sys.stderr)
                            result["code"] = 1
                        app.quit()
                    QTimer.singleShot(900, capture)
                return app.exec() or result["code"]
            finally:
                app.closeAllWindows()
    except Exception as error:
        notice = QMessageBox(QMessageBox.Icon.Critical, "Ошибка запуска",
                             "Не удалось запустить «АвтоСервис». Проверьте доступ к базе данных "
                             "и сведения об ошибке.")
        notice.setTextFormat(Qt.TextFormat.PlainText)
        notice.setDetailedText(str(error))
        notice.addButton("Закрыть", QMessageBox.ButtonRole.AcceptRole)
        notice.exec()
        return 1


if __name__ == "__main__":
    sys.exit(main())
