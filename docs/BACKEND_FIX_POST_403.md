# Исправление ошибки 403 Forbidden для POST запроса discover_news()

## Проблема

Frontend получает ошибку **403 Forbidden** при POST запросе к `/admin/references/newsresource/discover-news/`.

**Причина:** Метод `discover_news()` вызывается через Django Admin routing, который блокирует JWT аутентификацию для POST запросов.

---

## Решение

Создать отдельные view-обертки с `@csrf_exempt` для всех трех методов и убрать их из admin routing.

---

## Изменения в `references/admin.py`

### Обновить метод `get_urls()` в классе NewsResourceAdmin

**БЫЛО:**
```python
def get_urls(self):
    urls = super().get_urls()
    from django.urls import path
    my_urls = [
        path('discover-news/', self.discover_news, name='references_newsresource_discover'),
        path('discover-news-status/', self.get_discovery_status, name='references_newsresource_discover_status'),
        path('discover-news-info/', self.discover_news_info, name='references_newsresource_discover_info'),
    ]
    return my_urls + urls
```

**СТАЛО:**
```python
def get_urls(self):
    urls = super().get_urls()
    from django.urls import path
    
    # Создаем view-обертки с @csrf_exempt для поддержки JWT и AJAX запросов
    @csrf_exempt
    def discover_news_wrapper(request):
        """View-обертка для discover_news с JWT поддержкой"""
        return self.discover_news(request)
    
    @csrf_exempt
    def discover_news_status_wrapper(request):
        """View-обертка для get_discovery_status с JWT поддержкой"""
        return self.get_discovery_status(request)
    
    @csrf_exempt
    def discover_news_info_wrapper(request):
        """View-обертка для discover_news_info с JWT поддержкой"""
        return self.discover_news_info(request)
    
    my_urls = [
        path('discover-news/', discover_news_wrapper, name='references_newsresource_discover'),
        path('discover-news-status/', discover_news_status_wrapper, name='references_newsresource_discover_status'),
        path('discover-news-info/', discover_news_info_wrapper, name='references_newsresource_discover_info'),
    ]
    return my_urls + urls
```

**ВАЖНО:** 
- Используем локальные функции-обертки внутри `get_urls()` с декоратором `@csrf_exempt`
- Обертки вызывают методы класса через `self.discover_news(request)`
- Это позволяет обойти Django Admin middleware, который блокирует JWT токены

---

## Полный код изменений

### Импорты (в начале файла)

```python
from django.views.decorators.csrf import csrf_exempt
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed
```

### Функция аутентификации (уже должна быть)

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
            logger.debug(f"JWT authentication successful for user: {user.email}")
            return user
    except (AuthenticationFailed, Exception) as e:
        logger.debug(f"JWT authentication failed: {str(e)}")
    
    # Если JWT не сработал, проверяем session-based аутентификацию
    if hasattr(request, 'user') and request.user.is_authenticated:
        logger.debug(f"Session authentication successful for user: {request.user.email}")
        return request.user
    
    logger.debug("No authentication found")
    return None
```

### Обновленный метод get_urls() в классе NewsResourceAdmin

**ВАЖНО:** View-обертки определяются **внутри** метода `get_urls()` как локальные функции. Это позволяет использовать `self` для доступа к методам класса.

```python
def get_urls(self):
    urls = super().get_urls()
    from django.urls import path
    
    # Создаем view-обертки с @csrf_exempt для поддержки JWT и AJAX запросов
    @csrf_exempt
    def discover_news_wrapper(request):
        """View-обертка для discover_news с JWT поддержкой"""
        return self.discover_news(request)
    
    @csrf_exempt
    def discover_news_status_wrapper(request):
        """View-обертка для get_discovery_status с JWT поддержкой"""
        return self.get_discovery_status(request)
    
    @csrf_exempt
    def discover_news_info_wrapper(request):
        """View-обертка для discover_news_info с JWT поддержкой"""
        return self.discover_news_info(request)
    
    my_urls = [
        path('discover-news/', discover_news_wrapper, name='references_newsresource_discover'),
        path('discover-news-status/', discover_news_status_wrapper, name='references_newsresource_discover_status'),
        path('discover-news-info/', discover_news_info_wrapper, name='references_newsresource_discover_info'),
    ]
    return my_urls + urls
```

---

## Почему это работает

1. **`@csrf_exempt`** - отключает проверку CSRF токена для этих endpoints (обязательно для AJAX POST запросов)
2. **Локальные функции-обертки** - определены внутри `get_urls()`, имеют доступ к `self` через замыкание
3. **Прямой вызов методов** - `self.discover_news(request)` вызывает метод напрямую, минуя Django Admin middleware
4. **JWT аутентификация** - работает через `authenticate_jwt_request()` внутри методов класса
5. **Нет `admin_site.admin_view()`** - обертки не проходят через admin view wrapper, который блокирует JWT токены

---

## Проверка после исправления

### Тест POST запроса:

```bash
# Получить JWT токен
TOKEN=$(curl -X POST https://finance.ngrok.app/api/auth/jwt/create/ \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"password"}' \
  | jq -r '.access')

# Проверить POST endpoint
curl -X POST \
  https://finance.ngrok.app/admin/references/newsresource/discover-news/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Requested-With: XMLHttpRequest" \
  -H "Content-Type: application/json"
```

### Ожидаемый ответ:

```json
{
  "status": "running",
  "processed": 0,
  "total": 137,
  "percent": 0
}
```

---

## Важные моменты

1. ✅ Все три метода должны использовать view-обертки
2. ✅ `@csrf_exempt` обязателен для POST запросов через AJAX
3. ✅ Методы класса остаются без изменений (они уже используют `authenticate_jwt_request()`)
4. ✅ View-обертки определены внутри `get_urls()` как локальные функции с доступом к `self`
5. ✅ Обертки вызывают методы класса напрямую через `self.method_name(request)`

---

## Статус

После применения этих изменений:
- ✅ POST запросы будут работать с JWT токенами
- ✅ GET запросы продолжат работать
- ✅ CSRF не будет блокировать AJAX запросы
- ✅ JWT аутентификация будет работать для всех методов
