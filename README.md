# JavaScript для цепочки firewallPow

Источник: `/home/al/Загрузки/MY SITE Archive [26-07-27 16-30-23].har` (HAR-запись № 19).

## Файл

- `bootstrap.05ecc62c6d849fae.js` — исходный (минифицированный) JavaScript-бандл, извлечённый непосредственно из HAR. В нём определены оба вызова:
  - `POST /web/3/firewallPow/get` с JSON `{"challenge": ...}`;
  - `POST /web/3/firewallPow/verify` с JSON `{"challenge": challenge_jwt, "nonce": ...}`.

## E2E: `get` → `verify`

`main.py` получает свежий `pow_challenge` из HTTP 439, затем выполняет
`POST /get` и `POST /verify`. JWT из ответа первого PoW-запроса передаётся в
уже реализованную `build_verify_payload()` из
`firewallpow_payload_reference.py`; она возвращает оригинальный JWT и
найденный для него `nonce`.

URL источника challenge и `Referer` — константы из HAR. Значения из HAR не
используются: challenge берётся из текущего ответа, а cookies ведёт одна
внутренняя HTTP-сессия.

```bash
python3 main.py
```

Cookies из `Set-Cookie` первого запроса и `/get` остаются в cookie jar сессии и
автоматически передаются на следующие запросы.

После успешной PoW-проверки либо ответа HTTP 200 скрипт в той же сессии делает
10 запросов страницы: `p=1` … `p=10`. Для каждого выводится HTTP-статус — это
позволяет сразу увидеть, на какой странице сработала следующая защитная ветка.
При HTTP 429 или 439 проход останавливается, ответ классифицируется снова как
GeeTest или PoW и после успешного PoW начинается новый проход. HTTP 403 не
обрабатывается вслепую: его content type и body (до 12 000 символов) пишутся в
консоль и `firewall-debug.log`.

При HTTP 302 с заголовком `Server: QRATOR` скрипт автоматически воспроизводит
cookie-цепочку из `302.har`:

1. Генерирует новый `f` из `base.txt`, а `s` — из неизменного `base-s.json`.
2. Сохраняет `f` в cookie jar и отправляет `f`/`s` как multipart form-data на
   `POST /web/2/ft`.
3. Оставляет серверные `Set-Cookie` в той же сессии и сохраняет JSON-строку
   ответа `/ft` в cookie `ft` вместе с кавычками, как это делает исходный JS.
4. Отправляет пиксель `GET /web/1/u?<number>`, где `number` вычисляется точно
   как `Math.floor(Math.random() * 4294967295)`, и сохраняет его `Set-Cookie`.
5. Повторяет исходный GET с тем же URL и document-заголовками, включая
   константный `Referer`.

Успешными считаются HTTP 200 от обоих служебных endpoint'ов; иначе исходный
GET не повторяется, а причина записывается в диагностический лог. Число в
`/web/1/u?<number>` передаётся без знака `=`, как в HAR и исходном bundle.

Если источник возвращает HTTP 200, проверка не требуется. При HTTP 429 скрипт
сначала проверяет HTML на маркеры именно GeeTest (`#geetest_captcha`,
`gt4.js`, `initGeetest4` и `captchaId`). Только после этого выполняется ветка
из дополнительного HAR: `/web/5/firewallCaptcha/get`, затем GeeTest `/load`.
Полученная задача требует интерактивного решения GeeTest; этот скрипт не
эмулирует её финальную проверку.

## Что обрабатывает код

1. Из ответа `get` получает `success.result.challenge_jwt`.
2. Декодирует JWT payload и читает `id` и `compl`.
3. Подбирает `nonce`, для которого SHA-256 от строки `id:nonce` начинается с `compl` нулей.
4. Из ответа `verify` читает `success.result.verified` и вызывает обработчик успеха только если значение истинно.

Это единственный JavaScript-ресурс в данном HAR, содержащий оба точных пути. Отдельного файла для каждого endpoint’а в архиве нет.

## Qrator `f` / `s`

Разбор формирования fingerprint-полей, сохранённого raw-текста и границы
обратного декодирования вынесены в
[`QRATOR-FINGERPRINT-ANALYSIS.md`](./QRATOR-FINGERPRINT-ANALYSIS.md).

### Генерация вариантов из decoded base

```bash
python generate_qrator_variants.py \
  --count 1000 \
  --output variants.ndjson
```

Каждая строка NDJSON содержит `f`, статичный `s`, выбранный `canvasHash` и
timestamp. Генератор:

- читает 141-компонентную основу из `base.txt`;
- ставит текущий Unix timestamp в индекс 128;
- генерирует уникальный unsigned 32-bit canvas hash для индекса 106;
- выполняет точный XTEA encode;
- один раз кодирует неизменный `base-s.json`.

Для воспроизводимой тестовой последовательности можно передать `--seed`.
Поля CPU, screen, platform и GPU независимо не перемешиваются: они связаны с
составными fingerprint hashes, и их произвольная комбинация создаёт
противоречивый профиль.
