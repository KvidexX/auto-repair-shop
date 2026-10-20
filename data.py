"""Вымышленные исходные данные. Каждый экземпляр окна получает свою копию."""

from datetime import datetime, timedelta, time, timezone

LOCAL_TIMEZONE = timezone(timedelta(hours=10), "Asia/Vladivostok")


def local_now():
    """Местное время рабочего места; наивный datetime для полей расписания."""
    return datetime.now(LOCAL_TIMEZONE).replace(tzinfo=None)

CLIENTS = [
    {"id": 1, "name": "Смирнов Алексей Игоревич", "phone": "+7 (900) 000-00-01", "note": ""},
    {"id": 2, "name": "Соколова Мария Андреевна", "phone": "+7 (900) 000-00-02", "note": ""},
    {"id": 3, "name": "Волков Дмитрий Олегович", "phone": "+7 (900) 000-00-03", "note": ""},
    {"id": 4, "name": "Морозова Елена Викторовна", "phone": "+7 (900) 000-00-04", "note": ""},
    {"id": 5, "name": "Лебедев Сергей Павлович", "phone": "+7 (900) 000-00-05", "note": ""},
    {"id": 6, "name": "Кузнецова Анна Сергеевна", "phone": "+7 (900) 000-00-06", "note": ""},
    {"id": 7, "name": "Новиков Павел Романович", "phone": "+7 (900) 000-00-07", "note": ""},
]

CARS = [
    {"id": 1, "owner_id": 1, "brand": "Kia", "model": "Rio", "plate": "А123ВС125", "year": 2018, "vin": "", "mileage": 86400},
    {"id": 2, "owner_id": 2, "brand": "Toyota", "model": "Corolla", "plate": "М456ОР125", "year": 2017, "vin": "", "mileage": 112000},
    {"id": 3, "owner_id": 3, "brand": "Hyundai", "model": "Solaris", "plate": "К789НА125", "year": 2019, "vin": "", "mileage": 73500},
    {"id": 4, "owner_id": 4, "brand": "Škoda", "model": "Octavia", "plate": "Т234ЕК125", "year": 2020, "vin": "", "mileage": 62000},
    {"id": 5, "owner_id": 5, "brand": "Volkswagen", "model": "Polo", "plate": "В567УС125", "year": 2016, "vin": "", "mileage": 138000},
    {"id": 6, "owner_id": 6, "brand": "Renault", "model": "Duster", "plate": "Н890АМ125", "year": 2021, "vin": "", "mileage": 48700},
    {"id": 7, "owner_id": 7, "brand": "Lada", "model": "Vesta", "plate": "Р345ТО125", "year": 2022, "vin": "", "mileage": 35100},
    {"id": 8, "owner_id": 2, "brand": "Nissan", "model": "Note", "plate": "Е612КМ125", "year": 2015, "vin": "", "mileage": 124800},
    {"id": 9, "owner_id": 5, "brand": "Mazda", "model": "CX-5", "plate": "С908РХ125", "year": 2023, "vin": "", "mileage": 28600},
]


CATEGORIES = ("Диагностика", "Техническое обслуживание", "Ремонт")

SERVICES = [
    {"id": 1, "name": "Компьютерная диагностика", "category": "Диагностика", "price": 1500, "duration": 40, "description": "Чтение кодов ошибок и проверка электронных систем."},
    {"id": 2, "name": "Диагностика подвески", "category": "Диагностика", "price": 1000, "duration": 30, "description": "Осмотр элементов подвески на подъёмнике."},
    {"id": 3, "name": "Замена моторного масла", "category": "Техническое обслуживание", "price": 800, "duration": 30, "description": "Стоимость работы без расходных материалов."},
    {"id": 4, "name": "Замена масляного фильтра", "category": "Техническое обслуживание", "price": 300, "duration": 15, "description": "Замена фильтра, без стоимости детали."},
    {"id": 5, "name": "Замена тормозных колодок", "category": "Ремонт", "price": 1800, "duration": 60, "description": "Замена колодок на одной оси, без стоимости деталей."},
    {"id": 6, "name": "Замена свечей зажигания", "category": "Техническое обслуживание", "price": 1200, "duration": 45, "description": "Стоимость работы без свечей зажигания."},
    {"id": 7, "name": "Замена аккумулятора", "category": "Техническое обслуживание", "price": 500, "duration": 20, "description": "Снятие и установка аккумулятора, без его стоимости."},
    {"id": 8, "name": "Проверка тормозной системы", "category": "Диагностика", "price": 900, "duration": 30, "description": "Проверка состояния тормозных механизмов и магистралей."},
    {"id": 9, "name": "Замена ремня привода", "category": "Ремонт", "price": 2000, "duration": 60, "description": "Замена ремня навесного оборудования, без стоимости детали."},
]

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


def advance_order(order):
    """Единственная операция изменения оформленного документа — следующий этап."""
    index = ORDER_STATUSES.index(order["status"])
    if index == len(ORDER_STATUSES) - 1:
        return False
    if index == len(ORDER_STATUSES) - 2 and order["completed_at"] is None:
        order["completed_at"] = local_now().replace(tzinfo=LOCAL_TIMEZONE)
    order["status"] = ORDER_STATUSES[index + 1]
    return True


def make_orders(clients, cars, services, today):
    client_by_id = {c["id"]: c for c in clients}
    car_by_id = {c["id"]: c for c in cars}
    service_by_id = {s["id"]: s for s in services}
    examples = [
        (27, 1, 0, [3, 4], "Замена масла и масляного фильтра", "В работе"),
        (26, 2, 0, [1, 2], "Проверка подвески и электронных систем", "Оформлен"),
        (25, 3, 1, [8, 5], "Проверка тормозов и замена колодок", "Оформлен"),
        (24, 4, 1, [1, 6], "Диагностика и замена свечей", "Готов к выдаче"),
        (23, 5, 2, [2, 9], "Осмотр подвески и замена ремня", "Завершён"),
        (22, 6, 2, [1, 3, 4], "Плановое техническое обслуживание", "В работе"),
        (21, 7, 3, [7, 8], "Замена аккумулятора и проверка тормозов", "Завершён"),
    ]
    result = []
    for number, car_id, days_ago, service_ids, reason, status in examples:
        car = car_by_id[car_id]
        order = create_order(number, today - timedelta(days=days_ago), client_by_id[car["owner_id"]],
                             car, [service_by_id[s] for s in service_ids], reason)
        order["status"] = status
        if status == "Завершён":
            order["completed_at"] = datetime.combine(order["date"] + timedelta(days=1), time(16, 30), LOCAL_TIMEZONE)
        result.append(order)
    return result


def normalize_service_name(value):
    return " ".join(value.split()).casefold()


def make_appointments(today):
    """Свежие даты при каждом запуске, без копий ФИО и данных автомобиля."""
    rows = [
        (1, 1, 1, 9, 0, "Замена моторного масла", "Запланирована"),
        (2, 2, 1, 10, 30, "Диагностика подвески", "Запланирована"),
        (3, 3, 1, 12, 0, "Проверка тормозной системы", "Отменена"),
        (4, 4, 2, 9, 30, "Компьютерная диагностика", "Запланирована"),
        (5, 5, 2, 11, 0, "Замена тормозных колодок", "Запланирована"),
        (6, 6, 3, 14, 0, "Плановое обслуживание", "Отменена"),
        (7, 7, 3, 15, 30, "Проверка перед поездкой", "Запланирована"),
    ]
    return [{"id": number, "car_id": car_id, "date": today + timedelta(days=offset),
             "time": time(hour, minute), "reason": reason, "note": "", "status": status}
            for number, car_id, offset, hour, minute, reason, status in rows]


def normalize_plate(value):
    """Одинаковый ключ для регистра, пробелов и похожих латинских букв."""
    value = value.upper().translate(str.maketrans("ABCEHKMOPTXY", "АВСЕНКМОРТХУ"))
    return "".join(char for char in value if not char.isspace() and char not in "-·")
