#!/usr/bin/env python3
"""
Probe-скрипт для внутреннего API Wildberries.

Задача: снять неопределённость перед реализацией коннектора.
Ничего не сохраняет, только печатает вердикты.

Запускать локально (домен wb.ru доступен не отовсюду):
    python -m wb_aggregator.probe
"""

import json
import time
from typing import Any, Optional

import requests

from .config import (
    Constraints,
    APP_TYPE, CARD_URL, CURR, DEST, FILTERS_URL, HEADERS, LANG,
    PAUSE_SECONDS, REQUEST_TIMEOUT, SEARCH_HOSTS, SEARCH_QUERY, TARGET_SELLERS,
)
from .normalize import parse_price

# --- транспорт --------------------------------------------------------------

class WbError(Exception):
    pass


def get_json(url: str, params: dict, timeout: int = REQUEST_TIMEOUT) -> Any:
    time.sleep(PAUSE_SECONDS)
    r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
    if r.status_code == 429:
        raise WbError(f"429 rate limit: {url}")
    r.raise_for_status()
    # WB иногда отдаёт text/plain с JSON внутри — не полагаемся на content-type
    try:
        return r.json()
    except json.JSONDecodeError:
        raise WbError(f"не JSON, первые 300 символов: {r.text[:300]!r}")


def base_params(page: int = 1, **extra) -> dict:
    p = {
        "appType": APP_TYPE,
        "curr": CURR,
        "dest": DEST,
        "lang": LANG,
        "page": page,
        "resultset": "catalog",
        "sort": "popular",
        "spp": 30,
        "suppressSpellcheck": "false",
    }
    p.update(extra)
    return p


def extract_products(payload: Any) -> list[dict]:
    """Ответ приходил в разных обёртках: {'data': {'products': []}} и {'products': []}."""
    if not isinstance(payload, dict):
        return []
    if isinstance(payload.get("products"), list):
        return payload["products"]
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("products"), list):
        return data["products"]
    return []


# --- probe 1: жив ли эндпоинт и в какой обёртке ответ ------------------------

def probe_endpoint() -> Optional[str]:
    print("\n=== 1. Доступность эндпоинта поиска ===")
    for host in SEARCH_HOSTS:
        try:
            payload = get_json(host, base_params(query=SEARCH_QUERY))
        except Exception as e:
            print(f"  [FAIL] {host}: {type(e).__name__}: {e}")
            continue
        products = extract_products(payload)
        shape = "products" if "products" in payload else (
            "data.products" if "data" in payload else f"неизвестно: {list(payload)[:6]}"
        )
        print(f"  [OK]   {host}")
        print(f"         обёртка: {shape}, товаров на странице: {len(products)}")
        if products:
            print(f"         ключи товара: {sorted(products[0].keys())}")
        return host
    return None


# --- probe 2: резолв supplierId по названиям ---------------------------------

def probe_sellers(search_url: str) -> dict[str, int]:
    """
    Отдельного публичного справочника поставщиков нет.
    Практичный путь: пройти несколько страниц выдачи и собрать supplier -> supplierId.
    """
    print("\n=== 2. Резолв supplierId ===")
    found: dict[str, int] = {}
    seen: dict[str, int] = {}

    for page in range(1, 6):
        try:
            payload = get_json(search_url, base_params(page=page, query=SEARCH_QUERY))
        except Exception as e:
            print(f"  страница {page}: {e}")
            break
        products = extract_products(payload)
        if not products:
            break
        for p in products:
            name, sid = p.get("supplier"), p.get("supplierId")
            if name and sid:
                seen[name] = sid

    norm = lambda s: s.upper().replace(" ", "").replace("«", "").replace("»", "")
    targets = {norm(t): t for t in TARGET_SELLERS}
    for name, sid in seen.items():
        key = norm(name)
        for tkey, original in targets.items():
            if tkey in key or key in tkey:
                found[original] = sid
                print(f"  [OK]   {original:18} -> supplierId={sid}  (в выдаче: {name!r})")

    for t in TARGET_SELLERS:
        if t not in found:
            print(f"  [MISS] {t:18} не встретился на первых страницах")

    print(f"  всего уникальных продавцов просмотрено: {len(seen)}")
    if len(found) < len(TARGET_SELLERS):
        print("  -> добить недостающих: открыть страницу продавца на сайте и снять "
              "supplierId из XHR, либо расширить число страниц/запросов")
    return found


# --- probe 3: работают ли серверные фильтры ----------------------------------

def probe_server_filters(search_url: str, sellers: dict[str, int]) -> None:
    """
    Проверяем каждый фильтр отдельно: изменилось ли количество результатов
    и не протекают ли посторонние значения.
    """
    print("\n=== 3. Серверные фильтры ===")

    def count_and_sellers(params: dict) -> tuple[int, set]:
        payload = get_json(search_url, params)
        products = extract_products(payload)
        return len(products), {p.get("supplier") for p in products}

    baseline, _ = count_and_sellers(base_params(query=SEARCH_QUERY))
    print(f"  базовая выдача без фильтров: {baseline} товаров на странице")

    # 3a. фильтр по продавцу
    if sellers:
        name, sid = next(iter(sellers.items()))
        for param in ("fsupplier", "supplier"):
            try:
                n, got = count_and_sellers(base_params(query=SEARCH_QUERY, **{param: sid}))
            except Exception as e:
                print(f"  [FAIL] {param}={sid}: {e}")
                continue
            clean = got <= {name} or all(
                name.upper()[:6] in (g or "").upper() for g in got if g
            )
            verdict = "OK" if n and clean else "ПРОТЕКАЕТ"
            print(f"  [{verdict}] {param}={sid} -> {n} товаров, продавцы в выдаче: {got}")

    # 3b. фильтр по цене (в копейках, диапазон через ';')
    price_max = Constraints().price_max
    price_param = f"0;{price_max * 100}"
    for param in ("priceU", "price"):
        try:
            payload = get_json(search_url, base_params(query=SEARCH_QUERY, **{param: price_param}))
        except Exception as e:
            print(f"  [FAIL] {param}={price_param}: {e}")
            continue
        products = extract_products(payload)
        prices = [(parse_price(p).effective) for p in products]
        prices = [x for x in prices if x is not None]
        over = [x for x in prices if x > price_max]
        if not products:
            print(f"  [ПУСТО] {param}={price_param} -> 0 товаров, параметр может быть неверным")
        else:
            verdict = "OK" if not over else "ПРОТЕКАЕТ"
            print(f"  [{verdict}] {param}={price_param} -> {len(products)} товаров, "
                  f"max={max(prices) if prices else '-'}₽, выше порога: {len(over)}")

    # 3c. фасеты характеристик
    print("\n  фасеты (RAM / SSD):")
    try:
        payload = get_json(FILTERS_URL, base_params(query=SEARCH_QUERY))
    except Exception as e:
        print(f"  [FAIL] эндпоинт filters недоступен: {e}")
        return
    filters = (payload.get("data") or payload).get("filters") or []
    print(f"  доступно фасетов: {len(filters)}")
    for f in filters:
        title = (f.get("name") or "").lower()
        if any(k in title for k in ("оператив", "озу", "ram", "накопит", "ssd", "памят")):
            items = f.get("items") or []
            preview = [(i.get("name"), i.get("id")) for i in items[:8]]
            print(f"    key={f.get('key')!r:14} name={f.get('name')!r}")
            print(f"      значения: {preview}{' ...' if len(items) > 8 else ''}")
    print("  -> собрать key + id значений >= порога, они пойдут в запрос как "
          "f{key}={id1};{id2}")


# --- probe 4: глубина пагинации ---------------------------------------------

def probe_pagination(search_url: str, sellers: dict[str, int]) -> None:
    """
    Главный вопрос: потолок глубины на запрос или на клиента,
    и совпадает ли заявленный total с фактически выгруженным.
    """
    print("\n=== 4. Пагинация ===")

    payload = get_json(search_url, base_params(query=SEARCH_QUERY))
    total = (payload.get("data") or payload).get("total")
    print(f"  заявленный total по запросу {SEARCH_QUERY!r}: {total}")

    print("  ищем страницу, на которой выдача кончается (двоичный поиск по шагам):")
    last_ok = 0
    for page in (1, 5, 10, 20, 40, 60, 80, 100, 150, 200):
        try:
            products = extract_products(get_json(search_url, base_params(page=page, query=SEARCH_QUERY)))
        except Exception as e:
            print(f"    page={page:<4} ошибка: {e}")
            break
        print(f"    page={page:<4} товаров: {len(products)}")
        if not products:
            print(f"  -> потолок между {last_ok} и {page}")
            break
        last_ok = page
    else:
        print(f"  -> потолок не найден до page=200, last_ok={last_ok}")

    # тот же прогон с фильтром по продавцу: потолок на запрос или глобальный?
    if sellers:
        name, sid = next(iter(sellers.items()))
        print(f"  тот же тест с фильтром по продавцу {name}:")
        for page in (1, 10, 30, 60, 100):
            try:
                products = extract_products(
                    get_json(search_url, base_params(page=page, query=SEARCH_QUERY, fsupplier=sid))
                )
            except Exception as e:
                print(f"    page={page:<4} ошибка: {e}")
                break
            print(f"    page={page:<4} товаров: {len(products)}")
            if not products:
                break

    # размер страницы
    print("  проверка максимального размера страницы (spp):")
    for spp in (30, 100, 300):
        try:
            products = extract_products(get_json(search_url, base_params(query=SEARCH_QUERY, spp=spp)))
            print(f"    spp={spp:<4} фактически пришло: {len(products)}")
        except Exception as e:
            print(f"    spp={spp:<4} ошибка: {e}")


# --- probe 5: карточка товара, есть ли характеристики ------------------------

def probe_card(search_url: str) -> None:
    print("\n=== 5. Карточка товара: откуда брать RAM/SSD ===")
    products = extract_products(get_json(search_url, base_params(query=SEARCH_QUERY)))
    if not products:
        print("  нет товаров для проверки")
        return
    nm = products[0].get("id")
    try:
        payload = get_json(CARD_URL, {
            "appType": APP_TYPE, "curr": CURR, "dest": DEST, "nm": nm, "spp": 30,
        })
    except Exception as e:
        print(f"  [FAIL] card.wb.ru недоступен: {e}")
        print("  -> характеристики придётся тянуть из basket-CDN "
             "(basket-XX.wbbasket.ru/volY/partZ/{nm}/info/ru/card.json)")
        return
    cards = extract_products(payload)
    if not cards:
        print(f"  ответ есть, но products пуст; ключи: {list(payload)[:8]}")
        return
    card = cards[0]
    print(f"  nm={nm}, ключи карточки: {sorted(card.keys())}")
    opts = card.get("options") or card.get("grouped_options") or []
    if opts:
        print(f"  характеристики ({len(opts)}): {opts[:10]}")
    else:
        print("  [ВАЖНО] в ответе card.wb.ru нет характеристик -> RAM/SSD только из "
              "названия, либо нужен basket-CDN с card.json")


# --- main -------------------------------------------------------------------

def main() -> None:
    search_url = probe_endpoint()
    if not search_url:
        print("\nни один хост поиска не ответил — дальше идти бессмысленно")
        return
    sellers = probe_sellers(search_url)
    probe_server_filters(search_url, sellers)
    probe_pagination(search_url, sellers)
    probe_card(search_url)

    print("\n=== Итог ===")
    print("Записать в конфиг: supplierId четырёх продавцов, имя рабочего параметра")
    print("фильтра по продавцу и по цене, key+id фасетов RAM/SSD, потолок глубины,")
    print("максимальный spp. После этого писать коннектор.")


if __name__ == "__main__":
    main()
