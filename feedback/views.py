import logging
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.core.mail import send_mail
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from .models import Feedback
from .serializers import FeedbackSerializer
from .captcha_utils import verify_captcha

logger = logging.getLogger(__name__)


@api_view(['POST'])
@permission_classes([AllowAny])
def create_feedback(request):
    """
    Создание обратной связи.
    Доступно всем пользователям (включая анонимных).
    Требуется валидация CAPTCHA.
    """
    serializer = FeedbackSerializer(data=request.data)
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    # Валидация CAPTCHA
    captcha_token = serializer.validated_data.pop('captcha', None)
    if not captcha_token:
        return Response(
            {'captcha': ['CAPTCHA is required.']},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Проверка CAPTCHA
    captcha_type = getattr(settings, 'CAPTCHA_TYPE', 'hcaptcha')
    remoteip = request.META.get('REMOTE_ADDR')
    
    if not verify_captcha(captcha_token, captcha_type, remoteip):
        return Response(
            {'captcha': ['CAPTCHA verification failed. Please try again.']},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Создаем запись обратной связи
    feedback = serializer.save()
    
    # Отправляем email администратору
    try:
        admin_email = getattr(settings, 'ADMIN_EMAIL', settings.DEFAULT_FROM_EMAIL)
        subject = _('New feedback from HVAC News website')
        message = _(
            'You have received a new feedback message:\n\n'
            'From: {name} ({email})\n'
            'Message:\n{message}\n\n'
            '---\n'
            'Sent from HVAC News website'
        ).format(
            name=feedback.name or _('Anonymous'),
            email=feedback.email,
            message=feedback.message
        )
        
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [admin_email],
            fail_silently=False,
        )
    except Exception as e:
        # Логируем ошибку, но не прерываем процесс
        logger.error(f"Error sending feedback email: {e}", exc_info=True)
    
    return Response(
        {
            'message': _('Thank you for your feedback! We will contact you soon.'),
            'id': feedback.id
        },
        status=status.HTTP_201_CREATED
    )
