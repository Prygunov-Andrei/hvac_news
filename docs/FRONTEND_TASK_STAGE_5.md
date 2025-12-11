# Техническое задание для фронтенда: Этап 5 - Веб-редактор новостей

## Общее описание

Реализация полнофункционального веб-редактора новостей для администраторов с поддержкой:
- WYSIWYG-редактор с форматированием текста
- Загрузка и вставка медиафайлов (изображения, видео)
- Автоматический перевод на все языки через LLM
- Черновики и отложенная публикация
- Редактирование и удаление новостей

**Доступ:** Только для пользователей с правами администратора (`is_staff=true`)

---

## 1. API Endpoints

### 1.1. Новости (CRUD)

#### Создание новости
```http
POST /api/news/
Authorization: Bearer <admin_jwt_token>
Content-Type: application/json

{
  "title": "Заголовок новости",
  "body": "<p>HTML-контент новости...</p>",
  "source_language": "ru",
  "pub_date": "2025-12-25T10:00:00Z",
  "status": "draft",
  "auto_translate": true
}
```

**Ответ (201 Created):**
```json
{
  "id": 123,
  "title": "Заголовок новости",
  "title_ru": "Заголовок новости",
  "title_en": "News Title",
  "title_de": "Nachrichtentitel",
  "title_pt": "Título da Notícia",
  "body": "<p>HTML-контент новости...</p>",
  "body_ru": "<p>HTML-контент новости...</p>",
  "body_en": "<p>News HTML content...</p>",
  "body_de": "<p>Nachrichten HTML-Inhalt...</p>",
  "body_pt": "<p>Conteúdo HTML da notícia...</p>",
  "pub_date": "2025-12-25T10:00:00Z",
  "status": "draft",
  "source_language": "ru",
  "created_at": "2025-01-15T12:00:00Z",
  "updated_at": "2025-01-15T12:00:00Z",
  "author": {
    "id": 1,
    "email": "admin@example.com",
    "first_name": "Admin",
    "last_name": "User"
  },
  "media": []
}
```

**Ошибки:**
- `400 Bad Request` - невалидные данные
- `401 Unauthorized` - нет токена
- `403 Forbidden` - пользователь не администратор

---

#### Получение списка новостей
```http
GET /api/news/
Authorization: Bearer <token> (опционально для админов)
```

**Для обычных пользователей:** Возвращаются только опубликованные новости (`status=published`, `pub_date <= now`)

**Для администраторов:** Возвращаются все новости (включая черновики и запланированные)

**Параметры запроса:**
- `?page=1` - номер страницы (пагинация)
- `?limit=10` - количество на странице

**Ответ (200 OK):**
```json
{
  "count": 50,
  "next": "http://api.example.com/api/news/?page=2",
  "previous": null,
  "results": [
    {
      "id": 123,
      "title": "Заголовок",
      "title_ru": "...",
      "title_en": "...",
      "body": "...",
      "pub_date": "2025-01-15T10:00:00Z",
      "status": "published",
      "source_language": "ru",
      "author": {...},
      "media": [...]
    }
  ]
}
```

---

#### Получение одной новости
```http
GET /api/news/<id>/
Authorization: Bearer <token> (опционально)
```

**Ответ (200 OK):** Объект новости (см. формат выше)

**Ошибки:**
- `404 Not Found` - новость не найдена или недоступна для текущего пользователя

---

#### Редактирование новости
```http
PATCH /api/news/<id>/
Authorization: Bearer <admin_jwt_token>
Content-Type: application/json

{
  "title": "Обновленный заголовок",
  "body": "<p>Обновленный контент...</p>",
  "auto_translate": true
}
```

**Ответ (200 OK):** Полный объект новости с обновленными данными

**Ошибки:**
- `400 Bad Request` - невалидные данные
- `403 Forbidden` - нет прав администратора
- `404 Not Found` - новость не найдена

---

#### Удаление новости
```http
DELETE /api/news/<id>/
Authorization: Bearer <admin_jwt_token>
```

**Ответ (204 No Content)** - успешное удаление

**Ошибки:**
- `403 Forbidden` - нет прав администратора
- `404 Not Found` - новость не найдена

---

#### Получение черновиков (только для админов)
```http
GET /api/news/drafts/
Authorization: Bearer <admin_jwt_token>
```

**Ответ (200 OK):** Массив новостей со статусом `draft`

---

#### Получение запланированных новостей (только для админов)
```http
GET /api/news/scheduled/
Authorization: Bearer <admin_jwt_token>
```

**Ответ (200 OK):** Массив новостей со статусом `scheduled`

---

#### Ручная публикация новости (только для админов)
```http
POST /api/news/<id>/publish/
Authorization: Bearer <admin_jwt_token>
```

**Ответ (200 OK):**
```json
{
  "id": 123,
  "title": "...",
  "status": "published",
  "pub_date": "2025-01-15T12:00:00Z",
  ...
}
```

**Примечание:** Если `pub_date` в будущем, он автоматически устанавливается на текущее время.

---

### 1.2. Загрузка медиафайлов

#### Загрузка файла
```http
POST /api/media/
Authorization: Bearer <admin_jwt_token>
Content-Type: multipart/form-data

file: <binary_file>
media_type: "image" (опционально, определяется автоматически)
```

**Поддерживаемые форматы:**
- **Изображения:** `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp` (макс. 10 MB)
- **Видео:** `.mp4`, `.webm` (макс. 100 MB)

**Ответ (201 Created):**
```json
{
  "id": 456,
  "file": "/media/news/uploads/2025/01/image.jpg",
  "url": "http://api.example.com/media/news/uploads/2025/01/image.jpg",
  "media_type": "image",
  "file_size": 2048576,
  "uploaded_by": 1,
  "created_at": "2025-01-15T12:00:00Z"
}
```

**Ошибки:**
- `400 Bad Request` - недопустимый формат или размер файла
- `403 Forbidden` - нет прав администратора

---

#### Получение списка загруженных файлов
```http
GET /api/media/
Authorization: Bearer <admin_jwt_token>
```

**Ответ (200 OK):** Массив объектов `MediaUpload`

---

#### Удаление файла
```http
DELETE /api/media/<id>/
Authorization: Bearer <admin_jwt_token>
```

**Ответ (204 No Content)**

---

## 2. Структура данных

### 2.1. NewsPost (для создания/редактирования)

```typescript
interface NewsPostWrite {
  title: string;                    // Обязательно, не пустое
  body: string;                     // Обязательно, не пустое (HTML)
  pub_date: string;                 // ISO 8601 формат (YYYY-MM-DDTHH:mm:ssZ)
  status: 'draft' | 'scheduled' | 'published';  // По умолчанию: 'draft'
  source_language: 'ru' | 'en' | 'de' | 'pt';  // По умолчанию: 'ru'
  auto_translate?: boolean;          // По умолчанию: false
}
```

### 2.2. NewsPost (ответ от API)

```typescript
interface NewsPost {
  id: number;
  title: string;                     // Основной заголовок (язык по умолчанию)
  title_ru: string;                  // Заголовок на русском
  title_en: string;                  // Заголовок на английском
  title_de: string;                  // Заголовок на немецком
  title_pt: string;                  // Заголовок на португальском
  body: string;                      // Основной текст (HTML)
  body_ru: string;                   // Текст на русском
  body_en: string;                   // Текст на английском
  body_de: string;                   // Текст на немецком
  body_pt: string;                   // Текст на португальском
  pub_date: string;                  // ISO 8601
  status: 'draft' | 'scheduled' | 'published';
  source_language: 'ru' | 'en' | 'de' | 'pt';
  created_at: string;
  updated_at: string;
  author: {
    id: number;
    email: string;
    first_name: string;
    last_name: string;
  };
  media: Array<{
    id: number;
    file: string;
    media_type: 'image' | 'video';
  }>;
}
```

### 2.3. MediaUpload

```typescript
interface MediaUpload {
  id: number;
  file: string;                      // Путь к файлу
  url: string;                        // Полный URL файла
  media_type: 'image' | 'video';
  file_size: number;                 // Размер в байтах
  uploaded_by: number;                // ID пользователя
  created_at: string;
}
```

---

## 3. UI/UX Требования

### 3.1. Навигация

**Для администраторов должна быть доступна:**
- Кнопка/ссылка "Создать новость" в главном меню
- Раздел "Черновики" в меню
- Раздел "Запланированные" в меню
- Кнопки "Редактировать" и "Удалить" на карточках новостей

**Проверка прав администратора:**
```typescript
// После авторизации проверяем is_staff
const user = await getCurrentUser();
const isAdmin = user?.is_staff === true;
```

---

### 3.2. Страница создания/редактирования новости

#### Компоненты:

1. **WYSIWYG Редактор** (рекомендуется TipTap, Quill или Editor.js)
   - Панель инструментов:
     - Жирный, курсив, подчеркивание
     - Заголовки (H1-H6)
     - Списки (нумерованные, маркированные)
     - Ссылки
     - Вставка изображений
     - Вставка видео
   - Поддержка HTML-разметки
   - Автосохранение черновика (опционально)

2. **Форма публикации:**
   ```
   ┌─────────────────────────────────────┐
   │ Заголовок новости                    │
   │ [___________________________]        │
   │                                      │
   │ Редактор контента                    │
   │ ┌─────────────────────────────┐     │
   │ │                             │     │
   │ │  [Панель инструментов]      │     │
   │ │                             │     │
   │ │  [Текст новости...]          │     │
   │ │                             │     │
   │ └─────────────────────────────┘     │
   │                                      │
   │ Исходный язык: [RU ▼]               │
   │ ☑ Автоматический перевод            │
   │                                      │
   │ Статус: [Черновик ▼]                │
   │   - Черновик                        │
   │   - Запланировано                   │
   │   - Опубликовать сейчас             │
   │                                      │
   │ Дата публикации:                    │
   │ [2025-12-25] [10:00]                │
   │                                      │
   │ [Сохранить черновик] [Опубликовать] │
   └─────────────────────────────────────┘
   ```

3. **Загрузка медиа:**
   - Кнопка "Загрузить изображение/видео" в редакторе
   - Drag & Drop для загрузки файлов
   - Прогресс-бар при загрузке
   - Превью загруженных файлов
   - Вставка URL в редактор после загрузки

---

### 3.3. Страница списка новостей (для админов)

**Дополнительные элементы:**
- Фильтры: Все / Опубликованные / Черновики / Запланированные
- Поиск по заголовку
- Сортировка по дате
- Статус-бейджи на карточках новостей
- Кнопки действий: Редактировать, Удалить, Опубликовать

---

### 3.4. Страница черновиков

- Список всех черновиков
- Кнопка "Редактировать" на каждой карточке
- Кнопка "Опубликовать" на каждой карточке

---

### 3.5. Страница запланированных новостей

- Список всех запланированных новостей
- Отображение даты и времени публикации
- Кнопка "Опубликовать сейчас" (вызывает `/api/news/<id>/publish/`)

---

## 4. Обработка ошибок

### 4.1. Валидация формы

**Ошибки валидации (400 Bad Request):**
```json
{
  "title": ["Заголовок не может быть пустым."],
  "body": ["Текст новости не может быть пустым."],
  "status": ["Статус должен быть одним из: draft, scheduled, published."],
  "source_language": ["Исходный язык должен быть одним из: ru, en, de, pt."]
}
```

**Отображение:**
- Показывать ошибки под соответствующими полями
- Выделять поля с ошибками красной рамкой

### 4.2. Ошибки загрузки медиа

**Недопустимый формат (400):**
```json
{
  "file": ["Недопустимый формат файла. Разрешенные форматы: .jpg, .jpeg, .png, .gif, .webp, .mp4, .webm"]
}
```

**Превышен размер (400):**
```json
{
  "file": ["Размер изображения превышает лимит 10 MB."]
}
```

**Отображение:**
- Показывать toast-уведомление с ошибкой
- Не закрывать модальное окно загрузки при ошибке

### 4.3. Ошибки авторизации

**401 Unauthorized:**
- Перенаправлять на страницу входа
- Сохранять URL для возврата после авторизации

**403 Forbidden:**
- Показывать сообщение: "У вас нет прав для выполнения этого действия"
- Скрывать элементы интерфейса, требующие прав администратора

### 4.4. Ошибки перевода

**Если автоперевод не выполнился:**
- Новость все равно сохраняется
- Показывать предупреждение: "Автоматический перевод не выполнен. Новость сохранена без переводов."
- Предлагать повторить перевод вручную

---

## 5. Примеры реализации

### 5.1. Создание новости с автопереводом

```typescript
async function createNews(newsData: NewsPostWrite) {
  const response = await fetch('/api/news/', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${getToken()}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      title: newsData.title,
      body: newsData.body,
      source_language: newsData.source_language,
      pub_date: newsData.pub_date,
      status: newsData.status,
      auto_translate: newsData.auto_translate,
    }),
  });

  if (!response.ok) {
    const errors = await response.json();
    throw new ValidationError(errors);
  }

  return await response.json();
}
```

### 5.2. Загрузка медиафайла

```typescript
async function uploadMedia(file: File): Promise<MediaUpload> {
  const formData = new FormData();
  formData.append('file', file);
  
  // media_type опционален, определяется автоматически
  if (file.type.startsWith('image/')) {
    formData.append('media_type', 'image');
  } else if (file.type.startsWith('video/')) {
    formData.append('media_type', 'video');
  }

  const response = await fetch('/api/media/', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${getToken()}`,
    },
    body: formData,
  });

  if (!response.ok) {
    const errors = await response.json();
    throw new ValidationError(errors);
  }

  const media = await response.json();
  
  // Вставляем URL в редактор
  insertMediaIntoEditor(media.url, media.media_type);
  
  return media;
}
```

### 5.3. Получение черновиков

```typescript
async function getDrafts(): Promise<NewsPost[]> {
  const response = await fetch('/api/news/drafts/', {
    headers: {
      'Authorization': `Bearer ${getToken()}`,
    },
  });

  if (!response.ok) {
    throw new Error('Failed to fetch drafts');
  }

  return await response.json();
}
```

### 5.4. Публикация новости

```typescript
async function publishNews(newsId: number): Promise<NewsPost> {
  const response = await fetch(`/api/news/${newsId}/publish/`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${getToken()}`,
    },
  });

  if (!response.ok) {
    throw new Error('Failed to publish news');
  }

  return await response.json();
}
```

---

## 6. Логика работы статусов

### 6.1. Автоматическое изменение статуса

**Важно:** Бэкенд автоматически изменяет статус в зависимости от даты публикации:

- Если `status='published'` и `pub_date` в будущем → статус меняется на `'scheduled'`
- Если `status='scheduled'` и `pub_date` в прошлом → статус меняется на `'published'`

**Рекомендация для UI:**
- При выборе даты в будущем автоматически предлагать статус "Запланировано"
- При выборе даты в прошлом или "Сейчас" предлагать статус "Опубликовать"

### 6.2. Статусы новостей

| Статус | Описание | Видимость для обычных пользователей |
|--------|----------|-------------------------------------|
| `draft` | Черновик | Не видна |
| `scheduled` | Запланирована | Видна только если `pub_date <= now` |
| `published` | Опубликована | Видна если `pub_date <= now` |

---

## 7. Рекомендации по WYSIWYG редактору

### 7.1. TipTap (рекомендуется)

```typescript
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Image from '@tiptap/extension-image';
import Link from '@tiptap/extension-link';

const editor = useEditor({
  extensions: [
    StarterKit,
    Image.configure({
      inline: true,
      allowBase64: false,
    }),
    Link.configure({
      openOnClick: false,
    }),
  ],
  content: '<p>Начните писать...</p>',
});
```

**Интеграция загрузки изображений:**
```typescript
async function handleImageUpload(file: File) {
  const media = await uploadMedia(file);
  editor.chain().focus().setImage({ src: media.url }).run();
}
```

### 7.2. Альтернативы

- **Quill** - простой и легкий
- **Editor.js** - блочный редактор
- **Draft.js** - для React (требует больше настройки)

---

## 8. Чек-лист для тестирования

### 8.1. Функциональность

- [ ] Администратор может создать новость
- [ ] Обычный пользователь не видит кнопку "Создать новость"
- [ ] Обычный пользователь получает 403 при попытке создать новость
- [ ] Редактор сохраняет HTML-разметку
- [ ] Загрузка изображения работает и вставляет URL в редактор
- [ ] Загрузка видео работает и вставляет URL в редактор
- [ ] Валидация формы работает (пустые поля, недопустимые значения)
- [ ] Автоперевод заполняет все языковые поля
- [ ] При `auto_translate=false` переводы не выполняются
- [ ] Черновик сохраняется и не виден в публичном API
- [ ] Запланированная новость не видна до наступления даты
- [ ] Ручная публикация через `/publish/` работает
- [ ] Редактирование новости работает
- [ ] Удаление новости работает с подтверждением
- [ ] Список черновиков отображается корректно
- [ ] Список запланированных новостей отображается корректно

### 8.2. Обработка ошибок

- [ ] Ошибки валидации отображаются под полями
- [ ] Ошибка загрузки файла показывает понятное сообщение
- [ ] 401 ошибка перенаправляет на страницу входа
- [ ] 403 ошибка показывает сообщение о недостатке прав
- [ ] Ошибка перевода не блокирует сохранение новости

### 8.3. UI/UX

- [ ] Интерфейс интуитивно понятен
- [ ] Загрузка файлов показывает прогресс
- [ ] Автосохранение черновика работает (опционально)
- [ ] Дата и время публикации выбираются удобно
- [ ] Статусы новостей отображаются понятно (бейджи, цвета)
- [ ] Мобильная версия работает корректно

---

## 9. Дополнительные рекомендации

### 9.1. Автосохранение черновиков

Реализовать автосохранение каждые 30 секунд или при потере фокуса:

```typescript
useEffect(() => {
  const interval = setInterval(() => {
    if (hasUnsavedChanges) {
      saveDraft();
    }
  }, 30000);
  
  return () => clearInterval(interval);
}, [hasUnsavedChanges]);
```

### 9.2. Предпросмотр новости

Добавить кнопку "Предпросмотр" для просмотра новости в том виде, как она будет отображаться на сайте.

### 9.3. История изменений

В будущем можно добавить отображение истории изменений новости (когда была создана, когда последний раз редактировалась).

### 9.4. Массовые операции

Для админов можно добавить:
- Массовое удаление новостей
- Массовая публикация черновиков
- Массовое изменение статуса

---

## 10. Примеры запросов (cURL)

### Создание новости
```bash
curl -X POST http://localhost:8000/api/news/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Тестовая новость",
    "body": "<p>Это тестовая новость</p>",
    "source_language": "ru",
    "pub_date": "2025-12-25T10:00:00Z",
    "status": "draft",
    "auto_translate": true
  }'
```

### Загрузка изображения
```bash
curl -X POST http://localhost:8000/api/media/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -F "file=@/path/to/image.jpg" \
  -F "media_type=image"
```

### Получение черновиков
```bash
curl -X GET http://localhost:8000/api/news/drafts/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### Публикация новости
```bash
curl -X POST http://localhost:8000/api/news/123/publish/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

---

## Заключение

Это техническое задание покрывает все аспекты реализации веб-редактора новостей для фронтенда. При возникновении вопросов или необходимости уточнений, обращайтесь к бэкенд-разработчику.

**Приоритет реализации:**
1. CRUD операции с новостями
2. Загрузка медиафайлов
3. Черновики и отложенная публикация
4. Автоперевод (можно реализовать последним)

**Время на реализацию (оценка):**
- Базовый CRUD: 2-3 дня
- Загрузка медиа: 1 день
- Черновики и статусы: 1 день
- Автоперевод: 1 день
- Полировка и тестирование: 2 дня

**Итого:** ~7-8 рабочих дней

