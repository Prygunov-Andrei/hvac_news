# Frontend Task: Search Configuration & Discovery Analytics

## Описание

Реализовать интерфейс для управления настройками поиска новостей и просмотра аналитики по запускам поиска.

## Новые API Endpoints

### 1. Search Configuration (Конфигурация поиска)

**Base URL**: `/api/search-config/`

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/search-config/` | Список всех конфигураций |
| POST | `/api/search-config/` | Создать конфигурацию |
| GET | `/api/search-config/{id}/` | Получить конфигурацию |
| PUT | `/api/search-config/{id}/` | Обновить конфигурацию |
| DELETE | `/api/search-config/{id}/` | Удалить конфигурацию |
| GET | `/api/search-config/active/` | Получить активную конфигурацию |
| POST | `/api/search-config/{id}/activate/` | Активировать конфигурацию |
| POST | `/api/search-config/{id}/duplicate/` | Дублировать конфигурацию |

**Права доступа**: Только администраторы (IsAdminUser)

#### Поля конфигурации

```typescript
interface SearchConfiguration {
  id: number;
  name: string;
  is_active: boolean;
  
  // Провайдеры
  primary_provider: 'grok' | 'anthropic' | 'gemini' | 'openai';
  fallback_chain: string[]; // например: ['anthropic', 'openai']
  
  // Параметры LLM
  temperature: number; // 0.0 - 1.0, default 0.3
  timeout: number; // секунды, default 120
  max_news_per_resource: number; // default 10
  delay_between_requests: number; // секунды, default 0.5
  
  // Grok Web Search параметры
  max_search_results: number; // default 5, влияет на стоимость!
  search_context_size: 'low' | 'medium' | 'high'; // default 'low'
  
  // Модели LLM
  grok_model: string; // default 'grok-4-1-fast'
  anthropic_model: string; // default 'claude-3-5-haiku-20241022'
  gemini_model: string; // default 'gemini-2.0-flash-exp'
  openai_model: string; // default 'gpt-4o'
  
  // Тарифы (USD за 1M токенов)
  grok_input_price: number; // default 3.0
  grok_output_price: number; // default 15.0
  anthropic_input_price: number; // default 0.80
  anthropic_output_price: number; // default 4.0
  gemini_input_price: number; // default 0.075
  gemini_output_price: number; // default 0.30
  openai_input_price: number; // default 2.50
  openai_output_price: number; // default 10.0
  
  created_at: string; // ISO datetime
  updated_at: string; // ISO datetime
}
```

#### Краткий формат для списка

```typescript
interface SearchConfigurationListItem {
  id: number;
  name: string;
  is_active: boolean;
  primary_provider: string;
  max_search_results: number;
  temperature: number;
  updated_at: string;
}
```

---

### 2. Discovery Runs (История запусков поиска)

**Base URL**: `/api/discovery-runs/`

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/discovery-runs/` | Список запусков (пагинация) |
| GET | `/api/discovery-runs/{id}/` | Детали запуска |
| GET | `/api/discovery-runs/{id}/api_calls/` | API вызовы запуска |
| GET | `/api/discovery-runs/stats/` | Агрегированная статистика |
| GET | `/api/discovery-runs/latest/` | Последний запуск |

**Права доступа**: Только администраторы (IsAdminUser)

#### Детальный формат

```typescript
interface NewsDiscoveryRun {
  id: number;
  last_search_date: string; // YYYY-MM-DD
  config_snapshot: SearchConfiguration | null; // снимок конфигурации
  
  // Время
  started_at: string | null; // ISO datetime
  finished_at: string | null; // ISO datetime
  duration_display: string; // "HH:MM:SS"
  
  // Метрики API
  total_requests: number;
  total_input_tokens: number;
  total_output_tokens: number;
  estimated_cost_usd: string; // decimal string, например "0.5000"
  
  // Статистика по провайдерам
  provider_stats: {
    [provider: string]: {
      requests: number;
      input_tokens: number;
      output_tokens: number;
      cost: number;
      errors: number;
    }
  };
  
  // Результаты
  news_found: number;
  news_duplicates: number;
  resources_processed: number;
  resources_failed: number;
  
  // Вычисляемые поля
  efficiency: number; // news_found / cost, новости на доллар
  api_calls_count: number;
  
  created_at: string;
  updated_at: string;
}
```

#### Краткий формат для списка

```typescript
interface NewsDiscoveryRunListItem {
  id: number;
  last_search_date: string;
  config_name: string | null;
  started_at: string | null;
  finished_at: string | null;
  duration_display: string;
  total_requests: number;
  estimated_cost_usd: string;
  news_found: number;
  resources_processed: number;
  resources_failed: number;
  efficiency: number;
  created_at: string;
}
```

#### Статистика (GET /api/discovery-runs/stats/)

Query параметры:
- `days` (optional): фильтр по количеству дней (например, `?days=7` для последней недели)

```typescript
interface DiscoveryStats {
  total_runs: number;
  total_news_found: number;
  total_cost_usd: string; // decimal
  total_requests: number;
  total_input_tokens: number;
  total_output_tokens: number;
  avg_efficiency: number; // среднее news/dollar
  avg_cost_per_run: string; // decimal
  provider_breakdown: {
    [provider: string]: {
      requests: number;
      input_tokens: number;
      output_tokens: number;
      cost: number;
      errors: number;
    }
  };
}
```

---

### 3. Discovery API Calls (Детальная история вызовов)

**Base URL**: `/api/discovery-calls/`

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/discovery-calls/` | Список вызовов (пагинация) |
| GET | `/api/discovery-calls/{id}/` | Детали вызова |

**Query параметры фильтрации**:
- `provider`: фильтр по провайдеру ('grok', 'anthropic', 'gemini', 'openai')
- `success`: фильтр по успешности ('true', 'false')
- `run_id`: фильтр по ID запуска

**Права доступа**: Только администраторы (IsAdminUser)

```typescript
interface DiscoveryAPICall {
  id: number;
  discovery_run: number;
  resource: number | null;
  resource_name: string | null;
  manufacturer: number | null;
  manufacturer_name: string | null;
  
  provider: string; // 'grok', 'anthropic', 'gemini', 'openai'
  model: string;
  
  input_tokens: number;
  output_tokens: number;
  cost_usd: string; // decimal, например "0.001234"
  
  duration_ms: number; // миллисекунды
  success: boolean;
  error_message: string;
  
  news_extracted: number;
  
  created_at: string;
}
```

---

## UI Компоненты

### 1. Страница настроек поиска (`/admin/search-settings`)

**Секции:**

1. **Активная конфигурация** (карточка сверху)
   - Показать название, провайдер, основные параметры
   - Кнопка "Редактировать"

2. **Список конфигураций** (таблица)
   - Columns: Name, Active, Provider, Max Results, Temperature, Updated
   - Actions: Activate, Edit, Duplicate, Delete

3. **Форма создания/редактирования** (модальное окно или страница)
   - Группировка полей по секциям:
     - Основные настройки
     - Провайдеры
     - Параметры LLM
     - Grok Web Search
     - Модели (collapsible)
     - Тарифы (collapsible)

### 2. Страница аналитики поиска (`/admin/discovery-analytics`)

**Секции:**

1. **Дашборд** (карточки сверху)
   - Total Cost (с фильтром периода)
   - Total News Found
   - Average Efficiency (news/$)
   - Total Requests

2. **График стоимости** (line chart)
   - X: дата
   - Y: стоимость USD
   - Фильтр по периоду (7 дней, 30 дней, все)

3. **Breakdown по провайдерам** (pie chart или bar chart)
   - Стоимость по провайдерам
   - Количество запросов

4. **История запусков** (таблица с пагинацией)
   - Columns: ID, Date, Config, Duration, News, Cost, Efficiency
   - Click → детальный просмотр

5. **Детальный просмотр запуска** (страница или модал)
   - Общая информация
   - Статистика по провайдерам
   - Список API вызовов (таблица)

---

## Примеры запросов

### Получить активную конфигурацию
```bash
GET /api/search-config/active/
```

### Обновить конфигурацию
```bash
PATCH /api/search-config/1/
Content-Type: application/json

{
  "max_search_results": 3,
  "temperature": 0.2
}
```

### Получить статистику за 7 дней
```bash
GET /api/discovery-runs/stats/?days=7
```

### Получить вызовы с ошибками
```bash
GET /api/discovery-calls/?success=false
```

---

## Важные замечания

1. **Только одна активная конфигурация** — при активации одной, остальные автоматически деактивируются.

2. **config_snapshot** — при запуске поиска сохраняется снимок конфигурации, чтобы видеть какие именно параметры использовались.

3. **Расчёт стоимости** — стоимость рассчитывается автоматически на основе тарифов в конфигурации.

4. **Efficiency** — ключевая метрика для сравнения конфигураций: сколько новостей найдено на доллар.

5. **max_search_results** — критически важный параметр для Grok, напрямую влияет на стоимость (каждый веб-поиск стоит $5/1000 запросов).

---

## Приоритет реализации

1. **Высокий**: Страница настроек с возможностью редактирования активной конфигурации
2. **Средний**: Дашборд аналитики с карточками и графиком стоимости
3. **Низкий**: Детальный просмотр API вызовов
