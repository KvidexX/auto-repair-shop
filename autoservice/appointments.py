"""Планирование приёмки: общий получасовой поток и подключаемая SQLite."""

from datetime import datetime, timedelta, time

from PySide6.QtCore import QDate, Qt, QRectF
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMessageBox, QPushButton, QStyledItemDelegate, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget, QStyle,
)

from .data import make_appointments, local_now
from .persistence import save_reference_change
from .ui import DateEdit, OwnerComboBox, RowSelectionDelegate, icon

PLANNED = "Запланирована"
CANCELLED = "Отменена"
SLOTS = tuple(time(9 + step // 2, (step % 2) * 30) for step in range(19))


def qt_date(day):
    return QDate(day.year, day.month, day.day)


class AppointmentStatusDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        painter.save()
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        painter.fillRect(option.rect, QColor("#EBF1FD" if selected else "#FFFFFF"))
        text = index.data()
        background, foreground = ("#EAF1FE", "#3566B8") if text == PLANNED else ("#F0F2F4", "#747D89")
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(option.font)
        badge = QRectF(option.rect.x() + 10, option.rect.center().y() - 13,
                       painter.fontMetrics().horizontalAdvance(text) + 20, 27)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(background))
        painter.drawRoundedRect(badge, 6, 6)
        painter.setPen(QColor(foreground))
        painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, text)
        painter.setPen(QColor("#EEF1F5"))
        painter.drawLine(option.rect.bottomLeft(), option.rect.bottomRight())
        painter.restore()


class AppointmentDialog(QDialog):
    def __init__(self, clients, cars, appointments, parent=None, appointment=None, *, save_appointment=None):
        super().__init__(parent)
        self.clients, self.cars, self.appointments = clients, cars, appointments
        self.appointment = appointment
        self.save_appointment = save_appointment
        self.saved_appointment = None
        self.read_only = appointment is not None and appointment["status"] == CANCELLED
        self.setWindowTitle("Просмотр записи" if self.read_only else "Редактировать запись" if appointment else "Новая запись")
        self.setObjectName("appointmentDialog")
        self.setModal(True)
        self.setFixedSize(620, 610)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)
        title = QLabel(self.windowTitle())
        title.setObjectName("dialogTitle")
        layout.addWidget(title)
        hint = QLabel("Отменённая запись · только просмотр" if self.read_only else "Посещение автосервиса · приём с 09:00 до 18:00")
        hint.setObjectName("muted")
        layout.addWidget(hint)
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(8)
        self.client_input = OwnerComboBox()
        self.client_input.addItem("Выберите клиента", None)
        for client in clients:
            self.client_input.addItem(f"{client['name']} · КЛ-{client['id']:04d}", client["id"])
        self.car_input = OwnerComboBox()
        self.date_input = DateEdit()
        self.date_input.setCalendarPopup(True)
        self.date_input.setDisplayFormat("dd.MM.yyyy")
        self.date_input.setDate(qt_date(local_now().date() + timedelta(days=1)))
        self.time_input = OwnerComboBox()
        self.time_input.addItem("Выберите время", None)
        for slot in SLOTS:
            self.time_input.addItem(slot.strftime("%H:%M"), slot.strftime("%H:%M"))
        self.time_input.setCurrentIndex(1)
        self.reason_input = QLineEdit()
        self.reason_input.setMaxLength(200)
        self.reason_input.setPlaceholderText("Например, диагностика подвески")
        self.note_input = QTextEdit()
        self.note_input.setAcceptRichText(False)
        self.note_input.setFixedHeight(80)
        self.note_input.setPlaceholderText("Дополнительная информация о посещении")
        for caption, field, row, column, span in [
            ("Клиент *", self.client_input, 0, 0, 2),
            ("Автомобиль *", self.car_input, 2, 0, 2),
            ("Дата посещения *", self.date_input, 4, 0, 1),
            ("Время посещения *", self.time_input, 4, 1, 1),
            ("Причина обращения *", self.reason_input, 6, 0, 2),
            ("Примечание", self.note_input, 8, 0, 2),
        ]:
            label = QLabel(caption)
            label.setBuddy(field)
            if field is not self.note_input:
                field.setFixedHeight(38)
            grid.addWidget(label, row, column, 1, span)
            grid.addWidget(field, row + 1, column, 1, span)
        layout.addLayout(grid)
        self.error = QLabel("* Обязательные поля · интервал записи 30 минут")
        self.error.setObjectName("formHint")
        self.error.setWordWrap(True)
        self.error.setMinimumHeight(34)
        layout.addWidget(self.error)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.cancel_button = QPushButton("Закрыть" if self.read_only else "Отмена")
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
        self.client_input.currentIndexChanged.connect(self.update_cars)
        self.update_cars()
        if appointment:
            car = next(c for c in cars if c["id"] == appointment["car_id"])
            self.client_input.setCurrentIndex(self.client_input.findData(car["owner_id"]))
            self.car_input.setCurrentIndex(self.car_input.findData(car["id"]))
            self.date_input.setDate(qt_date(appointment["date"]))
            self.time_input.setCurrentIndex(self.time_input.findData(appointment["time"].strftime("%H:%M")))
            self.reason_input.setText(appointment["reason"])
            self.note_input.setPlainText(appointment["note"])
        if self.read_only:
            for field in (self.client_input, self.car_input, self.date_input, self.time_input):
                field.setEnabled(False)
            self.reason_input.setReadOnly(True)
            self.note_input.setReadOnly(True)
            self.save_button.hide()
        self.client_input.setFocus()

    def update_cars(self):
        client_id = self.client_input.currentData()
        self.car_input.clear()
        available = [c for c in self.cars if c["owner_id"] == client_id]
        caption = "Выберите автомобиль" if available else "У клиента нет автомобилей" if client_id is not None else "Сначала выберите клиента"
        self.car_input.addItem(caption, None)
        for car in available:
            self.car_input.addItem(f"{car['brand']} {car['model']} · {car['plate']} · АВ-{car['id']:04d}", car["id"])
        self.car_input.setEnabled(bool(available) and not self.read_only)

    def fail(self, field, message):
        self.error.setText(message)
        self.error.setStyleSheet("color: #B34B4B;")
        field.setFocus()

    def validate_and_accept(self):
        if self.read_only:
            return
        client_id = self.client_input.currentData()
        if not any(c["id"] == client_id for c in self.clients):
            self.fail(self.client_input, "Выберите существующего клиента.")
            return
        if not any(c["id"] == self.car_input.currentData() and c["owner_id"] == client_id for c in self.cars):
            self.fail(self.car_input, "Выберите автомобиль выбранного клиента.")
            return
        day = self.date_input.date()
        raw_slot = self.time_input.currentData()
        try:
            slot = time.fromisoformat(raw_slot) if isinstance(raw_slot, str) else None
        except ValueError:
            slot = None
        if not day.isValid():
            self.fail(self.date_input, "Укажите дату посещения.")
            return
        if slot not in SLOTS:
            self.fail(self.time_input, "Выберите время с 09:00 до 18:00 с шагом 30 минут.")
            return
        if not self.reason_input.text().strip():
            self.fail(self.reason_input, "Укажите причину обращения.")
            return
        timestamp = datetime.combine(day.toPython(), slot)
        previous = datetime.combine(self.appointment["date"], self.appointment["time"]) if self.appointment else None
        if timestamp < local_now() and timestamp != previous:
            self.fail(self.date_input, "Нельзя назначить посещение на прошедшие дату и время.")
            return
        own_id = self.appointment["id"] if self.appointment else None
        if any(a["id"] != own_id and a["status"] == PLANNED and a["date"] == day.toPython() and a["time"] == slot for a in self.appointments):
            self.fail(self.time_input, "Это время уже занято. Выберите другой интервал.")
            return
        if self.save_appointment is not None:
            self.saved_appointment = self.save_appointment(self.values())
            if self.saved_appointment is None:
                self.fail(self.save_button, "Запись не сохранена. Введённые данные остались в форме — повторите попытку.")
                return
        self.accept()

    def values(self):
        return {"car_id": self.car_input.currentData(), "date": self.date_input.date().toPython(),
                "time": time.fromisoformat(self.time_input.currentData()), "reason": self.reason_input.text().strip(),
                "note": self.note_input.toPlainText().strip()}


class AppointmentsPage(QWidget):
    def __init__(self, clients, cars, parent=None, *, demo=True, database=None):
        super().__init__(parent)
        self.clients, self.cars = clients, cars
        self.database = database
        self.appointments = (database.list_appointments() if database is not None else
                             make_appointments(local_now().date()) if demo else [])
        self.next_id = None if database is not None else max((a["id"] for a in self.appointments), default=0) + 1
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 20)
        layout.setSpacing(0)
        heading = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(6)
        title = QLabel("Запись на обслуживание")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Планирование посещений автосервиса")
        subtitle.setObjectName("muted")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        heading.addLayout(titles)
        heading.addStretch()
        self.add_button = QPushButton("Новая запись")
        self.add_button.setIcon(icon("plus", "#FFFFFF"))
        self.add_button.setObjectName("primary")
        self.add_button.setFixedSize(187, 42)
        self.add_button.clicked.connect(self.add_appointment)
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
        caption = QLabel("Посещения")
        caption.setObjectName("sectionTitle")
        toolbar.addWidget(caption)
        self.total = QLabel()
        self.total.setObjectName("count")
        self.total.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.total.setMinimumWidth(25)
        self.total.setFixedHeight(24)
        toolbar.addWidget(self.total)
        toolbar.addStretch()
        self.date_filter = DateEdit()
        self.date_filter.setCalendarPopup(True)
        self.date_filter.setDisplayFormat("dd.MM.yyyy")
        self.date_filter.setDate(qt_date(local_now().date() + timedelta(days=1)))
        self.date_filter.setFixedSize(142, 38)
        self.date_filter.setEnabled(False)
        self.date_filter.setAccessibleName("Фильтр по дате посещения")
        self.date_filter.dateChanged.connect(lambda: self.refresh())
        toolbar.addWidget(self.date_filter)
        self.all_dates = QCheckBox("Все даты")
        self.all_dates.setChecked(True)
        self.all_dates.toggled.connect(self.toggle_filter)
        toolbar.addWidget(self.all_dates)
        card_layout.addLayout(toolbar)
        self.table = QTableWidget(0, 7)
        self.table.setItemDelegate(RowSelectionDelegate(self.table))
        self.table.setHorizontalHeaderLabels(["ID записи", "Дата", "Время", "Автомобиль", "Клиент", "Причина обращения", "Статус"])
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
        header.setMinimumSectionSize(50)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        for column, width in [(0, 86), (1, 100), (2, 64), (3, 154), (4, 182), (6, 132)]:
            self.table.setColumnWidth(column, width)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.table.setItemDelegateForColumn(6, AppointmentStatusDelegate(self.table))
        self.table.itemSelectionChanged.connect(self.update_actions)
        self.table.cellDoubleClicked.connect(lambda row, column: self.open_appointment())
        card_layout.addWidget(self.table, 1)
        self.empty = QLabel("На выбранную дату записей нет. Выберите другую дату или покажите все.")
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
        self.edit_button.clicked.connect(self.edit_appointment)
        self.cancel_button = QPushButton("Отменить запись")
        self.cancel_button.setObjectName("danger")
        self.cancel_button.setFixedSize(148, 38)
        self.cancel_button.clicked.connect(self.cancel_appointment)
        actions.addWidget(self.edit_button)
        actions.addWidget(self.cancel_button)
        card_layout.addLayout(actions)
        layout.addWidget(card, 1)
        layout.addSpacing(14)
        self.footer = QLabel()
        self.footer.setObjectName("muted")
        layout.addWidget(self.footer)
        self.refresh()

    def toggle_filter(self, checked):
        self.date_filter.setEnabled(not checked)
        self.refresh()

    def selected_appointment(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        appointment_id = self.table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        return next((a for a in self.appointments if a["id"] == appointment_id), None)

    def update_actions(self):
        appointment = self.selected_appointment()
        active = appointment is not None and appointment["status"] == PLANNED
        self.edit_button.setEnabled(active)
        self.cancel_button.setEnabled(active)
        self.selection_hint.setText(f"Выбрана запись · ЗП-{appointment['id']:04d}" if appointment else "Выберите запись в таблице")
        if appointment and appointment["status"] == CANCELLED:
            self.selection_hint.setText("Отменена · двойной щелчок для просмотра")

    def refresh(self, selected_id=None):
        if selected_id is None:
            selected = self.selected_appointment()
            selected_id = selected["id"] if selected else None
        visible = sorted((a for a in self.appointments if self.all_dates.isChecked() or
                          a["date"] == self.date_filter.date().toPython()),
                         key=lambda a: (a["date"], a["time"], a["id"]))
        cars = {c["id"]: c for c in self.cars}
        clients = {c["id"]: c for c in self.clients}
        self.table.blockSignals(True)
        self.table.clearSelection()
        self.table.setRowCount(len(visible))
        for row, appointment in enumerate(visible):
            car = cars[appointment["car_id"]]
            client = clients[car["owner_id"]]
            self.table.setRowHeight(row, 51)
            name_parts = client["name"].split()
            name = " ".join(name_parts[:2]) + ("\n" + " ".join(name_parts[2:]) if len(name_parts) > 2 else "")
            values = [f"ЗП-{appointment['id']:04d}", appointment["date"].strftime("%d.%m.%Y"),
                      appointment["time"].strftime("%H:%M"), f"{car['brand']} {car['model']}\n{car['plate']}",
                      name, appointment["reason"], appointment["status"]]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value.replace("\n", " "))
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, appointment["id"])
                    item.setForeground(QColor("#3767B2"))
                self.table.setItem(row, column, item)
            if appointment["id"] == selected_id:
                self.table.selectRow(row)
        self.table.blockSignals(False)
        self.total.setText(str(len(self.appointments)))
        self.footer.setText(f"Найдено: {len(visible)} из {len(self.appointments)}")
        self.empty.setVisible(not visible)
        self.table.setVisible(bool(visible))
        self.update_actions()

    def add_appointment(self):
        dialog = AppointmentDialog(self.clients, self.cars, self.appointments, self)
        if self.database is not None:
            dialog.save_appointment = lambda values: self.save_form(values, dialog)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if self.database is not None:
                appointment = dialog.saved_appointment
            else:
                appointment = {"id": self.next_id, "status": PLANNED, **dialog.values()}
                self.appointments.append(appointment)
                self.next_id += 1
            # Новая запись остаётся видимой даже при активном фильтре другой даты.
            self.date_filter.setDate(qt_date(appointment["date"]))
            self.refresh(appointment["id"])
            self.scroll_to_selection()

    def edit_appointment(self):
        appointment = self.selected_appointment()
        if appointment is None or appointment["status"] == CANCELLED:
            return
        self.open_appointment()

    def open_appointment(self):
        appointment = self.selected_appointment()
        if appointment is None:
            return
        if self.database is not None:
            appointment_id = appointment["id"]
            appointment = self.save_record(lambda: self.database.get_appointment(appointment_id), self)
            if appointment is None:
                return
            self.refresh(appointment_id)
        dialog = AppointmentDialog(self.clients, self.cars, self.appointments, self, appointment)
        if self.database is not None and appointment["status"] == PLANNED:
            dialog.save_appointment = lambda values: self.save_form(values, dialog, appointment["id"])
        if dialog.exec() == QDialog.DialogCode.Accepted and appointment["status"] == PLANNED:
            if self.database is not None:
                appointment = dialog.saved_appointment
            else:
                appointment.update(dialog.values())
            self.date_filter.setDate(qt_date(appointment["date"]))
            self.refresh(appointment["id"])
            self.scroll_to_selection()

    def save_record(self, operation, parent):
        saved, appointment = save_reference_change(parent, self.database, operation, [
            (self.appointments, self.database.list_appointments),
        ], unique_message="Это время уже занято. Запись не сохранена — выберите другой интервал.")
        return next(a for a in self.appointments if a["id"] == appointment["id"]) if saved else None

    def save_form(self, values, dialog, appointment_id=None):
        def operation():
            # Повторяем проверку владельца по актуальным данным внутри транзакции.
            car = self.database.get_car(values["car_id"])
            if car["owner_id"] != dialog.client_input.currentData():
                raise ValueError("Владелец автомобиля изменился. Проверьте выбранного клиента и автомобиль.")
            fields = {"car_id": values["car_id"], "day": values["date"], "slot": values["time"],
                      "reason": values["reason"], "note": values["note"]}
            if appointment_id is None:
                return self.database.add_appointment(**fields)
            return self.database.update_appointment(appointment_id, **fields)
        return self.save_record(operation, dialog)

    def scroll_to_selection(self):
        rows = self.table.selectionModel().selectedRows()
        if rows:
            self.table.scrollToItem(self.table.item(rows[0].row(), 0))

    def cancel_appointment(self):
        appointment = self.selected_appointment()
        if appointment is None or appointment["status"] == CANCELLED:
            return
        question = QMessageBox(self)
        question.setWindowTitle("Отменить запись")
        question.setIcon(QMessageBox.Icon.Question)
        question.setText(f"Отменить посещение {appointment['date']:%d.%m.%Y} в {appointment['time']:%H:%M}?\n"
                         "Запись останется в списке для просмотра.")
        confirm = question.addButton("Отменить запись", QMessageBox.ButtonRole.DestructiveRole)
        cancel = question.addButton("Назад", QMessageBox.ButtonRole.RejectRole)
        question.setDefaultButton(cancel)
        question.setEscapeButton(cancel)
        question.exec()
        if question.clickedButton() == confirm:
            if self.database is not None:
                appointment = self.save_record(lambda: self.database.cancel_appointment(appointment["id"]), self)
                if appointment is None:
                    return
            else:
                appointment["status"] = CANCELLED
            self.refresh(appointment["id"])

