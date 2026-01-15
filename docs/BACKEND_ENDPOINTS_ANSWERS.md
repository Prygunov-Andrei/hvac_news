# Ответы на вопросы фронтенда по эндпоинтам

## 🔴 Эндпоинт информации о последнем поиске

**Эндпоинт:** `GET /admin/references/newsresource/discover-news-info/`

### ✅ Ответы на вопросы:

1. **Этот эндпоинт вообще существует в Django?**
   - ✅ **ДА**, эндпоинт реализован в `references/admin.py`, метод `discover_news_info()`
   - URL: `/admin/references/newsresource/discover-news-info/`

2. **Какая именно ошибка возникает на бэкенде (traceback)?**
   - Потенциальная проблема была в обработке `last_run.last_search_date` если он `None`
   - **ИСПРАВЛЕНО:** Добавлена проверка `if last_run and last_run.last_search_date`
   - Теперь эндпоинт корректно обрабатывает случай, когда еще не было поисков

3. **Требуется ли аутентификация администратора?**
   - ✅ **ДА**, требуется аутентификация через JWT или сессию
   - Требуются права администратора (`user.is_staff == True`)
   - При отсутствии аутентификации возвращает `401 Unauthorized`
   - При отсутствии прав администратора возвращает `403 Forbidden`

4. **Может ли эндпоинт возвращать 500 если еще не было ни одного поиска?**
   - ❌ **НЕТ**, после исправления эндпоинт корректно обрабатывает этот случай
   - Если нет `NewsDiscoveryStatus` - `last_discovery_date` будет `None`
   - Если нет `NewsDiscoveryRun` - `period_start` будет `None`
   - Все поля корректно обрабатываются

### Формат ответа:

```json
{
  "last_discovery_date": "2025-01-15T12:00:00Z" | null,
  "period_start": "2025-01-15T00:00:00Z" | null,
  "period_end": "2025-01-15T23:59:59Z",
  "total_resources": 220
}
```

**Примечание:** Все даты в формате ISO 8601 (UTC).

---

## ⚠️ Эндпоинт списка провайдеров

**Эндпоинт:** `GET /api/references/resources/available_providers/`

### ✅ Ответы на вопросы:

1. **Этот эндпоинт реализован в Django?**
   - ✅ **ДА**, эндпоинт реализован в `references/views.py`
   - Метод: `available_providers()` в `NewsResourceViewSet`
   - URL: `/api/references/resources/available_providers/`

2. **Требуется ли аутентификация?**
   - ❌ **НЕТ**, аутентификация не требуется
   - Эндпоинт доступен для всех (`permissions.AllowAny()`)
   - Можно вызывать без токена

3. **Как определяется available - проверяются ли реальные API ключи?**
   - ✅ **ДА**, проверяются реальные API ключи из настроек Django
   - `grok` - проверяется `settings.XAI_API_KEY` (не пустой)
   - `anthropic` - проверяется `settings.ANTHROPIC_API_KEY` (не пустой)
   - `openai` - проверяется `settings.TRANSLATION_API_KEY` (не пустой)
   - `auto` - всегда доступен (`available: true`)

### Формат ответа:

```json
{
  "providers": [
    {
      "id": "auto",
      "name": "Автоматический выбор (цепочка)",
      "description": "Использует цепочку: Grok → Anthropic → OpenAI",
      "available": true
    },
    {
      "id": "grok",
      "name": "Grok 4.1 Fast",
      "description": "Самый экономичный вариант (~$0.13 за 220 ресурсов)",
      "available": true
    },
    {
      "id": "anthropic",
      "name": "Anthropic Claude Haiku 4.5",
      "description": "Экономичный вариант от Anthropic (~$4.26 за 220 ресурсов)",
      "available": true
    },
    {
      "id": "openai",
      "name": "OpenAI GPT-5.2",
      "description": "Резервный вариант (~$6.35 за 220 ресурсов)",
      "available": true
    }
  ],
  "default": "auto"
}
```

---

## 📋 Эндпоинт запуска поиска с провайдером

**Эндпоинт:** `POST /admin/references/newsresource/discover-news/`

### ✅ Ответы на вопросы:

1. **Принимает ли этот эндпоинт параметр provider?**
   - ✅ **ДА**, параметр `provider` принимается через POST запрос
   - Параметр читается из `request.POST.get('provider', 'auto')`

2. **Какой формат тела запроса ожидается - FormData или JSON?**
   - ✅ **FormData** (application/x-www-form-urlencoded)
   - Эндпоинт использует `request.POST.get()`, что работает с FormData
   - Для JSON нужно было бы использовать `request.data.get()`

3. **Если provider не передан, используется ли auto по умолчанию?**
   - ✅ **ДА**, если `provider` не передан, используется `'auto'` по умолчанию
   - Код: `provider = request.POST.get('provider', 'auto')`

4. **Валидируется ли значение provider?**
   - ✅ **ДА**, значение валидируется
   - Допустимые значения: `'auto'`, `'grok'`, `'anthropic'`, `'openai'`
   - Если передано недопустимое значение - автоматически устанавливается `'auto'`
   - Код: 
     ```python
     if provider not in ['auto', 'grok', 'anthropic', 'openai']:
         provider = 'auto'
     ```

### Формат запроса:

**Правильный вариант (FormData):**
```javascript
const formData = new FormData();
formData.append('provider', 'grok');

fetch('/admin/references/newsresource/discover-news/', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'X-Requested-With': 'XMLHttpRequest'
  },
  body: formData
})
```

**Неправильный вариант (JSON) - НЕ РАБОТАЕТ:**
```javascript
// ❌ Это НЕ будет работать
fetch('/admin/references/newsresource/discover-news/', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({ provider: 'grok' })
})
```

### Формат ответа (AJAX):

```json
{
  "status": "running",
  "processed": 0,
  "total": 220,
  "percent": 0
}
```

---

## 📝 Дополнительные эндпоинты

### Запуск поиска по одному источнику (API)

**Эндпоинт:** `POST /api/references/resources/{id}/discover_news/`

**Формат:** JSON (не FormData!)

```javascript
fetch(`/api/references/resources/${resourceId}/discover_news/`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    provider: 'grok'  // или 'anthropic', 'openai', 'auto'
  })
})
```

**Ответ:**
```json
{
  "status": "running",
  "resource_id": 123,
  "resource_name": "ACHR News",
  "provider": "grok",
  "message": "Поиск новостей запущен для источника \"ACHR News\""
}
```

### Запуск поиска по одному источнику (Admin)

**Эндпоинт:** `POST /admin/references/newsresource/{id}/discover/`

**Формат:** FormData (как и основной эндпоинт)

```javascript
const formData = new FormData();
formData.append('provider', 'anthropic');

fetch(`/admin/references/newsresource/${resourceId}/discover/`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'X-Requested-With': 'XMLHttpRequest'
  },
  body: formData
})
```

---

## 🔧 Исправления

### Исправлена ошибка в `discover_news_info`:

**Проблема:** Потенциальная ошибка при обработке `last_run.last_search_date` если он `None`

**Исправление:**
```python
# Было:
if last_run:
    period_start = timezone.make_aware(
        datetime.combine(last_run.last_search_date, datetime.min.time())
    )

# Стало:
if last_run and last_run.last_search_date:
    try:
        period_start = timezone.make_aware(
            datetime.combine(last_run.last_search_date, datetime.min.time())
        )
    except (AttributeError, TypeError) as e:
        logger.warning(f"Error creating period_start from last_run: {str(e)}")
        period_start = None
```

---

## ✅ Итоговая таблица эндпоинтов

| Эндпоинт | Метод | Аутентификация | Формат | Статус |
|----------|-------|----------------|--------|--------|
| `/admin/references/newsresource/discover-news-info/` | GET | ✅ Требуется (admin) | - | ✅ Работает (исправлено) |
| `/api/references/resources/available_providers/` | GET | ❌ Не требуется | - | ✅ Работает |
| `/admin/references/newsresource/discover-news/` | POST | ✅ Требуется (admin) | FormData | ✅ Работает |
| `/api/references/resources/{id}/discover_news/` | POST | ✅ Требуется | JSON | ✅ Работает |
| `/admin/references/newsresource/{id}/discover/` | POST | ✅ Требуется (admin) | FormData | ✅ Работает |

---

## 🐛 Отладка ошибок

Если эндпоинт возвращает 500, проверьте:

1. **Логи Django:**
   ```bash
   # Проверьте логи Django на наличие traceback
   tail -f /path/to/django.log
   ```

2. **Проверка аутентификации:**
   - Убедитесь, что токен валиден
   - Убедитесь, что пользователь имеет права администратора (`is_staff=True`)

3. **Проверка базы данных:**
   - Убедитесь, что миграции применены: `python manage.py migrate`
   - Проверьте наличие таблиц: `news_newsdiscoverystatus`, `news_newsdiscoveryrun`

4. **Тестовый запрос:**
   ```bash
   curl -X GET "http://localhost:8000/admin/references/newsresource/discover-news-info/" \
     -H "Authorization: Bearer YOUR_TOKEN" \
     -H "X-Requested-With: XMLHttpRequest"
   ```
