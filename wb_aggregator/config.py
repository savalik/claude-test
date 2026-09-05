"""
Конфигурация коннектора.

Значения, помеченные TODO, заполняются по результатам прогона probe.py.
До этого коннектор писать рано — имена параметров и id фасетов угадывать нельзя.
"""

from dataclasses import dataclass
from typing import Optional

# --- параметры внутреннего API WB -------------------------------------------

DEST = -1257786          # регион/склад: влияет на цену и наличие. Менять осознанно.
CURR = "rub"
APP_TYPE = 1             # 1 = веб, 4 = мобильное
LANG = "ru"

SEARCH_HOSTS = [
    "https://search.wb.ru/exactmatch/ru/common/v18/search",
    "https://u-search.wb.ru/exactmatch/ru/common/v18/search",
]
FILTERS_URL = "https://search.wb.ru/exactmatch/ru/common/v18/filters"
SELLER_CATALOG_URL = "https://catalog.wb.ru/sellers/catalog"
CARD_URL = "https://card.wb.ru/cards/v2/detail"

HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8",
    "Origin": "https://www.wildberries.ru",
    "Referer": "https://www.wildberries.ru/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "cross-site",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
    ),
}

PAUSE_SECONDS = 1.2      # пауза между запросами; не убирать
REQUEST_TIMEOUT = 20

# --- целевые продавцы --------------------------------------------------------

TARGET_SELLERS = [
    "ХОЛОДИЛЬНИК.РУ",
    "ОНЛАЙНТРЕЙД.РУ",
    "СИТИЛИНК",
    "М.ВИДЕО",
]

# TODO(probe): заполнить по результатам probe_sellers()
SELLER_IDS: dict[str, int] = {}

# --- ограничения поиска ------------------------------------------------------

SEARCH_QUERY = "ноутбук"
MIN_PLAUSIBLE_PRICE_RUB = 5_000   # ниже — почти наверняка аксессуар или артефакт


@dataclass(frozen=True)
class Constraints:
    """Ограничения, которые коннектор принимает на вход."""
    price_max: int = 50_000
    ram_min_gb: int = 16
    storage_min_gb: int = 1000     # 1 ТБ; порог 1000, чтобы не терять «1000 ГБ»
    storage_type: str = "SSD"
    seller_ids: frozenset[int] = frozenset()


@dataclass
class QueryStrategy:
    """
    Стратегия обхода. Значения — из probe.py, не из головы.
    seller_batching: per_seller по умолчанию (см. docs/02-wb-connector-spec.md).
    """
    seller_batching: str = "per_seller"     # per_seller | combined
    page_size: int = 100                    # TODO(probe): максимальный рабочий spp
    max_depth: Optional[int] = None         # TODO(probe): потолок глубины пагинации
    split_on_depth_limit: bool = True

    # TODO(probe): какое имя параметра реально работает
    seller_param: str = "fsupplier"         # fsupplier | supplier
    price_param: str = "priceU"             # priceU | price


# TODO(probe): key фасета и id значений >= порога, из probe_server_filters()
FACET_RAM: dict = {}       # {"key": "f...", "value_ids": [...]}
FACET_STORAGE: dict = {}
