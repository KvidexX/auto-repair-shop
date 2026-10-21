"""Независимые правила документов, нормализация и время приложения (UTC+10)."""

from datetime import datetime, timedelta, timezone


LOCAL_TIMEZONE = timezone(timedelta(hours=10), "Asia/Vladivostok")


def local_now():
    """Местное время рабочего места; наивный datetime для полей расписания."""
    return datetime.now(LOCAL_TIMEZONE).replace(tzinfo=None)


CATEGORIES = ("Диагностика", "Техническое обслуживание", "Ремонт")


ORDER_STATUSES = ("Оформлен", "В работе", "Готов к выдаче", "Завершён")


def create_order(order_id, created_on, client, car, services, reason):
    """Создаёт независимый снимок документа, не изменяя справочники."""
    if car["owner_id"] != client["id"]:
        raise ValueError("Автомобиль должен принадлежать выбранному клиенту.")
    if not reason.strip():
        raise ValueError("Укажите причину обращения.")
    if not services:
        raise ValueError("Выберите хотя бы одну услугу.")
    if len({s["id"] for s in services}) != len(services):
        raise ValueError("Услуга может быть добавлена в заказ только один раз.")
    if any(type(s["price"]) is not int or s["price"] < 0 for s in services):
        raise ValueError("Стоимость должна быть целым неотрицательным числом рублей.")
    items = [{"service_id": s["id"], "name": s["name"], "price": s["price"]} for s in services]
    return {"id": order_id, "date": created_on, "client_id": client["id"], "client_name": client["name"],
            "car_id": car["id"], "car_snapshot": {key: car[key] for key in ("brand", "model", "plate")},
            "reason": reason.strip(), "items": items, "total": sum(item["price"] for item in items),
            "status": ORDER_STATUSES[0], "completed_at": None}


def edit_order(order, client, car, services, reason, *, reprice_service_ids=()):
    """Новый снимок активного документа; оставшиеся работы сохраняют свои цены."""
    if order["status"] == ORDER_STATUSES[-1]:
        raise ValueError("Завершённый заказ-наряд нельзя редактировать.")
    retained = {item["service_id"]: item for item in order["items"]}
    services = [({"id": s["id"], "name": retained[s["id"]]["name"], "price": retained[s["id"]]["price"]}
                 if s["id"] in retained and s["id"] not in reprice_service_ids else s) for s in services]
    result = create_order(order["id"], order["date"], client, car, services, reason)
    result.update(status=order["status"], completed_at=order["completed_at"])
    if client["id"] == order["client_id"]:
        result["client_name"] = order["client_name"]
    if car["id"] == order["car_id"]:
        result["car_snapshot"] = dict(order["car_snapshot"])
    return result


def advance_order(order):
    """Последовательный переход на следующий этап выполнения."""
    index = ORDER_STATUSES.index(order["status"])
    if index == len(ORDER_STATUSES) - 1:
        return False
    if index == len(ORDER_STATUSES) - 2 and order["completed_at"] is None:
        order["completed_at"] = local_now().replace(tzinfo=LOCAL_TIMEZONE)
    order["status"] = ORDER_STATUSES[index + 1]
    return True


def normalize_service_name(value):
    return " ".join(value.split()).casefold()


def normalize_plate(value):
    """Одинаковый ключ для регистра, пробелов и похожих латинских букв."""
    value = value.upper().translate(str.maketrans("ABCEHKMOPTXY", "АВСЕНКМОРТХУ"))
    return "".join(char for char in value if not char.isspace() and char not in "-·")
