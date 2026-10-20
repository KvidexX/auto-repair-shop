"""Каталог услуг и его форма. Только данные текущего сеанса, цены в целых рублях."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIntValidator
from PySide6.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QTextEdit,
    QVBoxLayout, QWidget,
)

from data import CATEGORIES, SERVICES, normalize_service_name
from ui import OwnerComboBox, RowSelectionDelegate, icon


class ServiceDialog(QDialog):
    def __init__(self, services, parent=None, service=None):
        super().__init__(parent)
        self.services = services
        self.service_id = service["id"] if service else None
        self.setWindowTitle("Редактировать услугу" if service else "Добавить услугу")
        self.setObjectName("serviceDialog")
        self.setModal(True)
        self.setFixedSize(580, 550)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)
        title = QLabel(self.windowTitle())
        title.setObjectName("dialogTitle")
        layout.addWidget(title)
        hint = QLabel("Наименование, стоимость и параметры работы")
        hint.setObjectName("muted")
        layout.addWidget(hint)
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Например, диагностика подвески")
        self.name_input.setMaxLength(160)
        self.category_input = OwnerComboBox()
        self.category_input.addItem("Выберите категорию", None)
        for category in CATEGORIES:
            self.category_input.addItem(category, category)
        self.price_input = QLineEdit()
        self.price_input.setPlaceholderText("Целое число рублей")
        self.price_input.setValidator(QIntValidator(0, 2_147_483_647, self))
        self.duration_input = QLineEdit()
        self.duration_input.setPlaceholderText("Не указано")
        self.duration_input.setValidator(QIntValidator(1, 2_147_483_647, self))
        self.description_input = QTextEdit()
        self.description_input.setAcceptRichText(False)
        self.description_input.setPlaceholderText("Дополнительная информация об услуге")
        self.description_input.setFixedHeight(80)
        for caption, field, row, column, span in [
            ("Наименование услуги *", self.name_input, 0, 0, 2),
            ("Категория *", self.category_input, 2, 0, 2),
            ("Стоимость, ₽ *", self.price_input, 4, 0, 1),
            ("Нормативное время, мин", self.duration_input, 4, 1, 1),
            ("Описание", self.description_input, 6, 0, 2),
        ]:
            label = QLabel(caption)
            label.setBuddy(field)
            if field is not self.description_input:
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
        layout.addLayout(buttons)
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.validate_and_accept)
        self.save_button.setDefault(True)
        if service:
            self.name_input.setText(service["name"])
            self.category_input.setCurrentIndex(self.category_input.findData(service["category"]))
            self.price_input.setText(str(service["price"]))
            self.duration_input.setText(str(service["duration"]) if service["duration"] is not None else "")
            self.description_input.setPlainText(service["description"])
        self.name_input.setFocus()

    def fail(self, field, message):
        self.error.setText(message)
        self.error.setStyleSheet("color: #B34B4B;")
        field.setFocus()

    def validate_and_accept(self):
        name = normalize_service_name(self.name_input.text())
        if not name:
            self.fail(self.name_input, "Введите наименование услуги.")
            return
        if any(s["id"] != self.service_id and normalize_service_name(s["name"]) == name for s in self.services):
            self.fail(self.name_input, "Услуга с таким наименованием уже есть в каталоге.")
            return
        if self.category_input.currentData() not in CATEGORIES:
            self.fail(self.category_input, "Выберите категорию услуги.")
            return
        for field, required, minimum, message in [
            (self.price_input, True, 0, "Стоимость: целое число рублей от 0 до 2 147 483 647."),
            (self.duration_input, False, 1, "Нормативное время: целое число минут от 1 до 2 147 483 647."),
        ]:
            value = field.text().strip()
            if not value and not required:
                continue
            if not value or not value.isascii() or not value.isdigit() or len(value) > 10 or not minimum <= int(value) <= 2_147_483_647:
                self.fail(field, message)
                return
        self.accept()

    def values(self):
        return {"name": " ".join(self.name_input.text().split()),
                "category": self.category_input.currentData(), "price": int(self.price_input.text()),
                "duration": int(self.duration_input.text()) if self.duration_input.text().strip() else None,
                "description": self.description_input.toPlainText().strip()}


class ServicesPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.services = [dict(service) for service in SERVICES]
        self.next_id = max((s["id"] for s in self.services), default=0) + 1
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 20)
        layout.setSpacing(0)
        heading = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(6)
        title = QLabel("Каталог услуг")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Услуги и стоимость работ автосервиса")
        subtitle.setObjectName("muted")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        heading.addLayout(titles)
        heading.addStretch()
        self.add_button = QPushButton("Добавить услугу")
        self.add_button.setIcon(icon("plus", "#FFFFFF"))
        self.add_button.setObjectName("primary")
        self.add_button.setFixedSize(187, 42)
        self.add_button.clicked.connect(self.add_service)
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
        caption = QLabel("Все услуги")
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
        self.search.setPlaceholderText("Поиск по названию или категории")
        self.search.setAccessibleName("Поиск услуг")
        self.search.setFixedSize(320, 38)
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icon("search"), QLineEdit.ActionPosition.LeadingPosition)
        self.search.textChanged.connect(lambda: self.refresh())
        toolbar.addWidget(self.search)
        card_layout.addLayout(toolbar)
        self.table = QTableWidget(0, 5)
        self.table.setItemDelegate(RowSelectionDelegate(self.table))
        self.table.setHorizontalHeaderLabels(["ID услуги", "Наименование услуги", "Категория", "Нормативное время", "Стоимость"])
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setFrameShape(QFrame.Shape.NoFrame)
        self.table.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setFixedHeight(42)
        header.setHighlightSections(False)
        header.setMinimumSectionSize(90)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        for column, width in [(0, 100), (2, 223), (3, 162), (4, 115)]:
            self.table.setColumnWidth(column, width)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self.update_actions)
        self.table.cellDoubleClicked.connect(lambda row, column: self.edit_service())
        card_layout.addWidget(self.table, 1)
        self.empty = QLabel("Услуги не найдены. Измените запрос или добавьте услугу.")
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
        self.edit_button = QPushButton("Редактировать")
        self.edit_button.setObjectName("secondary")
        self.edit_button.setFixedSize(142, 38)
        self.edit_button.clicked.connect(self.edit_service)
        self.delete_button = QPushButton("Удалить")
        self.delete_button.setObjectName("danger")
        self.delete_button.setFixedSize(100, 38)
        self.delete_button.clicked.connect(self.delete_service)
        actions.addWidget(self.edit_button)
        actions.addWidget(self.delete_button)
        card_layout.addLayout(actions)
        layout.addWidget(card, 1)
        layout.addSpacing(14)
        self.footer = QLabel()
        self.footer.setObjectName("muted")
        layout.addWidget(self.footer)
        self.refresh()

    def selected_service(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        service_id = self.table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        return next((s for s in self.services if s["id"] == service_id), None)

    def update_actions(self):
        service = self.selected_service()
        self.edit_button.setEnabled(service is not None)
        self.delete_button.setEnabled(service is not None)
        self.selection_hint.setText(f"Выбрана услуга · УС-{service['id']:04d}" if service else "Выберите услугу в таблице")

    def refresh(self, selected_id=None):
        if selected_id is None:
            selected = self.selected_service()
            selected_id = selected["id"] if selected else None
        query = normalize_service_name(self.search.text())
        visible = [s for s in self.services if query in normalize_service_name(f"{s['name']} {s['category']}")]
        self.table.blockSignals(True)
        self.table.clearSelection()
        self.table.setRowCount(len(visible))
        for row, service in enumerate(visible):
            self.table.setRowHeight(row, 43)
            values = [f"УС-{service['id']:04d}", service["name"], service["category"],
                      f"{service['duration']} мин" if service["duration"] is not None else "—",
                      f"{service['price']:,} ₽".replace(",", " ")]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, service["id"])
                    item.setForeground(QColor("#3767B2"))
                self.table.setItem(row, column, item)
            if service["id"] == selected_id:
                self.table.selectRow(row)
        self.table.blockSignals(False)
        self.total.setText(str(len(self.services)))
        self.footer.setText(f"Найдено: {len(visible)} из {len(self.services)}  ·  Изменения хранятся только до закрытия приложения")
        self.empty.setVisible(not visible)
        self.table.setVisible(bool(visible))
        self.update_actions()

    def add_service(self):
        dialog = ServiceDialog(self.services, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            service = {"id": self.next_id, **dialog.values()}
            self.services.append(service)
            self.next_id += 1
            self.search.clear()
            self.refresh(service["id"])
            self.table.scrollToItem(self.table.item(len(self.services) - 1, 0))

    def edit_service(self):
        service = self.selected_service()
        if service is None:
            return
        dialog = ServiceDialog(self.services, self, service)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            service.update(dialog.values())
            self.refresh(service["id"])

    def delete_service(self):
        service = self.selected_service()
        if service is None:
            return
        question = QMessageBox(self)
        question.setWindowTitle("Удалить услугу")
        question.setIcon(QMessageBox.Icon.Question)
        question.setTextFormat(Qt.TextFormat.PlainText)
        question.setText(f"Удалить услугу «{service['name']}» из каталога?")
        confirm = question.addButton("Удалить", QMessageBox.ButtonRole.DestructiveRole)
        cancel = question.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)
        question.setDefaultButton(cancel)
        question.setEscapeButton(cancel)
        question.exec()
        if question.clickedButton() == confirm:
            self.services.remove(service)
            self.refresh()
