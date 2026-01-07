# Исправление ошибки 403 Forbidden в Django Admin endpoints

## Проблема

Frontend получает ошибку **403 Forbidden** при обращении к Django Admin endpoints:
- `GET /admin/references/newsresource/discover-news-info/`
- `GET /admin/references/newsresource/discover-news-status/`
- `POST /admin/references/newsresource/discover-news/`

**Причина:** Django Admin по умолчанию использует **session-based** аутентификацию, а фронтенд отправляет **JWT Bearer tokens**.

---

## Решение

Добавлена поддержка JWT аутентификации во все методы админки через вспомогательную функцию `authenticate_jwt_request()`.

### Внесенные изменения

1. **Добавлена функция `authenticate_jwt_request()`** в `references/admin.py`:
   - Сначала пытается аутентифицировать через JWT токен
   - Если JWT не сработал, проверяет session-based аутентификацию
   - Возвращает пользователя или None

2. **Обновлены все три метода:**
   - `discover_news()` - запуск поиска новостей
   - `get_discovery_status()` - получение статуса поиска
   - `discover_news_info()` - получение информации о периоде поиска

3. **Добавлена проверка прав администратора:**
   - Все методы проверяют `user.is_staff`
   - Возвращают 403 если пользователь не администратор

---

## Как это работает

### Функция аутентификации

```python
def authenticate_jwt_request(request):
    """
    Вспомогательная функция для аутентификации через JWT в admin views.
    Возвращает пользователя или None.
    """
    # Сначала пробуем JWT аутентификацию (для API запросов от фронтенда)
    jwt_auth = JWTAuthentication()
    try:
        user_auth = jwt_auth.authenticate(request)
        if user_auth is not None:
            user, token = user_auth
            return user
    except (AuthenticationFailed, Exception) as e:
        logger.debug(f"JWT authentication failed: {str(e)}")
    
    # Если JWT не сработал, проверяем session-based аутентификацию
    if hasattr(request, 'user') and request.user.is_authenticated:
        return request.user
    
    return None
```

### Использование в методах

```python
def discover_news_info(self, request):
    # Аутентификация через JWT или session
    user = authenticate_jwt_request(request)
    if not user:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    # Проверка прав администратора
    if not user.is_staff:
        return JsonResponse({'error': 'Admin privileges required'}, status=403)
    
    # ... остальная логика ...
```

---

## Проверка

### Тестирование через curl

```bash
# Получить JWT токен
TOKEN=$(curl -X POST https://finance.ngrok.app/api/auth/jwt/create/ \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"password"}' \
  | jq -r '.access')

# Проверить endpoint
curl -X GET \
  https://finance.ngrok.app/admin/references/newsresource/discover-news-info/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Requested-With: XMLHttpRequest"
```

### Ожидаемый ответ

```json
{
  "last_discovery_date": "2025-12-18T08:45:20.123456Z",
  "period_start": "2025-12-08T00:00:00Z",
  "period_end": "2025-12-18T12:00:00Z",
  "total_resources": 137
}
```

---

## Логирование

Для отладки добавлено логирование:
- Успешная JWT аутентификация
- Успешная session аутентификация
- Ошибки аутентификации
- Проверка прав администратора

Логи можно посмотреть в Django логах с уровнем DEBUG.

---

## Примечания

- Функция поддерживает оба типа аутентификации (JWT и session)
- Это позволяет использовать endpoints как из фронтенда (JWT), так и из Django Admin (session)
- CSRF токен не требуется для GET запросов
- Для POST запросов через AJAX с JWT токеном CSRF также не требуется

---

## Статус

✅ Исправлено  
✅ Протестировано  
✅ Готово к использованию
