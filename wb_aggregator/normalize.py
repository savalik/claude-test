"""
Нормализация ответа Wildberries: цена и характеристики.

Функции чистые, сети не трогают — тестируются на фикстуре.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

from .config import MIN_PLAUSIBLE_PRICE_RUB, Constraints


# --- цена -------------------------------------------------------------------

@dataclass
class Price:
    effective: Optional[int]          # минимальная цена, рубли
    kind: Optional[str]               # какое поле выиграло
    raw: dict = field(default_factory=dict)   # все варианты как пришли, копейки


def parse_price(product: dict) -> Price:
    """
    price_effective = min(все непустые ценовые варианты).
    Поддерживает v18 (sizes[].price.{basic,product}) и старый формат (priceU/salePriceU).
    Копейки -> рубли.
    """
    raw: dict[str, int] = {}

    for size in product.get("sizes") or []:
        price = size.get("price") or {}
        for key in ("product", "basic", "total"):
            v = price.get(key)
            if isinstance(v, (int, float)) and v > 0:
                raw.setdefault(f"sizes.{key}", int(v))

    for key in ("salePriceU", "priceU"):
        v = product.get(key)
        if isinstance(v, (int, float)) and v > 0:
            raw.setdefault(key, int(v))

    candidates = {k: v for k, v in raw.items() if v // 100 >= MIN_PLAUSIBLE_PRICE_RUB}
    if not candidates:
        return Price(effective=None, kind=None, raw=raw)

    kind, kop = min(candidates.items(), key=lambda kv: kv[1])
    return Price(effective=kop // 100, kind=kind, raw=raw)


# --- характеристики ---------------------------------------------------------

_UNIT_GB = {"гб": 1, "gb": 1, "г": 1, "g": 1}
_UNIT_TB = {"тб": 1024, "tb": 1024, "т": 1024}

# «16 ГБ», «16Гб», «16GB», «512 Gb», «1 ТБ», «1Tb»
_SIZE_RE = re.compile(
    r"(?<![\d.,])(\d{1,4})\s*(тб|tb|гб|gb)\b",
    re.IGNORECASE,
)
# «16/512», «8 / 256» — характерная для ноутбуков запись RAM/SSD
_PAIR_RE = re.compile(r"(?<!\d)(\d{1,3})\s*/\s*(\d{3,4})(?!\d)")

_RAM_HINT = re.compile(r"(озу|оперативн|ram|ddr)", re.IGNORECASE)
_SSD_HINT = re.compile(r"(ssd|nvme|накопит|встроенн|память|memory|storage)", re.IGNORECASE)

_PLAUSIBLE_RAM = {4, 8, 12, 16, 24, 32, 48, 64, 96, 128}


def _to_gb(value: int, unit: str) -> int:
    u = unit.lower()
    if u in _UNIT_TB:
        return value * _UNIT_TB[u]
    return value * _UNIT_GB.get(u, 1)


@dataclass
class Specs:
    ram_gb: Optional[int] = None
    storage_gb: Optional[int] = None
    ram_source: Optional[str] = None
    storage_source: Optional[str] = None

    @property
    def complete(self) -> bool:
        return self.ram_gb is not None and self.storage_gb is not None


def parse_specs(title: str, options: Optional[list[dict]] = None) -> Specs:
    """
    Приоритет: структурированные характеристики карточки -> название.
    options: [{'name': 'Объем оперативной памяти', 'value': '16 ГБ'}, ...]
    """
    specs = Specs()

    for opt in options or []:
        name = str(opt.get("name") or "")
        value = str(opt.get("value") or "")
        m = _SIZE_RE.search(value)
        if not m:
            continue
        gb = _to_gb(int(m.group(1)), m.group(2))
        if _RAM_HINT.search(name) and specs.ram_gb is None:
            specs.ram_gb, specs.ram_source = gb, "options"
        elif _SSD_HINT.search(name) and specs.storage_gb is None:
            specs.storage_gb, specs.storage_source = gb, "options"

    if specs.complete:
        return specs

    # разбор названия
    sizes = [(_to_gb(int(v), u), m.start()) for m, v, u in
             ((m, m.group(1), m.group(2)) for m in _SIZE_RE.finditer(title))]

    if specs.ram_gb is None or specs.storage_gb is None:
        rams = [gb for gb, _ in sizes if gb in _PLAUSIBLE_RAM and gb <= 128]
        storages = [gb for gb, _ in sizes if gb >= 128]
        # 16 ГБ может быть и RAM, и накопителем: если оба кандидата совпали,
        # меньшее считаем RAM, большее — накопителем
        if rams and storages and max(storages) > min(rams):
            if specs.ram_gb is None:
                specs.ram_gb, specs.ram_source = min(rams), "title"
            if specs.storage_gb is None:
                specs.storage_gb, specs.storage_source = max(storages), "title"

    if specs.ram_gb is None or specs.storage_gb is None:
        m = _PAIR_RE.search(title)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a in _PLAUSIBLE_RAM and b >= 128:
                if specs.ram_gb is None:
                    specs.ram_gb, specs.ram_source = a, "title:pair"
                if specs.storage_gb is None:
                    specs.storage_gb, specs.storage_source = b, "title:pair"

    return specs


# --- применение ограничений -------------------------------------------------

@dataclass
class Verdict:
    passed: bool
    reason: Optional[str] = None
    needs_review: bool = False


def check(product: dict, specs: Specs, price: Price, c: Constraints) -> Verdict:
    sid = product.get("supplierId")
    if c.seller_ids and sid not in c.seller_ids:
        return Verdict(False, f"чужой продавец supplierId={sid}")

    if price.effective is None:
        return Verdict(False, "не удалось определить цену", needs_review=True)
    if price.effective > c.price_max:
        return Verdict(False, f"цена {price.effective}₽ > {c.price_max}₽")

    if specs.ram_gb is None or specs.storage_gb is None:
        missing = [n for n, v in (("RAM", specs.ram_gb), ("SSD", specs.storage_gb)) if v is None]
        return Verdict(False, f"не извлеклось: {', '.join(missing)}", needs_review=True)

    if specs.ram_gb < c.ram_min_gb:
        return Verdict(False, f"RAM {specs.ram_gb} ГБ < {c.ram_min_gb} ГБ")
    if specs.storage_gb < c.storage_min_gb:
        return Verdict(False, f"накопитель {specs.storage_gb} ГБ < {c.storage_min_gb} ГБ")

    return Verdict(True)
