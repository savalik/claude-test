# wb_aggregator relay

Реверс-прокси для обхода rate limit на общих/облачных IP. Разворачивается
на отдельном VPS с российским IP; `wb_aggregator` (откуда угодно) шлёт
запросы сюда, relay сам стучится в wb.ru и возвращает ответ как есть.

## Требования к VPS

Минимальные: 1 vCPU, 512 МБ–1 ГБ RAM, любой дистрибутив с Python 3.10+.
Трафик — считаные КБ на запрос, тарифы "от 100–300 ₽/мес" с запасом хватает
(например VDSina, SprintHost, Timeweb, Beget — конкретного провайдера
выбирайте сами, requirements минимальны).

## Установка

```bash
mkdir -p /opt/wb-relay && cd /opt/wb-relay
# скопировать сюда server.py и requirements.txt
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Сгенерировать секрет и подставить его в двух местах — здесь и в клиенте:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Запуск как systemd-сервис

```bash
cp wb-relay.service /etc/systemd/system/
# в /etc/systemd/system/wb-relay.service подставить реальный RELAY_TOKEN
systemctl daemon-reload
systemctl enable --now wb-relay
```

Проверка:

```bash
curl -s http://<VPS-IP>:8080/health
```

## Важно: закрыть порт от посторонних

`/fetch` форвардит только на `*.wb.ru` и `*.wildberries.ru` и требует токен
в заголовке `X-Relay-Token`, но порт 8080 всё равно голый HTTP без TLS.
Рекомендуется поставить перед uvicorn обратный прокси (nginx/caddy) с
HTTPS и файрвол (`ufw allow 22,443/tcp`, остальное закрыть), и стучаться в
relay только по HTTPS. Простейший вариант — Caddy с автоматическим
Let's Encrypt на домене-поддомене, который вы контролируете.

## Настройка клиента

В окружении, где работает `wb_aggregator` (в т.ч. в облачной сессии),
задать переменные:

```bash
export WB_RELAY_URL="https://<ваш-домен-или-IP>/fetch"
export WB_RELAY_TOKEN="<тот же секрет>"
```

Дальше `wb_aggregator.probe` и коннектор сами начнут ходить через relay —
код в `wb_aggregator/config.py` подхватывает эти переменные, ничего
менять в коде не нужно. Без них всё работает как раньше — прямыми
запросами.
