"""АвтоСервис: запуск SQLite, демонстрации и генерации снимков."""

import argparse
from contextlib import nullcontext
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QMessageBox

from autoservice.database import Database
from autoservice.ui import apply_light_theme
from autoservice.services import ServiceDialog
from autoservice.appointments import AppointmentDialog
from autoservice.orders import OrderDialog, OrderCard
from autoservice.app import MainWindow
from autoservice.dialogs import ClientDialog, CarDialog
from autoservice.styles import STYLE


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
