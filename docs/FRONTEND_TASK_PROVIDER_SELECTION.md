# Задание для Фронтенд-разработчика: Выбор провайдера LLM для поиска новостей

**Цель:** Добавить возможность выбора провайдера LLM при запуске поиска новостей. Пользователь должен иметь возможность выбрать конкретный провайдер (Grok, Anthropic, OpenAI) или использовать автоматический выбор (цепочка провайдеров).

**Приоритет:** Средний

**Время на реализацию:** 3-5 часов

## Описание задачи

При запуске поиска новостей (как по источникам, так и по производителям) пользователь должен иметь возможность выбрать провайдер LLM. Это позволит:
- Контролировать расходы (выбор самого экономичного провайдера)
- Тестировать качество разных провайдеров
- Использовать конкретный провайдер при необходимости

**Важно:** Поиск можно запускать:
1. **Для всех источников сразу** - массовый поиск
2. **Для отдельного источника** - индивидуальный поиск с выбором провайдера
3. **Для выбранных источников** - через admin actions

## API Endpoints

**Базовый URL:** `/api/references/resources/`

### Получение списка доступных провайдеров
```
GET /api/references/resources/available_providers/
```

**Аутентификация:** Не требуется

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

**Примечание:** Поле `available` показывает, настроен ли API ключ для данного провайдера. Если `false` - провайдер недоступен.

### Запуск поиска новостей по всем источникам
```
POST /admin/references/newsresource/discover-news/
Content-Type: application/x-www-form-urlencoded
```

**Аутентификация:** Требуется (JWT токен или сессия администратора)

**Параметры:**
- `provider` (string, опционально) - ID провайдера (`auto`, `grok`, `anthropic`, `openai`). По умолчанию: `auto`

**Пример запроса:**
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

**Ответ (AJAX):**
```json
{
  "status": "running",
  "processed": 0,
  "total": 220,
  "percent": 0
}
```

### Запуск поиска новостей по одному источнику (API)
```
POST /api/references/resources/{id}/discover_news/
Content-Type: application/json
```

**Аутентификация:** Требуется (JWT токен в заголовке `Authorization: Bearer {token}`)

**Параметры (JSON body):**
- `provider` (string, опционально) - ID провайдера (`auto`, `grok`, `anthropic`, `openai`). По умолчанию: `auto`

**Пример запроса:**
```javascript
fetch(`/api/references/resources/${resourceId}/discover_news/`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    provider: 'grok'
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

### Запуск поиска новостей по одному источнику (Admin)
```
POST /admin/references/newsresource/{id}/discover/
Content-Type: application/x-www-form-urlencoded
```

**Аутентификация:** Требуется (JWT токен или сессия администратора)

**Параметры:**
- `provider` (string, опционально) - ID провайдера (`auto`, `grok`, `anthropic`, `openai`). По умолчанию: `auto`

**Пример запроса:**
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

**Ответ (AJAX):**
```json
{
  "status": "running",
  "resource_id": 123,
  "resource_name": "ACHR News",
  "provider": "anthropic",
  "message": "Поиск новостей запущен для источника \"ACHR News\""
}
```

### Запуск поиска новостей по производителям
```
POST /admin/references/manufacturer/discover-manufacturers-news/
Content-Type: application/x-www-form-urlencoded
```

**Аутентификация:** Требуется (JWT токен или сессия администратора)

**Параметры:**
- `provider` (string, опционально) - ID провайдера (`auto`, `grok`, `anthropic`, `openai`). По умолчанию: `auto`

**Пример запроса:**
```javascript
const formData = new FormData();
formData.append('provider', 'grok');

fetch('/admin/references/manufacturer/discover-manufacturers-news/', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'X-Requested-With': 'XMLHttpRequest'
  },
  body: formData
})
```

**Ответ (AJAX):**
```json
{
  "status": "running",
  "processed": 0,
  "total": 50,
  "percent": 0
}
```

**Примечание:** Провайдер не возвращается в ответе, но сохраняется в `NewsDiscoveryStatus` для отслеживания.

## UI Требования

### 1. Компонент выбора провайдера

**Местоположение:** В модальном окне или форме запуска поиска новостей

**Элементы:**
- Радио-кнопки или выпадающий список для выбора провайдера
- Описание каждого провайдера (название + стоимость)
- Визуальная индикация доступности провайдера (disabled для недоступных)
- Подсказка о том, что означает "Автоматический выбор"

**Дизайн:**
- Рекомендуется использовать карточки (cards) для каждого провайдера
- Выделить рекомендуемый вариант (Grok - самый экономичный)
- Показать стоимость для каждого провайдера

### 2. Визуальные индикаторы

**Для доступных провайдеров:**
- Зеленая галочка или индикатор "Доступен"
- Активная кнопка/радио-кнопка

**Для недоступных провайдеров:**
- Серый цвет или индикатор "Недоступен"
- Disabled состояние
- Подсказка: "API ключ не настроен"

### 3. Информация о провайдерах

Отображать для каждого провайдера:
- **Название** (например, "Grok 4.1 Fast")
- **Стоимость** (например, "~$0.13 за 220 ресурсов")
- **Описание** (например, "Самый экономичный вариант")
- **Статус доступности** (Доступен / Недоступен)

## Примеры реализации

### React компонент (TypeScript)

```typescript
import { useState, useEffect } from 'react';

interface Provider {
  id: string;
  name: string;
  description: string;
  available: boolean;
}

interface ProvidersResponse {
  providers: Provider[];
  default: string;
}

const ProviderSelection: React.FC<{
  onProviderChange: (provider: string) => void;
  initialProvider?: string;
}> = ({ onProviderChange, initialProvider = 'auto' }) => {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string>(initialProvider);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/references/resources/available_providers/')
      .then(res => res.json())
      .then((data: ProvidersResponse) => {
        setProviders(data.providers);
        setSelectedProvider(initialProvider);
        onProviderChange(initialProvider);
        setLoading(false);
      })
      .catch(err => {
        console.error('Error fetching providers:', err);
        setLoading(false);
      });
  }, []);

  const handleProviderChange = (providerId: string) => {
    setSelectedProvider(providerId);
    onProviderChange(providerId);
  };

  if (loading) {
    return <div>Загрузка провайдеров...</div>;
  }

  return (
    <div className="provider-selection">
      <h3>Выберите провайдер LLM</h3>
      <div className="providers-grid">
        {providers.map(provider => (
          <div
            key={provider.id}
            className={`provider-card ${!provider.available ? 'disabled' : ''} ${
              selectedProvider === provider.id ? 'selected' : ''
            }`}
            onClick={() => provider.available && handleProviderChange(provider.id)}
          >
            <div className="provider-header">
              <input
                type="radio"
                name="provider"
                value={provider.id}
                checked={selectedProvider === provider.id}
                onChange={() => handleProviderChange(provider.id)}
                disabled={!provider.available}
              />
              <span className="provider-name">{provider.name}</span>
              {provider.available ? (
                <span className="badge available">Доступен</span>
              ) : (
                <span className="badge unavailable">Недоступен</span>
              )}
            </div>
            <p className="provider-description">{provider.description}</p>
            {!provider.available && (
              <p className="provider-hint">API ключ не настроен</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

export default ProviderSelection;
```

### Запуск поиска с выбранным провайдером

```typescript
const startNewsDiscovery = async (provider: string) => {
  const formData = new FormData();
  formData.append('provider', provider);

  try {
    const response = await fetch('/admin/references/newsresource/discover-news/', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${authToken}`,
        'X-Requested-With': 'XMLHttpRequest'
      },
      body: formData
    });

    if (!response.ok) {
      throw new Error('Ошибка запуска поиска');
    }

    const data = await response.json();
    // Обработка ответа (статус, прогресс и т.д.)
    return data;
  } catch (error) {
    console.error('Error starting discovery:', error);
    throw error;
  }
};
```

### TailwindCSS стили (пример)

```css
.provider-selection {
  @apply p-4;
}

.providers-grid {
  @apply grid grid-cols-1 md:grid-cols-2 gap-4 mt-4;
}

.provider-card {
  @apply border-2 rounded-lg p-4 cursor-pointer transition-all;
  @apply hover:border-blue-500 hover:shadow-md;
}

.provider-card.selected {
  @apply border-blue-600 bg-blue-50;
}

.provider-card.disabled {
  @apply opacity-50 cursor-not-allowed;
  @apply hover:border-gray-300 hover:shadow-none;
}

.provider-header {
  @apply flex items-center gap-3 mb-2;
}

.provider-name {
  @apply font-semibold text-lg;
}

.provider-description {
  @apply text-sm text-gray-600 mt-2;
}

.badge {
  @apply px-2 py-1 rounded text-xs font-medium;
}

.badge.available {
  @apply bg-green-100 text-green-800;
}

.badge.unavailable {
  @apply bg-gray-100 text-gray-600;
}
```

## UX Рекомендации

1. **По умолчанию:** Выбирать "Автоматический выбор" (`auto`)
2. **Валидация:** Не позволять запускать поиск с недоступным провайдером
3. **Подсказки:** Показывать tooltip с дополнительной информацией о каждом провайдере
4. **Визуальная иерархия:** Выделить рекомендуемый вариант (Grok - самый экономичный)
5. **Информативность:** Показывать стоимость для каждого провайдера
6. **Обратная связь:** При выборе недоступного провайдера показывать сообщение о необходимости настройки API ключа

## Интеграция в существующий UI

### Где добавить:

1. **Страница источников новостей (список):**
   - В модальном окне запуска поиска для всех источников
   - Или в форме перед кнопкой "Начать поиск"

2. **Карточка отдельного источника:**
   - Кнопка "Запустить поиск" с выбором провайдера
   - Может быть в виде dropdown или модального окна
   - Рекомендуется разместить рядом с кнопкой "Сохранить"

3. **Страница производителей:**
   - Аналогично, в форме запуска поиска по производителям

4. **Admin actions (для выбранных источников):**
   - При выборе нескольких источников в списке
   - Action "Запустить поиск новостей для выбранных источников" (`discover_selected_resources`)
   - Провайдер передается через POST параметр `provider` в форме action
   - **Важно:** Для admin actions провайдер передается через стандартную форму Django admin, где можно добавить поле выбора провайдера перед выполнением action

### Пример интеграции в модальное окно (для всех источников):

```typescript
const DiscoveryModal: React.FC<{
  isOpen: boolean;
  onClose: () => void;
  onStart: (provider: string) => void;
}> = ({ isOpen, onClose, onStart }) => {
  const [selectedProvider, setSelectedProvider] = useState<string>('auto');

  const handleStart = () => {
    onStart(selectedProvider);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay">
      <div className="modal-content">
        <h2>Запуск поиска новостей</h2>
        
        <ProviderSelection
          onProviderChange={setSelectedProvider}
          initialProvider={selectedProvider}
        />
        
        <div className="modal-actions">
          <button onClick={onClose}>Отмена</button>
          <button onClick={handleStart} className="primary">
            Начать поиск
          </button>
        </div>
      </div>
    </div>
  );
};
```

### Пример кнопки для отдельного источника:

```typescript
const ResourceDiscoveryButton: React.FC<{
  resourceId: number;
  resourceName: string;
}> = ({ resourceId, resourceName }) => {
  const [selectedProvider, setSelectedProvider] = useState<string>('auto');
  const [loading, setLoading] = useState(false);
  const [showProviderSelect, setShowProviderSelect] = useState(false);

  const handleDiscover = async () => {
    setLoading(true);
    try {
      const response = await fetch(`/api/references/resources/${resourceId}/discover_news/`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${authToken}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ provider: selectedProvider })
      });

      if (!response.ok) {
        throw new Error('Ошибка запуска поиска');
      }

      const data = await response.json();
      // Показать уведомление об успешном запуске
      showNotification(data.message, 'success');
      setShowProviderSelect(false);
    } catch (error) {
      showNotification('Ошибка при запуске поиска', 'error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="resource-discovery">
      {showProviderSelect ? (
        <div className="provider-select-dropdown">
          <ProviderSelection
            onProviderChange={setSelectedProvider}
            initialProvider={selectedProvider}
          />
          <div className="dropdown-actions">
            <button onClick={() => setShowProviderSelect(false)}>Отмена</button>
            <button onClick={handleDiscover} disabled={loading}>
              {loading ? 'Запуск...' : 'Запустить поиск'}
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => setShowProviderSelect(true)}
          className="btn-discover"
        >
          🔍 Запустить поиск новостей
        </button>
      )}
    </div>
  );
};
```

## Тестирование

1. **Проверить загрузку списка провайдеров:**
   - Все провайдеры отображаются
   - Правильно определяется доступность

2. **Проверить выбор провайдера:**
   - Можно выбрать любой доступный провайдер
   - Недоступные провайдеры disabled

3. **Проверить запуск поиска:**
   - Провайдер передается в POST запрос
   - Поиск запускается с выбранным провайдером

4. **Проверить валидацию:**
   - Нельзя запустить поиск с недоступным провайдером
   - Показываются соответствующие сообщения

## Дополнительные улучшения (опционально)

1. **Сохранение выбора:** Сохранять последний выбранный провайдер в localStorage
2. **Статистика:** Показывать историю использования провайдеров
3. **Сравнение:** Показывать сравнение стоимости разных провайдеров
4. **Рекомендации:** Подсказывать оптимальный провайдер на основе истории

## Примечания

- Провайдер "Автоматический выбор" всегда доступен
- Если все провайдеры недоступны, показывать предупреждение
- При ошибке загрузки списка провайдеров использовать значения по умолчанию
- Выбранный провайдер сохраняется в `NewsDiscoveryStatus` и может быть использован для анализа

## Чек-лист выполнения

- [ ] Реализован компонент выбора провайдера
- [ ] Интегрирован в форму запуска поиска по всем источникам
- [ ] Интегрирован в форму запуска поиска по производителям
- [ ] Добавлена кнопка запуска поиска для отдельного источника
- [ ] Реализован API вызов для поиска по одному источнику
- [ ] Отображается статус доступности каждого провайдера
- [ ] Провайдер передается в POST запрос при запуске поиска
- [ ] Добавлена валидация (нельзя выбрать недоступный провайдер)
- [ ] Добавлены подсказки и описания для каждого провайдера
- [ ] Протестирована работа с разными провайдерами
- [ ] Протестирован поиск по одному источнику
- [ ] Обработаны случаи ошибок (недоступность API, сетевые ошибки)
- [ ] Обработан случай источника типа "manual" (показывать предупреждение)
