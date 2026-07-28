# Avito Parser

E2E-клиент для последовательной обработки Avito firewallPow, QRATOR и
GeeTest. Все нужные Python-зависимости и локальная библиотека `GeekedTest`
входят в репозиторий.

## Быстрый запуск

Нужен установленный [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/mickberrad659-sketch/Avito-Parser.git
cd Avito-Parser
uv sync
uv run python main.py
```

`main.py` не использует `HTTP_PROXY`, `HTTPS_PROXY` и `ALL_PROXY` из
окружения: запросы выполняются через прямое соединение. Диагностический лог
пишется в `firewall-debug.log`, а полные тела защитных ответов сохраняются в
`firewall-debug-responses/` как `.json`, `.html` или `.txt` по фактическому
Content-Type; оба пути исключены из Git.

Проверка:

```bash
uv run --with pytest pytest -q
```

## JavaScript для цепочки firewallPow

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

Главный запрос — `GET /web/1/js/items` для `categoryId=98`,
`locationId=624840`. Все feature-параметры заданы константами в
`ITEMS_QUERY_PARAMETERS`, а `p` последовательно меняется от 1 до 100.
Каждый запрос содержит `X-Source: client-browser`. Challenge всегда берётся
из текущего ответа, а cookies ведёт одна внутренняя HTTP-сессия.

```bash
uv run python main.py
```

Cookies из `Set-Cookie` первого запроса и `/get` остаются в cookie jar сессии и
автоматически передаются на следующие запросы.

После успешной PoW-проверки либо ответа HTTP 200 скрипт в той же сессии делает
100 items-XHR: `p=1` … `p=100`. Для каждого сразу выводится HTTP-статус.
Из успешного JSON читаются верхнеуровневые `count`, `totalCount`,
`totalElements`, `mainCount`, `itemsOnPage`. В INFO рядом со статусом
выводятся `totalCount`, `itemsOnPage` и стабильный BLAKE2b-128 хеш полного
массива `catalog.items`; хеш подходит для быстрой проверки уникальности
страниц.
Между последовательными страницами выдерживается 0,05 секунды. При первом HTTP 403, 429 или 439
проход останавливается, ответ классифицируется и соответствующая защитная
ветка выполняется в той же сессии. После успешной PoW/Gee-проверки повторяется
тот же `p=N`, на котором появилась защита, и после его HTTP 200 цикл
продолжается с `p=N+1`. QRATOR также повторяет ровно исходный защищённый GET.

Body ответа читается целиком потоково. При обрыве выполняется до трёх попыток
с таймаутом 10 секунд. Если curl сообщает ошибку закрытия соединения уже после
полностью полученного HTML с `</html>`, сохранённый body принимается без
повторной загрузки. Proxy-переменные окружения намеренно игнорируются:
основной flow и вложенный GeeTest solver работают через прямое соединение.

При HTTP 302 с заголовком `Server: QRATOR` скрипт автоматически воспроизводит
cookie-цепочку из `302.har`:

1. Из HTML извлекает и загружает same-origin fingerprint JS.
2. Загружает `/favicon.ico`, чтобы получить/обновить cookie `v`, и выдерживает
   meta-refresh интервал из HAR до отметки в одну секунду.
3. Генерирует новый `f` из `base.txt`, а `s` — из неизменного `base-s.json`.
4. Сохраняет `f` в cookie jar и отправляет `f`/`s` как multipart form-data на
   `POST /web/2/ft`.
5. Оставляет серверные `Set-Cookie` в той же сессии и сохраняет JSON-строку
   ответа `/ft` в cookie `ft` вместе с кавычками, как это делает исходный JS.
6. Отправляет пиксель `GET /web/1/u?<number>`, где `number` вычисляется точно
   как `Math.floor(Math.random() * 4294967295)`, и сохраняет его `Set-Cookie`.
7. Ждёт две секунды, затем повторяет исходный items GET с тем же URL,
   `X-Source: client-browser` и остальными XHR-заголовками.

Успешными считаются HTTP 200 от обоих служебных endpoint'ов; иначе исходный
GET не повторяется, а причина записывается в диагностический лог. Число в
`/web/1/u?<number>` передаётся без знака `=`, как в HAR и исходном bundle.
Для HTTP/TLS используется Firefox-профиль `curl_cffi`, а явные заголовки
соответствуют Firefox 152 из HAR.

Если источник возвращает HTTP 200, проверка не требуется. При HTTP 429 скрипт
сначала проверяет JSON на `pow_challenge`. Captcha dispatcher может прийти как
HTTP 403, так и HTTP 429; оба варианта распознаются по
`X-Firewall-Show-Captcha: true` и ссылке
`ru.avito://1/firewall/captcha/show`. Dispatcher вызывает
`/web/5/firewallCaptcha/get` и классифицирует фактически выбранный тип.
`geeTest` запускается с captcha ID, извлечённым из Avito bundle; для
HTML-ветки остаётся проверка маркеров `#geetest_captcha`, `gt4.js`,
`initGeetest4` и `captchaId`.

Для GeeTest затем выполняется `/load`. Полный объект `data` передаётся уже
реализованному solver-у из `GeekedTest`; тот формирует `w`, отправляет GeeTest
`/verify`, а полученный `seccode` передаётся в Avito
`POST /web/3/firewallCaptcha/verify`. После `verified=true` исходный GET
повторяется в той же Avito-сессии.

Если GeeTest `/verify` отвечает `result=fail`, отклонённый `lot_number`
повторно не используется. Скрипт заново выполняет исходный items GET с тем же
`p=N`, получает свежую captcha-ветку и новый `/load`, затем запускает solver
с нуля. После пяти последовательных отказов работа прекращается; ошибка
содержит тип последней задачи, `lot_number`, `result` и серверный
`fail_count`.

Avito и вся GeeTest-цепочка (`/load`, изображения и `/verify`) используют одну
`curl_cffi.Session`, один cookie jar и один сетевой маршрут. GeeTest-запросы
повторяют Firefox-заголовки из HAR (`Referer: https://www.avito.ru/`,
`Sec-Fetch-Site: cross-site`), а `firewallCaptcha/get` и
`firewallCaptcha/verify` используют постоянный Referer страницы каталога.
Ответ Avito `verified=false` также считается неудачной Gee-попыткой и
перезапускает цепочку с исходного GET, максимум пять раз подряд.

Каждый captcha-flow автоматически сохраняет полные структурированные HTTP-
диагностики в `firewall-debug-responses/exchange-*.json`: method, URL,
заголовки и cookie jar до запроса, params/JSON payload, HTTP status,
заголовки, полное body и cookie jar после ответа. Артефакты создаются для защищённого page GET,
`firewallCaptcha/get`, GeeTest `/load`, GeeTest `/verify`,
`firewallCaptcha/verify` и первого повторного page GET. Файлы содержат
действующие cookies и captcha-токены, поэтому их нельзя публиковать; каталог
исключён из Git.

Живой E2E HTML- и JSON-dispatcher веток подтверждён 27–28 июля 2026 года:
свежие `firewallCaptcha/get` и GeeTest `/load` были решены локальным solver-ом,
после чего Avito принял `firewallCaptcha/verify` и вернул успешную
верификацию. Неизвестные или пока неподдерживаемые варианты сохраняются
целиком для диагностики.

HTTP 400 не считается защитной веткой: его полное тело сохраняется в
`firewall-debug-responses/page-p-N-http-400.*`, заголовки попадают в
`firewall-debug.log`, после чего цикл продолжает запрос со следующей страницы.

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
