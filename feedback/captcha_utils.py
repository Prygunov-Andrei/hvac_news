import requests
from django.conf import settings
from django.core.exceptions import ValidationError


def verify_hcaptcha(token, remoteip=None):
    """
    Проверка hCaptcha токена через API.
    
    Args:
        token: Токен, полученный от фронтенда
        remoteip: IP адрес пользователя (опционально)
    
    Returns:
        bool: True если CAPTCHA валидна, False иначе
    
    Raises:
        ValidationError: Если произошла ошибка при проверке
    """
    secret_key = getattr(settings, 'HCAPTCHA_SECRET_KEY', None)
    
    if not secret_key:
        # В режиме разработки без ключа пропускаем проверку
        if settings.DEBUG:
            return True
        raise ValidationError('HCAPTCHA_SECRET_KEY is not configured')
    
    if not token:
        return False
    
    data = {
        'secret': secret_key,
        'response': token,
    }
    
    if remoteip:
        data['remoteip'] = remoteip
    
    try:
        response = requests.post(
            'https://hcaptcha.com/siteverify',
            data=data,
            timeout=5
        )
        result = response.json()
        return result.get('success', False)
    except requests.RequestException as e:
        # В режиме разработки пропускаем ошибки сети
        if settings.DEBUG:
            return True
        raise ValidationError(f'Error verifying CAPTCHA: {str(e)}')


def verify_recaptcha(token, remoteip=None):
    """
    Проверка Google ReCaptcha токена через API.
    
    Args:
        token: Токен, полученный от фронтенда
        remoteip: IP адрес пользователя (опционально)
    
    Returns:
        bool: True если CAPTCHA валидна, False иначе
    
    Raises:
        ValidationError: Если произошла ошибка при проверке
    """
    secret_key = getattr(settings, 'RECAPTCHA_SECRET_KEY', None)
    
    if not secret_key:
        # В режиме разработки без ключа пропускаем проверку
        if settings.DEBUG:
            return True
        raise ValidationError('RECAPTCHA_SECRET_KEY is not configured')
    
    if not token:
        return False
    
    data = {
        'secret': secret_key,
        'response': token,
    }
    
    if remoteip:
        data['remoteip'] = remoteip
    
    try:
        response = requests.post(
            'https://www.google.com/recaptcha/api/siteverify',
            data=data,
            timeout=5
        )
        result = response.json()
        return result.get('success', False)
    except requests.RequestException as e:
        # В режиме разработки пропускаем ошибки сети
        if settings.DEBUG:
            return True
        raise ValidationError(f'Error verifying CAPTCHA: {str(e)}')


def verify_captcha(token, captcha_type='hcaptcha', remoteip=None):
    """
    Универсальная функция для проверки CAPTCHA.
    
    Args:
        token: Токен, полученный от фронтенда
        captcha_type: Тип CAPTCHA ('hcaptcha' или 'recaptcha')
        remoteip: IP адрес пользователя (опционально)
    
    Returns:
        bool: True если CAPTCHA валидна, False иначе
    """
    if captcha_type == 'hcaptcha':
        return verify_hcaptcha(token, remoteip)
    elif captcha_type == 'recaptcha':
        return verify_recaptcha(token, remoteip)
    else:
        # В режиме разработки пропускаем неизвестный тип
        if settings.DEBUG:
            return True
        return False

