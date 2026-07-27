# Анализ полей `f` и `s` Qrator

## Итог

Поля `f` и `s` в `POST /web/2/ft` — не хеши. Это обратимо
зашифрованный payload:

```text
raw text
  → упаковка JavaScript charCodeAt в 32-битные little-endian слова
  → XTEA, 32 раунда, блок 64 бита, без IV
  → ciphertext bytes в hex
```

Для `f` перед ciphertext добавляется версия `5.`. Для `s` префикса нет.

Python-реализация, не требующая браузера:

```text
qrator_payload_codec.py
```

Она подтверждена полным round-trip:

```text
encode(decode(f)) == f
encode(decode(s)) == s
```

Равенство выполнено:

- для payload, созданного исходным bundle в `jsdom`;
- для payload исходного HAR;
- для payload из настоящего Camoufox runtime.

В Camoufox bundle обходит подменённые `Array.join`, `JSON.stringify`,
`Function` и `eval`, получая чистые intrinsics через защитную ветку. Поэтому
прямой JavaScript-hook этой ветки не дал значения. Plaintext всё равно
восстановлен точно, а не предположительно: повторное шифрование каждого
восстановленного байта даёт исходный ciphertext целиком. Для детерминированного
XTEA с известным ключом это подтверждает, что сохранённый текст является
непосредственным входом до encode.

## Ключ и параметры

Четыре 32-битных слова ключа:

```python
KEY = (
    1901231474,  # 0x71527d72
    1081891380,  # 0x407c5a34
    1433695566,  # 0x5574754e
    978402641,   # 0x3a513d51
)
```

В little-endian ASCII это:

```text
r}Rq4Z|@NutUQ=Q:
```

Параметры:

- алгоритм: XTEA;
- размер блока: 8 байт;
- количество раундов: 32;
- delta: `0x9e3779b9`;
- порядок байтов: little-endian;
- режим: независимое шифрование каждого блока, фактически ECB;
- IV/nonce отсутствует;
- последний неполный блок дополняется нулевыми значениями;
- каждый 8-байтовый ciphertext-блок записывается как 16 hex-символов.

Формула шифрования одного блока:

```python
total = 0
for _ in range(32):
    left += (
        (((right << 4) ^ (right >> 5)) + right)
        ^ (total + key[total & 3])
    )
    total += 0x9e3779b9
    right += (
        (((left << 4) ^ (left >> 5)) + left)
        ^ (total + key[(total >> 11) & 3])
    )
```

Все операции выполняются в `uint32`.

## Что находится в `f`

После удаления `5.` и XTEA-decode получается одна строка из 141 значения,
разделённых `;`.

Пример начала raw из исходного Firefox HAR:

```text
1920;1080;24;24;240;180;240;180;...
```

Назначение части индексов подтверждено дифференциальными Camoufox-пробами:

| Индекс | Содержимое |
|---:|---|
| 0 | `screen.width` |
| 1 | `screen.height` |
| 2 | `screen.colorDepth` |
| 3 | `screen.pixelDepth` |
| 4–23 | `Date.getTimezoneOffset()` для набора дат, включая DST |
| 36 | наличие `WebSocket` |
| 43 | нормализованный `navigator.doNotTrack` |
| 45 | `navigator.hardwareConcurrency` |
| 46 | 32-битный fingerprint/hash `navigator.platform` |
| 47 | 32-битный fingerprint/hash `navigator.languages` |
| 106 | canvas fingerprint/hash, стабильный внутри одного профиля |
| 108 | составной hash набора свойств `navigator` |
| 109 | составной hash объекта `screen` |
| 110 | WebGL/GPU renderer fingerprint/hash |
| 111 | `navigator.maxTouchPoints` |
| 128 | Unix timestamp в секундах |
| 132 | `navigator.webdriver` |
| 140 | audio fingerprint/hash либо sentinel `3`, если AudioContext недоступен |

Составной индекс 108 подтверждён изменениями `userAgent`, `platform`,
`languages`, `hardwareConcurrency`, `maxTouchPoints`, `cookieEnabled`,
`doNotTrack` и `webdriver`. Индекс 109 меняется при изменении основных и
доступных размеров/глубины `screen`.

Результаты всех контрольных запусков находятся в:

```text
qrator-camoufox-field-probes.json
```

Воспроизведение:

```bash
/usr/bin/python probe_qrator_fields_camoufox.py
```

Остальные позиции — результаты дополнительных browser/environment probes:
наличие и поведение Web API, feature flags и внутренние 32-битные
fingerprint-значения. Они сохранены полностью, но ещё не всем присвоено
семантическое имя.

Полная строка исходного HAR:

```text
qrator-har-raw-f.txt
```

Полная строка Camoufox runtime:

```text
qrator-camoufox-raw-f.txt
```

Camoufox-вариант содержит 434 символа; исходный HAR — 436 символов. В обоих
случаях количество компонентов равно 141.

Важно: XTEA-оболочка `f` полностью обратима, однако некоторые компоненты внутри
raw уже представлены как 32-битные fingerprint/hash-значения. Расшифрование
`f` восстанавливает именно текст, поданный в XTEA, но не обязательно исходные
canvas/WebGL/API-данные, из которых ранее были рассчитаны отдельные числа.

## Что находится в `s`

После XTEA-decode получается JSON проверки расширений и ограничений окружения.

Исходный Firefox HAR:

```json
{
  "monospace": false,
  "readOnly": false,
  "noLengthPlugins": false,
  "installedExtensions": []
}
```

Camoufox runtime:

```json
{
  "monospace": true,
  "readOnly": false,
  "noLengthPlugins": false,
  "installedExtensions": []
}
```

Таким образом:

- `f` — основной числовой browser fingerprint;
- `s` — отдельный JSON результата extension/plugin environment probes;
- оба поля используют одинаковый ключ и одинаковую XTEA-функцию;
- `s` не является подписью или хешем `f`.

Сырые JSON сохранены в:

```text
qrator-har-raw-s.json
qrator-camoufox-raw-s.json
```

## Почему длина меняется

Длина ciphertext определяется длиной raw:

```python
hex_length = ceil(raw_js_code_units / 8) * 16
```

Для исходного HAR:

- `f`: 436 символов raw → 55 блоков → 880 hex-символов плюс `5.`;
- `s`: 85 символов raw → 11 блоков → 176 hex-символов.

Для Camoufox:

- `f`: 434 символа raw → те же 55 блоков;
- `s`: 84 символа raw → те же 11 блоков.

Повторяющиеся ciphertext-блоки объясняются ECB-подобной обработкой: одинаковые
8-символьные блоки plaintext с одинаковым ключом дают одинаковый ciphertext.

## Локальный encode/decode

Decode:

```bash
python qrator_payload_codec.py decode f '5.<hex>'
python qrator_payload_codec.py decode s '<hex>'
```

Encode:

```bash
python qrator_payload_codec.py encode f '<raw;browser;vector>'
python qrator_payload_codec.py encode s \
  '{"monospace":false,"readOnly":false,"noLengthPlugins":false,"installedExtensions":[]}'
```

Использование как модуля:

```python
from qrator_payload_codec import decode_field, encode_field

raw_f = decode_field(f_value, "f")
assert encode_field(raw_f, "f") == f_value

raw_s = decode_field(s_value, "s")
assert encode_field(raw_s, "s") == s_value
```

## Извлечение из HAR

```bash
python extract_qrator_ft_from_har.py \
  '/home/al/Загрузки/gee прошли и дальше идет наша 302.har'
```

Скрипт:

1. находит `POST /web/2/ft`;
2. извлекает multipart-поля `f` и `s`;
3. расшифровывает оба поля;
4. сохраняет raw;
5. выполняет обратный encode и сообщает результат полного сравнения.

Для исследованного HAR:

```text
f round-trip=True
s round-trip=True
```

## Получение Camoufox-базы

```bash
/usr/bin/python trace_qrator_camoufox.py
```

Скрипт запускает исходный bundle в Camoufox, локально перехватывает
`/web/2/ft`, расшифровывает перехваченные `f/s` и сохраняет:

```text
qrator-camoufox-trace.json
qrator-camoufox-raw-f.txt
qrator-camoufox-raw-s.json
```

В последнем проверенном запуске:

```text
Offline encode round-trip: f=True, s=True
```

## Граница обратимости

XTEA обратима, поэтому ciphertext `f/s` можно восстановить до непосредственно
зашифрованного текста.

Есть две неоднозначности:

1. нулевой padding не хранит исходную длину, поэтому настоящий завершающий
   `NUL` невозможно отличить от padding;
2. bundle упаковывает JavaScript UTF-16 code units операциями `charCodeAt` и
   32-битными сдвигами. Для наблюдаемого ASCII payload преобразование полностью
   обратимо. Для code units выше `0xff` эта предварительная упаковка не
   инъективна и может терять информацию.

Все фактически перехваченные `f/s` содержат ASCII и декодируются без потерь.

Реализация MurmurHash3, найденная в bundle, не является XTEA-оболочкой
`f/s`. Её перехваченные вызовы с `"1"`, `"2"` и `"4"` относятся к
антианалитическому/контрольному коду. Она не мешает обратному decode полей.
