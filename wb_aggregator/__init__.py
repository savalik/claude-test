"""Агрегатор объявлений о ноутбуках. MVP: коннектор Wildberries."""

from .config import Constraints, QueryStrategy
from .normalize import Price, Specs, Verdict, check, parse_price, parse_specs

__all__ = [
    "Constraints",
    "QueryStrategy",
    "Price",
    "Specs",
    "Verdict",
    "check",
    "parse_price",
    "parse_specs",
]
