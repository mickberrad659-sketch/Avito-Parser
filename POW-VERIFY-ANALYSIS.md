# Разбор формирования payload для `firewallPow/verify`

## Вывод

Да, это proof-of-work (PoW). Поле `challenge` в запросе `verify` — это **не** исходный `pow_challenge`. Это полный `challenge_jwt`, полученный от `/web/3/firewallPow/get`, переданный обратно без изменения. По данным внутри JWT браузер вычисляет и добавляет второе поле — `nonce`.

```text
HTTP 439 с pow_challenge
          |
          v
POST /firewallPow/get  { challenge: pow_challenge }
          |
          v
challenge_jwt  -- без изменений --> verify.challenge
          |
          +-- decode JWT payload --> id, compl
                                      |
                                      v
                           подобрать nonce для SHA-256(id + ":" + nonce)
                                      |
                                      v
POST /firewallPow/verify { challenge: challenge_jwt, nonce }
```

## Источник данных

Разбор выполнен по HAR-записям № 495, 501 и 504 и по исходному минифицированному бандлу [`bootstrap.05ecc62c6d849fae.js`](./bootstrap.05ecc62c6d849fae.js). Значения одноразовых `challenge` и JWT в примерах ниже намеренно сокращены: их не следует считать постоянными или повторно используемыми.

## 1. Откуда берётся исходный `challenge`

Непосредственно перед PoW браузер сделал обычный запрос данных:

```text
GET /web/1/js/items?... → HTTP 439
```

Тело ответа 439:

```json
{
  "pow_challenge": "CVeayI9S…1mPg"
}
```

Это непрозрачная строка, выданная сервером. Бандл не декодирует и не преобразует её. Она лишь подставляется как есть в запрос `get`:

```http
POST /web/3/firewallPow/get
Content-Type: application/json

{"challenge":"CVeayI9S…1mPg"}
```

## 2. Что приходит от `get`

В HAR ответ выглядит так:

```json
{
  "success": {
    "result": {
      "challenge_jwt": "eyJ…ITQE",
      "max_solution_time_sec": 60
    },
    "status": "ok"
  }
}
```

Код извлекает только `success.result.challenge_jwt`; если поля нет, выбрасывает ошибку `no challenge_jwt`.

`max_solution_time_sec` присутствует в ответе, но в найденной реализации компонента не используется при вычислении или построении запроса `verify`.

## 3. Как используется `challenge_jwt`

JWT имеет обычную трёхчастную форму `header.payload.signature`.

В браузере бандл:

1. разбивает строку по `.`;
2. берёт вторую часть — `payload`;
3. выполняет base64url-декодирование (`-` → `+`, `_` → `/`, затем добавляет `=`);
4. разбирает JSON;
5. проверяет только типы `id` (строка) и `compl` (число).

Для записанного случая JWT payload декодируется в:

```json
{
  "compl": 4,
  "id": "b360b677-17c2-840d-5758-60e59982ded8",
  "iat": 1785158950,
  "nbf": 1785158950,
  "exp": 1785159250,
  "iss": "firewall-captcha",
  "unblock_ttl_sec": 420,
  "v": 1
}
```

На стороне клиента подпись JWT не верифицируется. Это ожидаемо для PoW: клиенту нужно прочитать параметры задания, а сервер при `verify` сам проверяет подпись переданного JWT и найденный nonce. В payload `verify` передаётся оригинальная строка JWT целиком, включая header и signature, а не декодированный JSON и не один `id`.

## 4. Как вычисляется `nonce`

Формула, реализованная в бандле:

```text
digest = SHA-256(UTF-8(`${id}:${nonce}`))
условие: digest в hex начинается с "0".repeat(compl)
```

`nonce` начинается с `0` и увеличивается на `1`, пока условие не станет истинным. Каждые 10 000 попыток код уступает управление через `setTimeout(..., 0)`, чтобы не надолго блокировать интерфейс. Для хеширования используется Web Crypto API:

```js
crypto.subtle.digest("SHA-256", new TextEncoder().encode(`${id}:${nonce}`))
```

В HAR:

```text
id       = b360b677-17c2-840d-5758-60e59982ded8
compl    = 4
nonce    = 233984
SHA-256  = 0000e0688a48e686465f27728d21a517b36490e79f258809a47a9220165f79c6
```

Первые четыре шестнадцатеричных символа хеша — `0000`, поэтому `nonce = 233984` удовлетворяет сложности `4`.

## 5. Итоговый payload `verify`

После расчёта браузер создаёт именно такой объект:

```json
{
  "challenge": "<полный challenge_jwt из ответа get, без изменений>",
  "nonce": 233984
}
```

и отправляет его как JSON:

```http
POST /web/3/firewallPow/verify
Content-Type: application/json

{"challenge":"eyJ…ITQE","nonce":233984}
```

Важное соответствие полей:

| Источник | Поле / действие | Результат |
|---|---|---|
| ответ HTTP 439 | `pow_challenge` | без изменений → `get.challenge` |
| ответ `get` | `challenge_jwt` | без изменений → `verify.challenge` |
| JWT payload | `id`, `compl` | используются только для поиска `nonce` |
| локальное вычисление | подходящий `nonce` | → `verify.nonce` |

## 6. Проверка результата

Ответ `verify` в HAR:

```json
{
  "success": {
    "result": {
      "unblock_ttl": 420,
      "verified": true
    },
    "status": "ok"
  }
}
```

Код приводит `success.result.verified` к boolean. Только `true` считается успешным прохождением: выставляется сообщение «Проверка пройдена» и вызывается переданный компоненту callback `onSuccess`.

В обоих ответах (`get` и `verify`) сервер также передал `Set-Cookie` для HttpOnly cookie `v` с областью `.avito.ru`. JavaScript не может прочитать такую cookie, но браузер сохранит её; это, вероятно, часть серверного состояния разблокировки. Сам компонент не использует `unblock_ttl` напрямую.

## 7. Ошибки и повторы в клиентском коде

- Сетевые запросы `get` и `verify` получают `AbortSignal.timeout(5000)` по умолчанию: это 5 секунд на один HTTP-запрос, а не лимит всего PoW.
- При исключении компонент повторяет полный цикл `get → расчёт → verify` до 3 раз.
- Пауза между повторениями — 1 секунда.
- Если `verified` не истинно, это считается ошибкой `not verified` и запускает повтор.

## Мини-псевдокод

```text
powChallenge = response_439.pow_challenge
jwt = POST /firewallPow/get { challenge: powChallenge }
       .success.result.challenge_jwt

{ id, compl } = decodeBase64Url(jwt.split('.')[1])
nonce = 0
while hex(SHA256(id + ':' + nonce)) does not start with '0' repeated compl:
    nonce += 1

result = POST /firewallPow/verify {
    challenge: jwt,
    nonce: nonce
}

success = Boolean(result.success?.result?.verified)
```

