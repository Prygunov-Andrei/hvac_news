# Исправление ошибки Gemini API

## Проблема

При использовании модели `gemini-3-pro-preview` возникала ошибка:
```
429 You exceeded your current quota
Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_input_token_count, limit: 0, model: gemini-3-pro
```

## Причина

Модель `gemini-3-pro-preview` **НЕ доступна на бесплатном тарифе** Google Gemini API. Для использования этой модели требуется платная подписка с включенным Cloud Billing.

На бесплатном тарифе квота для этой модели равна 0, что вызывает ошибку 429 (Quota Exceeded).

## Решение

Переключиться на модель, доступную на бесплатном тарифе:

### Рекомендуемая модель: `gemini-2.5-flash`

**Характеристики:**
- **Модель:** `gemini-2.5-flash`
- **Бесплатный тариф:** 250 запросов в день
- **Входные токены:** до 1 миллиона
- **Выходные токены:** до 65,536
- **Возможности:** текст, изображения, видео, аудио, function calling, structured outputs

**Альтернатива:** `gemini-2.5-flash-lite`
- **Бесплатный тариф:** 1,000 запросов в день
- Оптимизирована для высокообъемных задач с низкой задержкой

## Внесенные изменения

1. **config/settings.py:**
   ```python
   NEWS_DISCOVERY_GEMINI_MODEL = os.getenv('NEWS_DISCOVERY_GEMINI_MODEL', 'gemini-2.5-flash')
   ```

2. **Обновлена документация** в `docs/NEWS_DISCOVERY_PLAN.md`

## Проверка

После изменения модели тестирование прошло успешно:
- ✅ Gemini API работает без ошибок
- ✅ Создание новостей функционирует корректно
- ✅ Ошибок: 0

## Дополнительная информация

### Доступные модели на бесплатном тарифе (по состоянию на декабрь 2025):

1. **gemini-2.5-flash**
   - 250 запросов/день
   - Подходит для большинства задач

2. **gemini-2.5-flash-lite**
   - 1,000 запросов/день
   - Для высокообъемных задач

### Модели, требующие платную подписку:

- `gemini-3-pro-preview` ❌
- `gemini-3-pro` ❌
- `gemini-3-flash` (требует проверки)

### Устаревшие модели (retired):

- `gemini-1.5-flash` ❌
- `gemini-1.5-pro` ❌

## Ссылки

- [Gemini API Models Documentation](https://ai.google.dev/models/gemini)
- [Gemini API Quotas](https://ai.google.dev/gemini-api/docs/quota)
- [Gemini API Pricing](https://ai.google.dev/pricing)
