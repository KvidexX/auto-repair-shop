"""Сохранение справочника и обновление его снимков для интерфейса."""

import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox


def save_reference_change(parent, database, operation, collections):
    """Меняет списки на месте только после успешного COMMIT всех операций.

    collections — пары (список интерфейса, функция загрузки из БД).
    Ошибка чтения после записи также откатывает транзакцию.
    """
    try:
        with database.transaction():
            result = operation()
            snapshots = [load() for _, load in collections]
    except (sqlite3.Error, ValueError, KeyError) as error:
        if isinstance(error, sqlite3.IntegrityError):
            message = ("Изменение не сохранено: запись связана с другими данными "
                       "или нарушает ограничения уникальности и допустимых значений.")
        elif isinstance(error, KeyError):
            message = "Изменение не сохранено: запись больше не существует в базе данных."
        elif isinstance(error, ValueError):
            message = f"Изменение не сохранено. {error}"
        else:
            message = "Не удалось сохранить изменение в SQLite. Проверьте доступ к базе данных и повторите попытку."
        notice = QMessageBox(QMessageBox.Icon.Warning, "Ошибка сохранения", message, parent=parent)
        notice.setTextFormat(Qt.TextFormat.PlainText)
        notice.setDetailedText(str(error))
        notice.addButton("Понятно", QMessageBox.ButtonRole.AcceptRole)
        notice.exec()
        return False, None
    for (records, _), snapshot in zip(collections, snapshots):
        records[:] = snapshot
    return True, result
