# Матрица decoded Qrator `f`

Профилей: 8. Измерений на профиль: 2.

Классификация:

- constant_across_samples: 116;
- fingerprint_dependent: 24;
- changes_within_same_profile: 0;
- deterministic_time: 1.

Повторные страницы одного профиля разделены паузой более одной секунды.

## Основные выводы

- До XTEA поле `f` уже является числовым вектором из 141 позиции.
- Внутри одного Camoufox-профиля все значения, кроме индекса 128, были
  стабильны.
- Индекс 128 равен `floor(Date.now()/1000)` и менялся строго вместе со временем.
- Per-request случайных чисел среди 141 позиций в этой серии не обнаружено.
- Индекс 106 менялся для каждого нового профиля, но оставался стабильным на
  повторной странице: это profile-seeded canvas fingerprint/hash.
- Индекс 110 повторялся для одинаковых GPU renderer и менялся между Apple M1,
  Mac Intel, Windows Intel, NVIDIA и Microsoft Basic Renderer. Это
  WebGL/GPU renderer fingerprint/hash.
- Индексы 54–59, 61, 63–64, 68, 72, 78, 84, 92–93 и 97 разделили Windows и
  macOS на значения 0/1. Это OS-dependent feature/font/API flags; точные имена
  отдельных probes ещё не установлены.
- `navigator.hardwareConcurrency` хранится напрямую в индексе 45. Наблюдались
  значения 8, 10, 12, 16 и 32.
- `navigator.deviceMemory` в Firefox/Camoufox отсутствует (`null`); отдельного
  подтверждённого RAM-поля в этой ветке не найдено.
- UA строкой не хранится. UA участвует в составном 32-битном значении 108.
  Произвольное изменение UA в контролируемой пробе меняло этот индекс.
- `platform` и `languages` представлены 32-битными значениями 46 и 47.
- `s` не входит в эту матрицу: это отдельный читаемый JSON проверки расширений.

Все hash/fingerprint-поля представлены unsigned uint32, поэтому их полный
формальный диапазон — `0..4294967295`. Числовая близость двух hashes ничего не
означает.

Классификация `constant_across_samples` означает только константность в
исследованных профилях. Например, язык, timezone, extensions и audio setup во
всех автоматически созданных профилях были одинаковыми. Контрольные подмены
доказали, что индексы 4–23, 36, 43, 47, 108, 109, 111, 132 и 140 могут
изменяться при изменении соответствующего окружения.

| idx | назначение | класс | unique | min | max | значения |
|---:|---|---|---:|---:|---:|---|
| 0 | screen.width | fingerprint_dependent | 5 | 960 | 1920 | 960, 1512, 1600, 1680, 1920 |
| 1 | screen.height | fingerprint_dependent | 5 | 540 | 1080 | 540, 900, 982, 1050, 1080 |
| 2 | screen.colorDepth | fingerprint_dependent | 2 | 24 | 30 | 24, 30 |
| 3 | screen.pixelDepth | fingerprint_dependent | 2 | 24 | 30 | 24, 30 |
| 4 | timezone offset probe | constant_across_samples | 1 | 240 | 240 | 240 |
| 5 | timezone offset probe | constant_across_samples | 1 | 180 | 180 | 180 |
| 6 | timezone offset probe | constant_across_samples | 1 | 240 | 240 | 240 |
| 7 | timezone offset probe | constant_across_samples | 1 | 180 | 180 | 180 |
| 8 | timezone offset probe | constant_across_samples | 1 | 240 | 240 | 240 |
| 9 | timezone offset probe | constant_across_samples | 1 | 180 | 180 | 180 |
| 10 | timezone offset probe | constant_across_samples | 1 | 240 | 240 | 240 |
| 11 | timezone offset probe | constant_across_samples | 1 | 180 | 180 | 180 |
| 12 | timezone offset probe | constant_across_samples | 1 | 240 | 240 | 240 |
| 13 | timezone offset probe | constant_across_samples | 1 | 240 | 240 | 240 |
| 14 | timezone offset probe | constant_across_samples | 1 | 240 | 240 | 240 |
| 15 | timezone offset probe | constant_across_samples | 1 | 240 | 240 | 240 |
| 16 | timezone offset probe | constant_across_samples | 1 | 240 | 240 | 240 |
| 17 | timezone offset probe | constant_across_samples | 1 | 240 | 240 | 240 |
| 18 | timezone offset probe | constant_across_samples | 1 | 240 | 240 | 240 |
| 19 | timezone offset probe | constant_across_samples | 1 | 180 | 180 | 180 |
| 20 | timezone offset probe | constant_across_samples | 1 | 180 | 180 | 180 |
| 21 | timezone offset probe | constant_across_samples | 1 | 180 | 180 | 180 |
| 22 | timezone offset probe | constant_across_samples | 1 | 180 | 180 | 180 |
| 23 | timezone offset probe | constant_across_samples | 1 | 180 | 180 | 180 |
| 24 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 25 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 26 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 27 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 28 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 29 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 30 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 31 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 32 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 33 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 34 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 35 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 36 | WebSocket support flag | constant_across_samples | 1 | 1 | 1 | 1 |
| 37 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 38 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 39 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 40 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 41 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 42 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 43 | normalized navigator.doNotTrack | constant_across_samples | 1 | 1 | 1 | 1 |
| 44 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 45 | navigator.hardwareConcurrency | fingerprint_dependent | 5 | 8 | 32 | 8, 10, 12, 16, 32 |
| 46 | hash(navigator.platform) | fingerprint_dependent | 2 | 1005301203 | 3955448693 | 1005301203, 3955448693 |
| 47 | hash(navigator.languages) | constant_across_samples | 1 | 41002199 | 41002199 | 41002199 |
| 48 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 49 |  | constant_across_samples | 1 | 2 | 2 | 2 |
| 50 |  | constant_across_samples | 1 | 2 | 2 | 2 |
| 51 |  | constant_across_samples | 1 | 2 | 2 | 2 |
| 52 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 53 |  | constant_across_samples | 1 | 2 | 2 | 2 |
| 54 |  | fingerprint_dependent | 2 | 0 | 1 | 0, 1 |
| 55 |  | fingerprint_dependent | 2 | 0 | 1 | 0, 1 |
| 56 |  | fingerprint_dependent | 2 | 0 | 1 | 0, 1 |
| 57 |  | fingerprint_dependent | 2 | 0 | 1 | 0, 1 |
| 58 |  | fingerprint_dependent | 2 | 0 | 1 | 0, 1 |
| 59 |  | fingerprint_dependent | 2 | 0 | 1 | 0, 1 |
| 60 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 61 |  | fingerprint_dependent | 2 | 0 | 1 | 0, 1 |
| 62 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 63 |  | fingerprint_dependent | 2 | 0 | 1 | 0, 1 |
| 64 |  | fingerprint_dependent | 2 | 0 | 1 | 0, 1 |
| 65 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 66 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 67 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 68 |  | fingerprint_dependent | 2 | 0 | 1 | 0, 1 |
| 69 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 70 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 71 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 72 |  | fingerprint_dependent | 2 | 0 | 1 | 0, 1 |
| 73 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 74 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 75 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 76 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 77 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 78 |  | fingerprint_dependent | 2 | 0 | 1 | 0, 1 |
| 79 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 80 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 81 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 82 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 83 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 84 |  | fingerprint_dependent | 2 | 0 | 1 | 0, 1 |
| 85 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 86 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 87 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 88 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 89 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 90 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 91 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 92 |  | fingerprint_dependent | 2 | 0 | 1 | 0, 1 |
| 93 |  | fingerprint_dependent | 2 | 0 | 1 | 0, 1 |
| 94 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 95 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 96 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 97 |  | fingerprint_dependent | 2 | 0 | 1 | 0, 1 |
| 98 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 99 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 100 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 101 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 102 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 103 |  | constant_across_samples | 1 | 5 | 5 | 5 |
| 104 |  | constant_across_samples | 1 | 3641819743 | 3641819743 | 3641819743 |
| 105 |  | constant_across_samples | 1 | 3577560136 | 3577560136 | 3577560136 |
| 106 | canvas fingerprint/hash (profile-stable) | fingerprint_dependent | 8 | 109715837 | 3433461283 | 109715837, 295597827, 520769875, 772757374, 1065046482, 2930309092, 3111173713, 3433461283 |
| 107 |  | constant_across_samples | 1 | 3469306551 | 3469306551 | 3469306551 |
| 108 | composite navigator hash | constant_across_samples | 1 | 1582120644 | 1582120644 | 1582120644 |
| 109 | composite screen hash | constant_across_samples | 1 | 1320192270 | 1320192270 | 1320192270 |
| 110 | WebGL/GPU renderer fingerprint/hash | fingerprint_dependent | 5 | 1990741309 | 4189790824 | 1990741309, 2485359653, 4058090831, 4111105773, 4189790824 |
| 111 | navigator.maxTouchPoints | constant_across_samples | 1 | 0 | 0 | 0 |
| 112 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 113 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 114 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 115 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 116 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 117 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 118 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 119 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 120 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 121 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 122 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 123 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 124 |  | constant_across_samples | 1 | 2 | 2 | 2 |
| 125 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 126 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 127 |  | constant_across_samples | 1 | 1 | 1 | 1 |
| 128 | floor(Date.now()/1000) | deterministic_time | 16 | 1785172505 | 1785172534 | 1785172505, 1785172507, 1785172509, 1785172511, 1785172512, 1785172515, 1785172516, 1785172518, … |
| 129 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 130 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 131 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 132 | navigator.webdriver | constant_across_samples | 1 | 0 | 0 | 0 |
| 133 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 134 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 135 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 136 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 137 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 138 |  | constant_across_samples | 1 | 0 | 0 | 0 |
| 139 |  | constant_across_samples | 1 | 3517267889 | 3517267889 | 3517267889 |
| 140 | audio fingerprint/hash | constant_across_samples | 1 | 3369925510 | 3369925510 | 3369925510 |

## Профили

Полные UA, platform, languages, screen, CPU, touch, timezone и WebGL metadata для каждого измерения находятся в JSON:

`qrator-fingerprint-matrix.json`
