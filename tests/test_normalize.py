#!/usr/bin/env python3
"""Прогон нормализации на фикстуре. Названия — типичные для WB формулировки.

Запуск: python -m tests.test_normalize   (из корня репозитория)
"""

from wb_aggregator import Constraints, check, parse_price, parse_specs

FIXTURE = [
    # v18: цена в sizes[].price, копейки
    {
        "id": 1, "supplierId": 111, "supplier": "СИТИЛИНК",
        "name": "Ноутбук ASUS Vivobook 15 16/1024 ГБ SSD IPS серый",
        "sizes": [{"price": {"basic": 6199000, "product": 4789000}}],
    },
    {
        "id": 2, "supplierId": 222, "supplier": "М.ВИДЕО",
        "name": 'Ноутбук игровой 15.6" Ryzen 5 16 ГБ / 1 ТБ SSD',
        "sizes": [{"price": {"basic": 5900000, "product": 4995000}}],
    },
    # старый формат priceU/salePriceU
    {
        "id": 3, "supplierId": 333, "supplier": "ХОЛОДИЛЬНИК.РУ",
        "name": "Ноутбук HUAWEI MateBook D16 16/512 Гб",
        "priceU": 6400000, "salePriceU": 4830000,
    },
    # пара 16/512 без единиц
    {
        "id": 4, "supplierId": 444, "supplier": "ОНЛАЙНТРЕЙД.РУ",
        "name": "Ноутбук Lenovo IdeaPad Slim 3 15IAH8 16/1024",
        "sizes": [{"price": {"basic": 5500000, "product": 4990000}}],
    },
    # цена выше порога
    {
        "id": 5, "supplierId": 111, "supplier": "СИТИЛИНК",
        "name": "Ноутбук MSI Katana 17 32 ГБ 1 ТБ SSD RTX 4060",
        "sizes": [{"price": {"basic": 12000000, "product": 9899000}}],
    },
    # чужой продавец
    {
        "id": 6, "supplierId": 999, "supplier": "ТехноМаркет777",
        "name": "Ноутбук 16 ГБ 1 ТБ SSD новый",
        "sizes": [{"price": {"basic": 4500000, "product": 3990000}}],
    },
    # RAM ниже порога
    {
        "id": 7, "supplierId": 222, "supplier": "М.ВИДЕО",
        "name": "Ноутбук Acer Aspire 3 8 ГБ 1 ТБ SSD",
        "sizes": [{"price": {"basic": 4200000, "product": 3790000}}],
    },
    # характеристики не извлекаются -> needs_review
    {
        "id": 8, "supplierId": 333, "supplier": "ХОЛОДИЛЬНИК.РУ",
        "name": "Ноутбук ультратонкий металлический корпус для работы и учёбы",
        "sizes": [{"price": {"basic": 5100000, "product": 4600000}}],
    },
    # структурированные характеристики перебивают название
    {
        "id": 9, "supplierId": 444, "supplier": "ОНЛАЙНТРЕЙД.РУ",
        "name": "Ноутбук Digma Pro в комплекте чехол 16 ГБ",
        "sizes": [{"price": {"basic": 5300000, "product": 4750000}}],
        "options": [
            {"name": "Объем оперативной памяти", "value": "16 ГБ"},
            {"name": "Объем накопителя SSD", "value": "1 ТБ"},
        ],
    },
    # мусорная цена аксессуара рядом с настоящей
    {
        "id": 10, "supplierId": 111, "supplier": "СИТИЛИНК",
        "name": "Ноутбук HP 250 G9 16 ГБ 1024 ГБ SSD",
        "sizes": [{"price": {"basic": 4900000, "product": 4490000, "total": 39000}}],
    },
]

SELLERS = frozenset({111, 222, 333, 444})
C = Constraints(seller_ids=SELLERS)


def main() -> None:
    passed = review = 0
    print(f"{'id':>3}  {'цена':>8}  {'RAM':>5}  {'SSD':>7}  вердикт")
    print("-" * 78)
    for p in FIXTURE:
        price = parse_price(p)
        specs = parse_specs(p["name"], p.get("options"))
        v = check(p, specs, price, C)
        mark = "PASS" if v.passed else ("REVIEW" if v.needs_review else "skip")
        if v.passed:
            passed += 1
        if v.needs_review:
            review += 1
        print(f"{p['id']:>3}  "
              f"{(str(price.effective) + '₽') if price.effective else '—':>8}  "
              f"{specs.ram_gb or '—':>5}  {specs.storage_gb or '—':>7}  "
              f"{mark:<7} {v.reason or ''}")
        if price.effective:
            print(f"     price.kind={price.kind}  "
                  f"specs.src=({specs.ram_source},{specs.storage_source})")

    print("-" * 78)
    print(f"прошло: {passed}, на ревью: {review}, из {len(FIXTURE)}")


if __name__ == "__main__":
    main()
