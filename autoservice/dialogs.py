"""Формы добавления и редактирования клиентов и автомобилей."""

from datetime import date

from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QVBoxLayout,
)

from .data import normalize_plate
from .ui import OwnerComboBox


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
