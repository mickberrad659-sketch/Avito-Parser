# GeeTest `/load`: происхождение параметров и ответ

Источник: `/home/al/Загрузки/доп проверка.har`, анализ выполнен офлайн по HAR. Внешний запрос не выполнялся.

## Итог

Запрос `/load` запускает библиотека GeeTest, подгруженная из HTML страницы блокировки. Параметры имеют разные источники:

| Параметр | Значение в HAR | Откуда берётся |
|---|---|---|
| `captcha_id` | `2d9c743cf7d63dbc9db578a608196bcd` | Явно задан в inline-скрипте HTML: `const captchaId = '…'`; передаётся в `initGeetest4({ captchaId, product: 'bind', language: 'rus' }, ...)`. |
| `challenge` | UUID v4 вида `e7e13b94-…` | Генерирует `gt4.js`. В библиотеке используется `config.challenge || uuid()`. В конфигурации страницы `challenge` не передан, поэтому вызывается локальная `uuid()` на основе `Math.random()`. |
| `callback` | `geetest_1785159864813` | Генерирует `gt4.js` для JSONP. Формула: `geetest_` + `(parseInt(Math.random() * 10000) + Date.now())`. Каждая попытка и fallback-домен имеют своё значение. |
| `client_type` | `web` | В `gt4.js`: явный `config.clientType`, иначе `h5` для mobile User-Agent и `web` для desktop. В этой записи определён desktop-вариант. |
| `lang` | `rus` | Inline-страница передаёт `language: 'rus'` в `initGeetest4`. |

Таким образом, `captcha_id` приходит из HTML первого запроса. `challenge` **не** приходит из HTML или Avito API: в данном сценарии его создаёт сам загруженный GeeTest-клиент. `callback` тоже локально генерируется клиентом; он нужен только для обёртки JSONP-ответа.

## Запрос и ответ

Первый домен `gcaptcha4.geetest.com` не ответил в записи, поэтому библиотека автоматически повторила тот же `/load` на fallback-домене `gcaptcha4.geevisit.com`. Успешный ответ — JSONP, а не чистый JSON:

```js
geetest_1785159864813({"status":"success","data":{ ... }})
```

Нужные для дальнейшего протокола поля находятся здесь:

```text
response.data.payload
response.data.payload_protocol
```

Дополнительно ответ содержит `lot_number`, `process_token`, тип капчи, адреса изображений и `pow_detail`. В данной записи `pow_detail` имеет `bits: 0`, поэтому в ответе `/load` нет вычислительной PoW-сложности; дальнейший объёмный `w` в запросе `/verify` формируется библиотекой GeeTest после прохождения интерактивной проверки и сбора клиентских сигналов.

## Сохранённые данные

Точная извлечённая структура, включая `payload` и `payload_protocol`, сохранена в [`geetest_load_response.json`](./geetest_load_response.json). Одноразовые значения из HAR уже истекли и пригодны только для анализа формата.

Для следующих HAR используйте офлайн-парсер [`extract_geetest_load_from_har.py`](./extract_geetest_load_from_har.py): он найдёт успешный `/load`, снимет JSONP-обёртку и сохранит нужные поля в JSON-файл.

