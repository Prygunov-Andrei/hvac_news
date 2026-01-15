# Интеграция Anthropic Claude для поиска новостей

## Обзор

Anthropic Claude добавлен как дополнительный провайдер в цепочку поиска новостей. Используется модель **Claude Haiku 4.5** - самый экономичный вариант от Anthropic.

## Цепочка провайдеров

Порядок использования провайдеров:
1. **Grok 4.1 Fast** (основной) - самый дешевый (~$0.13 за 220 ресурсов)
2. **Anthropic Claude Haiku 4.5** (опционально) - если Grok недоступен (~$4.26 за 220 ресурсов)
3. **OpenAI GPT-5.2** (резервный) - если оба предыдущих недоступны (~$6.35 за 220 ресурсов)

## Цены Anthropic (2025)

### Claude Haiku 4.5 (рекомендуется)
- **Input токены:** $1.00 за 1M токенов
- **Output токены:** $5.00 за 1M токенов
- **Веб-поиск:** $10.00 за 1,000 поисков
- **Для 220 ресурсов:** ~$4.26 за разовый поиск

### Claude Sonnet 4.5 (альтернатива)
- **Input токены:** $3.00 за 1M токенов
- **Output токены:** $15.00 за 1M токенов
- **Веб-поиск:** $10.00 за 1,000 поисков
- **Для 220 ресурсов:** ~$8.36 за разовый поиск

## Настройка

### 1. Установка зависимостей

```bash
pip install anthropic>=0.34.0
```

Или обновить requirements.txt:
```bash
pip install -r requirements.txt
```

### 2. Получение API ключа

1. Зарегистрируйтесь на [console.anthropic.com](https://console.anthropic.com)
2. Создайте API ключ
3. Убедитесь, что веб-поиск включен для вашего аккаунта (требуется в настройках)

### 3. Настройка переменных окружения

Добавьте в `.env` файл:

```env
# Anthropic (Claude) Configuration
ANTHROPIC_API_KEY=your-anthropic-api-key-here
NEWS_DISCOVERY_ANTHROPIC_MODEL=claude-3-5-haiku-20241022
NEWS_DISCOVERY_USE_ANTHROPIC=True
NEWS_DISCOVERY_ANTHROPIC_PRIORITY=2
```

### Параметры:

- `ANTHROPIC_API_KEY` - API ключ от Anthropic (обязательно)
- `NEWS_DISCOVERY_ANTHROPIC_MODEL` - модель Claude (по умолчанию: `claude-3-5-haiku-20241022`)
  - `claude-3-5-haiku-20241022` - Haiku 4.5 (рекомендуется, самый дешевый)
  - `claude-3-5-sonnet-20241022` - Sonnet 4.5 (дороже, но качественнее)
- `NEWS_DISCOVERY_USE_ANTHROPIC` - включить/выключить Anthropic (`True`/`False`, по умолчанию: `False`)
- `NEWS_DISCOVERY_ANTHROPIC_PRIORITY` - приоритет в цепочке (1=сразу после Grok, 2=перед OpenAI, по умолчанию: 2)

## Использование

### Включение Anthropic

Установите в `.env`:
```env
NEWS_DISCOVERY_USE_ANTHROPIC=True
```

### Отключение Anthropic

Установите в `.env`:
```env
NEWS_DISCOVERY_USE_ANTHROPIC=False
```

Или просто не указывайте `ANTHROPIC_API_KEY`.

## Как это работает

1. Система сначала пытается использовать **Grok** (если включен)
2. Если Grok недоступен или вернул ошибку, пробует **Anthropic** (если включен)
3. Если Anthropic тоже недоступен, использует **OpenAI** как резервный вариант
4. Если все провайдеры недоступны - создается новость об ошибке

## Сравнение провайдеров

| Провайдер | Модель | Стоимость (220 ресурсов) | Месяц (30 дней) |
|-----------|--------|-------------------------|-----------------|
| **Grok** | 4.1 Fast | **~$0.13** | **~$3.90** |
| **Anthropic** | Haiku 4.5 | ~$4.26 | ~$127.80 |
| **OpenAI** | GPT-5.2 | ~$6.35 | ~$190.50 |

**Вывод:** Grok остается самым экономичным вариантом, Anthropic - хорошая альтернатива между Grok и OpenAI.

## Технические детали

### Веб-поиск

Anthropic использует инструмент `web_search_20250305` с параметрами:
- `max_uses: 5` - максимум 5 веб-поисков на запрос
- Автоматическое определение необходимости поиска моделью

### Формат ответа

Anthropic возвращает JSON в том же формате, что и другие провайдеры:
```json
{
  "news": [
    {
      "title": {"ru": "...", "en": "...", "de": "...", "pt": "..."},
      "summary": {"ru": "...", "en": "...", "de": "...", "pt": "..."},
      "source_url": "https://..."
    }
  ]
}
```

### Обработка ошибок

- Если Anthropic недоступен - автоматически переключается на следующий провайдер
- Если JSON некорректен - логируется предупреждение, возвращается пустой результат
- Все ошибки логируются с префиксом `[Anthropic]`

## Рекомендации

1. **Для экономии:** Используйте Grok как основной провайдер, Anthropic только как fallback
2. **Для качества:** Если нужна альтернатива Grok, используйте Anthropic Haiku 4.5
3. **Для максимального качества:** Используйте Anthropic Sonnet 4.5 (но это дороже)

## Полезные ссылки

- [Anthropic API Documentation](https://docs.anthropic.com)
- [Claude API Pricing](https://claude.com/pricing#api)
- [Web Search Tool Documentation](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/web-search-tool)
