# Поле `is_no_news_found` для фильтрации записей "новостей не найдено"

## Описание

Добавлено поле `is_no_news_found` в модель `NewsPost` для пометки записей, которые создаются когда при поиске новостей в источнике ничего не найдено.

Это поле позволяет легко фильтровать и массово удалять такие записи на фронтенде после проверки администратором.

## Технические детали

- **Тип поля:** `BooleanField`
- **По умолчанию:** `False`
- **Только для чтения:** Да (устанавливается автоматически системой)

## Использование в API

### 1. Получение всех записей "новостей не найдено"

```http
GET /api/news/?is_no_news_found=true
```

**Ответ:**
```json
[
  {
    "id": 123,
    "title": "Новостей от источника 'Example' не найдено",
    "is_no_news_found": true,
    "source_url": "https://example.com",
    "status": "draft",
    ...
  },
  ...
]
```

### 2. Получение только реальных новостей (исключая "не найдено")

```http
GET /api/news/?is_no_news_found=false
```

или просто:

```http
GET /api/news/
```

(по умолчанию `is_no_news_found=false` для реальных новостей)

### 3. Массовое удаление записей "новостей не найдено"

**Вариант 1: Через фильтр в запросе DELETE**

```http
DELETE /api/news/?is_no_news_found=true
```

**Вариант 2: На фронтенде - получить список ID и удалить**

```javascript
// 1. Получить все записи "не найдено"
const response = await fetch('/api/news/?is_no_news_found=true');
const noNewsPosts = await response.json();

// 2. Удалить каждую запись
for (const post of noNewsPosts) {
  await fetch(`/api/news/${post.id}/`, {
    method: 'DELETE',
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });
}
```

## В админ-панели Django

- Поле отображается в списке новостей
- Доступен фильтр по `is_no_news_found` в правой панели
- Поле только для чтения (нельзя изменить вручную)

## Автоматическая установка

Поле автоматически устанавливается в `True` при создании записи через метод `_create_no_news_news()` в `discovery_service.py`.

## Пример использования на фронтенде

```javascript
// Компонент для массового удаления записей "не найдено"
async function deleteNoNewsFoundPosts() {
  try {
    // Получаем все записи "не найдено"
    const response = await fetch('/api/news/?is_no_news_found=true&status=draft', {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });
    
    const posts = await response.json();
    
    if (posts.length === 0) {
      alert('Нет записей "новостей не найдено" для удаления');
      return;
    }
    
    // Подтверждение
    const confirmed = confirm(
      `Найдено ${posts.length} записей "новостей не найдено". Удалить все?`
    );
    
    if (!confirmed) return;
    
    // Удаляем каждую запись
    const deletePromises = posts.map(post => 
      fetch(`/api/news/${post.id}/`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      })
    );
    
    await Promise.all(deletePromises);
    alert(`Успешно удалено ${posts.length} записей`);
    
    // Обновляем список
    window.location.reload();
    
  } catch (error) {
    console.error('Ошибка при удалении:', error);
    alert('Произошла ошибка при удалении записей');
  }
}
```

## Фильтрация в списке новостей

```javascript
// Показать только записи "не найдено"
const showOnlyNoNews = async () => {
  const response = await fetch('/api/news/?is_no_news_found=true');
  const posts = await response.json();
  setNewsList(posts);
};

// Показать только реальные новости
const showOnlyRealNews = async () => {
  const response = await fetch('/api/news/?is_no_news_found=false');
  const posts = await response.json();
  setNewsList(posts);
};
```

## Примечания

- Поле устанавливается автоматически системой при создании записи "новостей не найдено"
- Нельзя изменить это поле вручную через API (только для чтения)
- Все существующие записи "не найдено" будут автоматически помечены при следующем запуске поиска
- Для старых записей можно обновить вручную через админ-панель или SQL запрос
