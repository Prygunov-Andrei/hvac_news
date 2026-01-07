# Результаты тестирования моделей для поиска новостей

## Проблемы обнаруженные при тестировании

### 1. OpenAI GPT-5.2-pro

**Ошибка:**
```
Error code: 404 - {'error': {'message': 'This is not a chat model and thus not supported in the v1/chat/completions endpoint. Did you mean to use v1/completions?', 'type': 'invalid_request_error', 'param': 'model', 'code': None}}
```

**Причина:**
- `gpt-5.2-pro` доступен только в Responses API, а не в Chat Completions API
- Для Chat Completions API нужно использовать:
  - `gpt-5.2` (Thinking) - для сложных задач
  - `gpt-5.2-chat-latest` (Instant) - для быстрых задач

**Решение:**
- Изменить модель на `gpt-5.2` (Thinking) для Chat Completions API
- Или использовать Responses API для `gpt-5.2-pro`

### 2. Gemini-3-pro-preview

**Ошибки:**

1. **Синтаксис google_search:**
```
Unknown field for FunctionDeclaration: google_search
```

2. **Квота превышена:**
```
429 You exceeded your current quota, please check your plan and billing details.
* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 0, model: gemini-3-pro
```

**Причины:**
- Gemini-3-pro **не доступна на бесплатном тарифе** (limit: 0)
- Неправильный синтаксис для включения `google_search` tool
- Используется устаревший пакет `google.generativeai` (нужно использовать `google.genai`)

**Решение:**
- Использовать модель доступную на бесплатном тарифе: `gemini-2.5-flash`
- Или настроить платный аккаунт для Gemini-3-pro
- Обновить код для использования нового пакета `google.genai` с правильным синтаксисом

## Рекомендации

### Краткосрочное решение:
1. **OpenAI:** Использовать `gpt-5.2` (Thinking) вместо `gpt-5.2-pro`
2. **Gemini:** Использовать `gemini-2.5-flash` (доступна на бесплатном тарифе) или настроить платный аккаунт

### Долгосрочное решение:
1. Обновить код для использования нового пакета `google.genai` вместо `google.generativeai`
2. Настроить платный аккаунт для Gemini-3-pro если нужна эта модель
3. Проверить поддержку веб-поиска в выбранных моделях

## Текущий статус

- ✅ OpenAI модель исправлена на `gpt-5.2`
- ⚠️ Gemini модель требует настройки (квота или синтаксис)
- ⚠️ Нужно протестировать после исправлений
