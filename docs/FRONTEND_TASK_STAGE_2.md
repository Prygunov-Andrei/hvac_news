# Задание для Фронтенд-разработчика (Этап 2: Справочники и Мультиязычность)

**Цель этапа:** Реализовать публичные разделы "Производители", "Бренды" и "Ресурсы" с поддержкой переключения языков.

**Важно:** Данные разделы доступны **без авторизации**.

## 1. Переключение языков (Language Switcher)
В шапке сайта необходимо реализовать переключатель языков: **RU | EN | DE | PT**.
По умолчанию выбранный язык сохраняется (в localStorage или cookie).

При запросе к API, текущий язык интерфейса должен отправляться в заголовке:
`Accept-Language: en` (или ru, de, pt).
*Примечание: На данный момент API возвращает все поля переводов (`name_ru`, `name_en`...), но для корректной работы Django (форматирование дат, чисел) этот заголовок полезен.*

В ответе API вы получите поля вида:
*   `description` (текущий язык сервера или дефолтный)
*   `description_ru`
*   `description_en`
*   `description_de`
*   `description_pt`

**Логика фронтенда:** Вы можете либо отображать поле `description` (если доверяете `Accept-Language`), либо явно брать поле `description_{lang}` в зависимости от выбранного языка в UI.

## 2. Раздел "Производители" (Manufacturers)
**URL:** `/manufacturers`
**API:** `GET /api/references/manufacturers/`

**Отображение:**
*   Таблица или список карточек.
*   Группировка по полю `region` (если заполнено).
*   Столбцы: Название, Регион, Ссылки (website_1...3), Описание.
*   При клике на производителя можно раскрыть список его брендов (нужно будет фильтровать API брендов или получить их вложенными, пока API отдает только список).

## 3. Раздел "Бренды" (Brands)
**URL:** `/brands`
**API:** `GET /api/references/brands/`

**Отображение:**
*   Сетка (Grid) с логотипами.
*   Карточка бренда: Лого, Название, Ссылка на Производителя (текстом), Описание.
*   Сортировка по алфавиту.

## 4. Раздел "Полезные ресурсы" (Resources)
**URL:** `/resources`
**API:** `GET /api/references/resources/`

**Отображение:**
*   Простой список или плитка.
*   Логотип, Название, Описание, Кнопка "Перейти" (ссылка на `url`).

---

## API Specification (v1)

Base URL: `https://<your-ngrok-url>/api/references`

### 1. Manufacturers
`GET /manufacturers/`
```json
[
  {
    "id": 1,
    "name": "Daikin",
    "region": "Japan",
    "website_1": "https://daikin.com",
    "description_ru": "Описание на русском",
    "description_en": "Description in English",
    ...
  }
]
```

### 2. Brands
`GET /brands/`
```json
[
  {
    "id": 1,
    "manufacturer": 1,
    "manufacturer_name": "Daikin",
    "name": "Daikin Comfort",
    "logo": "http://.../media/brands/logos/logo.png",
    "description_ru": "...",
    ...
  }
]
```

### 3. News Resources
`GET /resources/`
```json
[
  {
    "id": 1,
    "name": "ASHRAE",
    "url": "https://ashrae.org",
    "logo": "...",
    "description_ru": "..."
  }
]
```

