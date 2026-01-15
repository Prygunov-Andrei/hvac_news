# Выбор провайдера LLM для поиска новостей

## Обзор

Теперь пользователь может выбрать конкретный провайдер LLM для каждого поиска новостей. Доступны 4 варианта:

1. **Автоматический выбор (цепочка)** - `auto` (по умолчанию)
   - Использует цепочку: Grok → Anthropic → OpenAI
   - Если один провайдер недоступен, автоматически переключается на следующий

2. **Grok 4.1 Fast** - `grok`
   - Самый экономичный вариант (~$0.13 за 220 ресурсов)
   - Требует настройки `XAI_API_KEY`

3. **Anthropic Claude Haiku 4.5** - `anthropic`
   - Экономичный вариант от Anthropic (~$4.26 за 220 ресурсов)
   - Требует настройки `ANTHROPIC_API_KEY`

4. **OpenAI GPT-5.2** - `openai`
   - Резервный вариант (~$6.35 за 220 ресурсов)
   - Требует настройки `TRANSLATION_API_KEY`

## Использование

### В админке Django

При запуске поиска новостей через админку, добавьте параметр `provider` в POST запрос:

```html
<form method="post" action="/admin/references/newsresource/discover-news/">
    <select name="provider">
        <option value="auto">Автоматический выбор</option>
        <option value="grok">Grok 4.1 Fast</option>
        <option value="anthropic">Anthropic Claude Haiku 4.5</option>
        <option value="openai">OpenAI GPT-5.2</option>
    </select>
    <button type="submit">Начать поиск</button>
</form>
```

### Через API

#### 1. Получить список доступных провайдеров

```http
GET /api/references/resources/available_providers/
```

**Ответ:**
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

#### 2. Запустить поиск с выбранным провайдером

```http
POST /admin/references/newsresource/discover-news/
Content-Type: application/x-www-form-urlencoded

provider=grok
```

Или для производителей:

```http
POST /admin/references/manufacturer/discover-manufacturers-news/
Content-Type: application/x-www-form-urlencoded

provider=anthropic
```

### Программно (Python)

```python
from news.discovery_service import NewsDiscoveryService
from references.models import NewsResource

service = NewsDiscoveryService(user=request.user)

# Использовать конкретный провайдер
created, errors, error_msg = service.discover_news_for_resource(
    resource, 
    provider='grok'  # или 'anthropic', 'openai', 'auto'
)

# Или для всех новостей
status_obj = NewsDiscoveryStatus.create_new_status(
    total_count=220,
    search_type='resources',
    provider='anthropic'  # выбранный провайдер
)
service.discover_all_news(status_obj=status_obj)
```

## Хранение выбранного провайдера

Выбранный провайдер сохраняется в модели `NewsDiscoveryStatus` в поле `provider`. Это позволяет:

- Отслеживать, какой провайдер использовался для каждого поиска
- Анализировать эффективность разных провайдеров
- Повторять поиск с тем же провайдером

## Поведение при ошибках

- **Автоматический выбор (`auto`)**: При ошибке одного провайдера автоматически переключается на следующий
- **Конкретный провайдер**: При ошибке создается новость об ошибке, поиск не переключается на другой провайдер

## Рекомендации

1. **Для экономии**: Используйте `grok` - самый дешевый вариант
2. **Для надежности**: Используйте `auto` - автоматический fallback при ошибках
3. **Для тестирования**: Используйте конкретный провайдер для сравнения результатов
4. **Для качества**: Используйте `anthropic` или `openai` если нужна альтернатива Grok

## Миграция базы данных

После обновления кода выполните миграцию:

```bash
python manage.py migrate news
```

Это добавит поле `provider` в таблицу `news_newsdiscoverystatus`.
