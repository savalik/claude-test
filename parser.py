#!/usr/bin/env python3
"""
Парсер тестов с сайта prombez24.com

Алгоритм:
1. Получает сессию и CSRF-токен
2. Загружает все вопросы постранично через /ticket/ordered/
3. Для каждого вопроса перебирает варианты ответов через POST /ticket/check
4. Определяет правильный ответ по ответу сервера
5. Сохраняет результат в JSON-файл
"""

import argparse
import json
import re
import sys
import time

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://prombez24.com"
DEFAULT_TEST_ID = 293
DEFAULT_PAGE_SIZE = 10
REQUEST_DELAY = 0.5  # секунд между запросами


def create_session() -> requests.Session:
    """Создаёт сессию с User-Agent браузера."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    })
    return session


def get_csrf_token(session: requests.Session, test_id: int) -> str:
    """Получает CSRF-токен из страницы с билетом."""
    url = f"{BASE_URL}/ticket/ordered/"
    params = {"testId": test_id, "page": 0, "size": DEFAULT_PAGE_SIZE}
    resp = session.get(url, params=params)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # Ищем CSRF-токен в мета-теге или скрытом поле формы
    meta = soup.find("meta", attrs={"name": "_csrf"})
    if meta:
        return meta["content"]

    hidden = soup.find("input", attrs={"name": "_csrf"})
    if hidden:
        return hidden["value"]

    raise RuntimeError(
        "Не удалось найти CSRF-токен. "
        "Возможно, структура страницы изменилась."
    )


def parse_questions_page(html: str) -> list[dict]:
    """
    Парсит одну страницу с вопросами.

    Возвращает список словарей:
    [
        {
            "id": 338580,
            "text": "Текст вопроса",
            "answers": [
                {"id": 123, "index": 0, "text": "Вариант 1"},
                {"id": 124, "index": 1, "text": "Вариант 2"},
                ...
            ]
        },
        ...
    ]
    """
    soup = BeautifulSoup(html, "html.parser")
    questions = []

    # Ищем все блоки вопросов. Типичные паттерны для Spring MVC форм:
    # - каждый вопрос обёрнут в div/fieldset
    # - скрытое поле questionList[N].id хранит ID вопроса
    # - радио-кнопки/чекбоксы questionList[N].answers[M].checked для ответов

    # Стратегия 1: ищем скрытые поля questionList[N].id
    question_id_inputs = soup.find_all(
        "input", attrs={"name": re.compile(r"questionList\[\d+\]\.id")}
    )

    if question_id_inputs:
        for q_input in question_id_inputs:
            name = q_input["name"]
            match = re.search(r"questionList\[(\d+)\]", name)
            if not match:
                continue
            q_index = int(match.group(1))
            q_id = int(q_input["value"])

            # Текст вопроса — ищем ближайший родительский блок
            question_text = _extract_question_text(q_input)

            # Ищем ответы для этого вопроса
            answers = _extract_answers(soup, q_index)

            questions.append({
                "id": q_id,
                "index": q_index,
                "text": question_text,
                "answers": answers,
            })
    else:
        # Стратегия 2: ищем по радио-кнопкам/чекбоксам
        answer_inputs = soup.find_all(
            "input",
            attrs={"name": re.compile(r"questionList\[\d+\]\.answers\[\d+\]\.checked")},
        )
        seen_questions = {}
        for a_input in answer_inputs:
            name = a_input["name"]
            q_match = re.search(r"questionList\[(\d+)\]", name)
            a_match = re.search(r"answers\[(\d+)\]", name)
            if not q_match or not a_match:
                continue
            q_index = int(q_match.group(1))
            a_index = int(a_match.group(1))

            if q_index not in seen_questions:
                # Ищем ID вопроса рядом
                q_id = _find_question_id_near(soup, q_index, a_input)
                question_text = _extract_question_text(a_input)
                seen_questions[q_index] = {
                    "id": q_id,
                    "index": q_index,
                    "text": question_text,
                    "answers": [],
                }

            answer_text = _extract_answer_text(a_input)
            answer_id = _find_answer_id_near(soup, q_index, a_index)
            seen_questions[q_index]["answers"].append({
                "id": answer_id,
                "index": a_index,
                "text": answer_text,
            })

        questions = list(seen_questions.values())

    return questions


def _extract_question_text(element) -> str:
    """Извлекает текст вопроса из ближайшего контейнера."""
    # Поднимаемся по DOM, ищем текст в заголовках, label или p
    parent = element
    for _ in range(10):
        parent = parent.parent
        if parent is None:
            break

        # Ищем текст в различных элементах
        for tag in ["h3", "h4", "h5", "p", "label", "span", "div"]:
            text_el = parent.find(tag, class_=re.compile(r"question|title|text", re.I))
            if text_el:
                return text_el.get_text(strip=True)

        # Также ищем по data-атрибутам или просто первый заголовок
        header = parent.find(re.compile(r"^h\d$"))
        if header:
            return header.get_text(strip=True)

    return ""


def _extract_answers(soup: BeautifulSoup, q_index: int) -> list[dict]:
    """Извлекает ответы для вопроса с данным индексом."""
    answers = []
    pattern = re.compile(
        rf"questionList\[{q_index}\]\.answers\[(\d+)\]\.checked"
    )
    answer_inputs = soup.find_all("input", attrs={"name": pattern})

    for a_input in answer_inputs:
        match = pattern.search(a_input["name"])
        if not match:
            continue
        a_index = int(match.group(1))
        answer_text = _extract_answer_text(a_input)
        answer_id = _find_answer_id_near(soup, q_index, a_index)
        answers.append({
            "id": answer_id,
            "index": a_index,
            "text": answer_text,
        })

    return answers


def _extract_answer_text(input_element) -> str:
    """Извлекает текст ответа рядом с input-элементом."""
    # Ищем label
    input_id = input_element.get("id", "")
    if input_id:
        label = input_element.find_parent().find("label", attrs={"for": input_id})
        if label:
            return label.get_text(strip=True)

    # Текст в label, оборачивающем input
    parent_label = input_element.find_parent("label")
    if parent_label:
        # Убираем текст самого input
        return parent_label.get_text(strip=True)

    # Следующий sibling
    sibling = input_element.find_next_sibling()
    if sibling:
        return sibling.get_text(strip=True)

    return ""


def _find_question_id_near(soup, q_index: int, near_element) -> int | None:
    """Ищет скрытое поле с ID вопроса."""
    hidden = soup.find(
        "input",
        attrs={"name": f"questionList[{q_index}].id"},
    )
    if hidden:
        return int(hidden["value"])
    return None


def _find_answer_id_near(soup, q_index: int, a_index: int) -> int | None:
    """Ищет скрытое поле с ID ответа."""
    hidden = soup.find(
        "input",
        attrs={"name": f"questionList[{q_index}].answers[{a_index}].id"},
    )
    if hidden:
        return int(hidden["value"])
    return None


def fetch_all_questions(
    session: requests.Session,
    test_id: int,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> list[dict]:
    """Загружает все вопросы постранично."""
    all_questions = []
    page = 0

    while True:
        url = f"{BASE_URL}/ticket/ordered/"
        params = {"testId": test_id, "page": page, "size": page_size}

        print(f"  Загрузка страницы {page}...")
        resp = session.get(url, params=params)
        resp.raise_for_status()

        questions = parse_questions_page(resp.text)
        if not questions:
            break

        all_questions.extend(questions)
        print(f"  Найдено вопросов на странице: {len(questions)}")

        # Если на странице меньше вопросов чем page_size — это последняя
        if len(questions) < page_size:
            break

        page += 1
        time.sleep(REQUEST_DELAY)

    return all_questions


def check_answer(
    session: requests.Session,
    test_id: int,
    csrf_token: str,
    question: dict,
    answer_index: int,
    page: int,
) -> dict:
    """
    Отправляет ответ на проверку и возвращает результат.

    Отправляем один вопрос с одним выбранным ответом.
    """
    url = f"{BASE_URL}/ticket/check"
    params = {
        "ordered": "true",
        "ticketNum": 1,
        "page": page,
    }

    form_data = {
        "_csrf": csrf_token,
        "testId": str(test_id),
        "errorsCount": "0",
        f"questionList[0].id": str(question["id"]),
        f"questionList[0].answers[{answer_index}].checked": "on",
    }

    # Добавляем ID ответов если есть
    for ans in question["answers"]:
        idx = ans["index"]
        if ans.get("id") is not None:
            form_data[f"questionList[0].answers[{idx}].id"] = str(ans["id"])

    resp = session.post(url, params=params, data=form_data)
    resp.raise_for_status()

    return _parse_check_response(resp.text, question, answer_index)


def _parse_check_response(
    html: str,
    question: dict,
    submitted_answer_index: int,
) -> dict:
    """
    Анализирует ответ сервера после проверки.

    Возвращает:
    {
        "correct": True/False,
        "correct_answer_index": int | None,
        "errors_count": int | None,
    }
    """
    soup = BeautifulSoup(html, "html.parser")

    result = {
        "correct": False,
        "correct_answer_index": None,
        "errors_count": None,
    }

    # Паттерн 1: ищем элемент с классом, указывающим на ошибку/успех
    error_el = soup.find(class_=re.compile(r"error|wrong|incorrect|danger", re.I))
    success_el = soup.find(class_=re.compile(r"success|correct|right", re.I))

    if success_el and not error_el:
        result["correct"] = True
        result["correct_answer_index"] = submitted_answer_index
        return result

    # Паттерн 2: ищем errorsCount в ответе
    errors_input = soup.find("input", attrs={"name": "errorsCount"})
    if errors_input:
        try:
            result["errors_count"] = int(errors_input["value"])
            if result["errors_count"] == 0:
                result["correct"] = True
                result["correct_answer_index"] = submitted_answer_index
                return result
        except (ValueError, KeyError):
            pass

    # Паттерн 3: Ищем подсветку правильного ответа
    for ans in question["answers"]:
        idx = ans["index"]
        name = f"questionList[0].answers[{idx}].checked"
        input_el = soup.find("input", attrs={"name": name})
        if input_el:
            parent = input_el.parent
            if parent:
                classes = " ".join(parent.get("class", []))
                if re.search(r"correct|right|success|green", classes, re.I):
                    result["correct_answer_index"] = idx
                    result["correct"] = (idx == submitted_answer_index)
                    return result

    # Паттерн 4: текстовый анализ — ищем "ошибок: 0" или подобное
    text = soup.get_text()
    err_match = re.search(r"ошиб\w*[:\s]*(\d+)", text, re.I)
    if err_match:
        errors = int(err_match.group(1))
        result["errors_count"] = errors
        if errors == 0:
            result["correct"] = True
            result["correct_answer_index"] = submitted_answer_index

    return result


def find_correct_answers(
    session: requests.Session,
    test_id: int,
    csrf_token: str,
    questions: list[dict],
    delay: float = REQUEST_DELAY,
) -> list[dict]:
    """
    Для каждого вопроса перебирает ответы и находит правильный.

    Возвращает список вопросов с добавленным полем correct_answer.
    """
    results = []

    for i, question in enumerate(questions):
        q_num = i + 1
        print(f"\n[{q_num}/{len(questions)}] {question['text'][:80]}...")

        correct_found = False
        for ans in question["answers"]:
            a_idx = ans["index"]
            print(f"  Проверяю вариант {a_idx}: {ans['text'][:60]}...", end=" ")

            # Может понадобиться обновить CSRF-токен
            try:
                check_result = check_answer(
                    session, test_id, csrf_token, question, a_idx, page=i,
                )
            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code == 403:
                    print("CSRF expired, обновляю токен...")
                    csrf_token = get_csrf_token(session, test_id)
                    check_result = check_answer(
                        session, test_id, csrf_token, question, a_idx, page=i,
                    )
                else:
                    raise

            if check_result["correct"]:
                print("✓ ПРАВИЛЬНО")
                question["correct_answer"] = ans
                correct_found = True
                break
            else:
                print("✗")

            time.sleep(delay)

        if not correct_found:
            print("  ⚠ Правильный ответ не определён")
            question["correct_answer"] = None

        results.append(question)
        time.sleep(delay)

    return results


def save_results(results: list[dict], output_file: str) -> None:
    """Сохраняет результаты в JSON-файл."""
    # Подготавливаем чистый вывод
    output = []
    for q in results:
        entry = {
            "id": q["id"],
            "question": q["text"],
            "answers": [
                {"index": a["index"], "text": a["text"]}
                for a in q["answers"]
            ],
        }
        if q.get("correct_answer"):
            entry["correct_answer"] = {
                "index": q["correct_answer"]["index"],
                "text": q["correct_answer"]["text"],
            }
        else:
            entry["correct_answer"] = None
        output.append(entry)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nРезультаты сохранены в {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Парсер тестов с prombez24.com"
    )
    parser.add_argument(
        "--test-id",
        type=int,
        default=DEFAULT_TEST_ID,
        help=f"ID теста (по умолчанию: {DEFAULT_TEST_ID})",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=DEFAULT_PAGE_SIZE,
        help=f"Размер страницы для загрузки вопросов (по умолчанию: {DEFAULT_PAGE_SIZE})",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=REQUEST_DELAY,
        help=f"Задержка между запросами в секундах (по умолчанию: {REQUEST_DELAY})",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="results.json",
        help="Выходной файл (по умолчанию: results.json)",
    )
    parser.add_argument(
        "--questions-only",
        action="store_true",
        help="Только загрузить вопросы без поиска правильных ответов",
    )
    args = parser.parse_args()

    print(f"=== Парсер тестов prombez24.com ===")
    print(f"Test ID: {args.test_id}")
    print()

    session = create_session()

    # 1. Получаем CSRF-токен
    print("Получение CSRF-токена...")
    csrf_token = get_csrf_token(session, args.test_id)
    print(f"CSRF-токен: {csrf_token[:16]}...")

    # 2. Загружаем все вопросы
    print("\nЗагрузка вопросов...")
    questions = fetch_all_questions(session, args.test_id, args.page_size)
    print(f"\nВсего вопросов: {len(questions)}")

    if not questions:
        print("Вопросы не найдены. Проверьте test_id.", file=sys.stderr)
        sys.exit(1)

    if args.questions_only:
        save_results(questions, args.output)
        return

    # 3. Находим правильные ответы
    print("\nПоиск правильных ответов...")
    results = find_correct_answers(
        session, args.test_id, csrf_token, questions, args.delay,
    )

    # 4. Сохраняем результаты
    save_results(results, args.output)

    # Статистика
    found = sum(1 for q in results if q.get("correct_answer"))
    print(f"\nНайдено правильных ответов: {found}/{len(results)}")


if __name__ == "__main__":
    main()
