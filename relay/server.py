#!/usr/bin/env python3
"""
Реверс-прокси relay для wb_aggregator.

Разворачивается на маленьком VPS с российским IP. Принимает запрос от
wb_aggregator (который может работать откуда угодно, в том числе из
песочницы с общим/перегруженным IP), сам делает HTTP GET к wb.ru и
возвращает ответ как есть. Для wb.ru запрос выглядит так, будто он пришёл
с IP этого VPS, а не из песочницы.

Публично доступен в интернете — поэтому:
- запросы форвардятся только на хосты из ALLOWED_HOST_SUFFIXES (иначе это
  был бы open proxy для чего угодно);
- требуется общий секрет в заголовке X-Relay-Token.

Запуск:
    RELAY_TOKEN=... uvicorn server:app --host 0.0.0.0 --port 8080
"""

import os
from urllib.parse import urlparse

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response

RELAY_TOKEN = os.environ["RELAY_TOKEN"]  # без токена сервер не стартует
ALLOWED_HOST_SUFFIXES = ("wb.ru", "wildberries.ru")
FORWARD_TIMEOUT = 25

app = FastAPI()


def _host_allowed(host: str) -> bool:
    host = host.lower()
    return any(host == s or host.endswith("." + s) for s in ALLOWED_HOST_SUFFIXES)


@app.get("/fetch")
def fetch(request: Request, target: str):
    if request.headers.get("X-Relay-Token") != RELAY_TOKEN:
        raise HTTPException(status_code=403, detail="bad token")

    host = urlparse(target).hostname or ""
    if not _host_allowed(host):
        raise HTTPException(status_code=400, detail=f"host not allowed: {host}")

    forward_headers = {
        key[len("X-Fwd-"):]: value
        for key, value in request.headers.items()
        if key.lower().startswith("x-fwd-")
    }

    try:
        upstream = requests.get(target, headers=forward_headers, timeout=FORWARD_TIMEOUT)
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", "application/octet-stream"),
    )


@app.get("/health")
def health():
    return {"status": "ok"}
