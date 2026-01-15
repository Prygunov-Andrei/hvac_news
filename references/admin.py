import os
import re
import logging
from datetime import datetime
from django.contrib import admin
from django.conf import settings
from django.contrib import messages
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed
from modeltranslation.admin import TranslationAdmin
from .models import Manufacturer, Brand, NewsResource, NewsResourceStatistics, ManufacturerStatistics
from news.models import NewsDiscoveryRun, NewsDiscoveryStatus

logger = logging.getLogger(__name__)


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
        # Продолжаем проверку session-based аутентификации
    
    # Если JWT не сработал, проверяем session-based аутентификацию (для обычного Django Admin)
    if hasattr(request, 'user') and request.user.is_authenticated:
        logger.debug(f"Session authentication successful for user: {request.user.email}")
        return request.user
    
    logger.debug("No authentication found")
    return None

@admin.register(Manufacturer)
class ManufacturerAdmin(TranslationAdmin):
    list_display = ('name', 'region', 'statistics_display', 'ranking_score_display', 'is_active_display', 'websites_display')
    list_display_links = ('name',)
    search_fields = ('name', 'region', 'description')
    list_filter = ('region', 'statistics__is_active')
    list_per_page = 50
    ordering = ['-statistics__ranking_score', 'name']
    change_list_template = "admin/manufacturer_changelist.html"
    
    def get_urls(self):
        urls = super().get_urls()
        from django.urls import path
        
        # Создаем view-обертки с @csrf_exempt для поддержки JWT и AJAX запросов
        @csrf_exempt
        def discover_manufacturers_news_wrapper(request):
            """View-обертка для discover_manufacturers_news с JWT поддержкой"""
            return self.discover_manufacturers_news(request)
        
        @csrf_exempt
        def discover_manufacturers_status_wrapper(request):
            """View-обертка для get_manufacturers_discovery_status с JWT поддержкой"""
            return self.get_manufacturers_discovery_status(request)
        
        @csrf_exempt
        def discover_manufacturers_info_wrapper(request):
            """View-обертка для discover_manufacturers_info с JWT поддержкой"""
            return self.discover_manufacturers_info(request)
        
        my_urls = [
            path('discover-manufacturers-news/', discover_manufacturers_news_wrapper, name='references_manufacturer_discover'),
            path('discover-manufacturers-status/', discover_manufacturers_status_wrapper, name='references_manufacturer_discover_status'),
            path('discover-manufacturers-info/', discover_manufacturers_info_wrapper, name='references_manufacturer_discover_info'),
        ]
        return my_urls + urls
    
    def websites_display(self, obj):
        """Отображение сайтов производителя"""
        websites = []
        if obj.website_1:
            websites.append(format_html('<a href="{}" target="_blank">{}</a>', obj.website_1, '1'))
        if obj.website_2:
            websites.append(format_html('<a href="{}" target="_blank">{}</a>', obj.website_2, '2'))
        if obj.website_3:
            websites.append(format_html('<a href="{}" target="_blank">{}</a>', obj.website_3, '3'))
        return format_html(', '.join(websites)) if websites else '-'
    websites_display.short_description = _('Сайты')
    
    def statistics_display(self, obj):
        """Отображение статистики производителя"""
        try:
            stats = obj.statistics
            return format_html(
                '<div style="font-size: 11px;">'
                '📰 Новостей: <strong>{}</strong><br/>'
                '🔍 Поисков: <strong>{}</strong><br/>'
                '✅ Успешность: <strong>{:.1f}%</strong><br/>'
                '📅 За 30 дней: <strong>{}</strong>'
                '</div>',
                stats.total_news_found,
                stats.total_searches,
                stats.success_rate,
                stats.news_last_30_days
            )
        except ManufacturerStatistics.DoesNotExist:
            return format_html('<span style="color: #999;">Нет данных</span>')
    statistics_display.short_description = _('Статистика')
    
    def ranking_score_display(self, obj):
        """Отображение рейтинга"""
        try:
            stats = obj.statistics
            color = '#28a745' if stats.ranking_score >= 50 else '#ffc107' if stats.ranking_score >= 20 else '#dc3545'
            return format_html(
                '<span style="color: {}; font-weight: bold;">{:.1f}</span>',
                color,
                stats.ranking_score
            )
        except ManufacturerStatistics.DoesNotExist:
            return format_html('<span style="color: #999;">-</span>')
    ranking_score_display.short_description = _('Рейтинг')
    ranking_score_display.admin_order_field = 'statistics__ranking_score'
    
    def is_active_display(self, obj):
        """Отображение статуса активности"""
        try:
            stats = obj.statistics
            if stats.is_active:
                return format_html('<span style="color: #28a745;">✓ Активен</span>')
            else:
                return format_html('<span style="color: #dc3545;">✗ Неактивен</span>')
        except ManufacturerStatistics.DoesNotExist:
            return format_html('<span style="color: #999;">-</span>')
    is_active_display.short_description = _('Статус')
    is_active_display.admin_order_field = 'statistics__is_active'
    
    def discover_manufacturers_news(self, request):
        """Запускает поиск новостей для всех производителей"""
        from news.discovery_service import NewsDiscoveryService
        
        # Аутентификация через JWT или session
        user = authenticate_jwt_request(request)
        if not user:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': 'Authentication required'}, status=401)
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        
        # Проверка прав администратора
        if not user.is_staff:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': 'Admin privileges required'}, status=403)
            return JsonResponse({'error': 'Permission denied'}, status=403)
        
        request.user = user
        
        if request.method == 'POST':
            # Получаем выбранный провайдер из POST запроса
            provider = request.POST.get('provider', 'auto')
            if provider not in ['auto', 'grok', 'anthropic', 'openai']:
                provider = 'auto'
            
            # Создаем статус для отслеживания прогресса
            manufacturer_count = Manufacturer.objects.count()
            status_obj = NewsDiscoveryStatus.create_new_status(manufacturer_count, search_type='manufacturers', provider=provider)
            
            # Если это AJAX запрос - запускаем поиск в фоне
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                import threading
                
                def run_discovery():
                    try:
                        service = NewsDiscoveryService(user=request.user)
                        service.discover_all_manufacturers_news(status_obj=status_obj)
                    except Exception as e:
                        logger.error(f"Error during manufacturers news discovery: {str(e)}")
                        status_obj.status = 'error'
                        status_obj.save()
                
                thread = threading.Thread(target=run_discovery)
                thread.daemon = True
                thread.start()
                
                return JsonResponse({
                    'status': 'running',
                    'processed': 0,
                    'total': manufacturer_count,
                    'percent': 0
                })
            
            # Если это обычный POST - запускаем синхронно
            try:
                service = NewsDiscoveryService(user=request.user)
                stats = service.discover_all_manufacturers_news(status_obj=status_obj)
                
                self.message_user(
                    request,
                    _('Поиск новостей по производителям завершен. Создано новостей: {}, ошибок: {}, обработано производителей: {}').format(
                        stats['created'], stats['errors'], stats['total_processed']
                    ),
                    level=messages.SUCCESS
                )
            except Exception as e:
                logger.error(f"Error during manufacturers news discovery: {str(e)}")
                self.message_user(
                    request,
                    _('Ошибка при поиске новостей по производителям: {}').format(str(e)),
                    level=messages.ERROR
                )
            
            from django.shortcuts import redirect
            return redirect(request.path)
        
        # GET запрос - показываем страницу подтверждения
        from django.shortcuts import render
        last_search_date = NewsDiscoveryRun.get_last_search_date()
        today = timezone.now().date()
        manufacturer_count = Manufacturer.objects.count()
        
        context = {
            'title': _('Поиск новостей по производителям'),
            'opts': self.model._meta,
            'last_search_date': last_search_date,
            'today': today,
            'manufacturer_count': manufacturer_count,
        }
        return render(request, 'admin/discover_manufacturers_news.html', context)
    
    def get_manufacturers_discovery_status(self, request):
        """API endpoint для получения текущего статуса поиска по производителям"""
        user = authenticate_jwt_request(request)
        if not user:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        
        if not user.is_staff:
            return JsonResponse({'error': 'Admin privileges required'}, status=403)
        
        status_obj = NewsDiscoveryStatus.objects.filter(search_type='manufacturers').order_by('-created_at').first()
        if status_obj:
            return JsonResponse({
                'processed': status_obj.processed_count,
                'total': status_obj.total_count,
                'status': status_obj.status,
                'percent': status_obj.get_progress_percent()
            })
        else:
            return JsonResponse({
                'processed': 0,
                'total': 0,
                'status': 'none',
                'percent': 0
            })
    
    def discover_manufacturers_info(self, request):
        """Получить информацию о последнем поиске новостей по производителям"""
        user = authenticate_jwt_request(request)
        if not user:
            logger.warning(f"discover_manufacturers_info: Authentication failed. Headers: {dict(request.headers)}")
            return JsonResponse({'error': 'Authentication required'}, status=401)
        
        if not user.is_staff:
            logger.warning(f"discover_manufacturers_info: User {user.email} is not staff")
            return JsonResponse({'error': 'Admin privileges required'}, status=403)
        
        last_status = NewsDiscoveryStatus.objects.order_by('-created_at').first()
        last_discovery_date = last_status.created_at if last_status else None
        
        last_run = NewsDiscoveryRun.objects.first()
        period_start = None
        if last_run:
            period_start = timezone.make_aware(
                datetime.combine(last_run.last_search_date, datetime.min.time())
            )
        
        period_end = timezone.now()
        total_manufacturers = Manufacturer.objects.count()
        
        return JsonResponse({
            'last_discovery_date': last_discovery_date.isoformat() if last_discovery_date else None,
            'period_start': period_start.isoformat() if period_start else None,
            'period_end': period_end.isoformat(),
            'total_manufacturers': total_manufacturers
        })

@admin.register(Brand)
class BrandAdmin(TranslationAdmin):
    list_display = ('name', 'manufacturer')
    search_fields = ('name', 'manufacturer__name')
    list_filter = ('manufacturer',)

@admin.register(NewsResource)
class NewsResourceAdmin(TranslationAdmin):
    list_display = ('name', 'section', 'language_display', 'source_type_display', 'url_link', 'statistics_display', 'ranking_score_display', 'is_active_display', 'has_logo')
    list_display_links = ('name',)
    search_fields = ('name', 'url', 'description', 'section')
    list_filter = ('language', 'source_type', 'section', 'statistics__is_active', 'statistics__error_rate')
    list_per_page = 50
    actions = ['delete_selected', 'mark_as_manual', 'mark_as_auto', 'mark_as_hybrid', 'discover_selected_resources']
    ordering = ['-statistics__ranking_score', 'name']
    fieldsets = (
        (_('Основная информация'), {
            'fields': ('name', 'url', 'section', 'description')
        }),
        (_('Настройки поиска'), {
            'fields': ('source_type', 'language', 'custom_search_instructions'),
            'description': _('Источники типа "Ручной ввод" пропускаются при автоматическом поиске. '
                           'Для источников типа "Гибридный" используются кастомные инструкции. '
                           'Язык источника определяет язык промпта для LLM.')
        }),
        (_('Служебная информация'), {
            'fields': ('internal_notes',),
            'description': _('Служебные заметки о источнике. Видны только администраторам.')
        }),
        (_('Медиа'), {
            'fields': ('logo',)
        }),
    )
    change_list_template = "admin/newsresource_changelist.html"
    
    def source_type_display(self, obj):
        """Отображение типа источника с цветовой индикацией"""
        colors = {
            'auto': '#28a745',  # зеленый
            'manual': '#dc3545',  # красный
            'hybrid': '#ffc107',  # желтый
        }
        icons = {
            'auto': '🤖',
            'manual': '✋',
            'hybrid': '⚙️',
        }
        color = colors.get(obj.source_type, '#6c757d')
        icon = icons.get(obj.source_type, '')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{} {}</span>',
            color,
            icon,
            obj.get_source_type_display()
        )
    source_type_display.short_description = _('Тип поиска')
    source_type_display.admin_order_field = 'source_type'
    
    def language_display(self, obj):
        """Отображение языка источника с флагом"""
        flags = {
            'ru': '🇷🇺',
            'en': '🇺🇸',
            'es': '🇪🇸',
            'de': '🇩🇪',
            'pt': '🇵🇹',
            'fr': '🇫🇷',
            'it': '🇮🇹',
            'tr': '🇹🇷',
            'ar': '🇸🇦',
            'zh': '🇨🇳',
            'ja': '🇯🇵',
            'ko': '🇰🇷',
            'pl': '🇵🇱',
            'nl': '🇳🇱',
            'sv': '🇸🇪',
            'other': '🌐',
        }
        flag = flags.get(obj.language, '🌐')
        return format_html(
            '<span>{} {}</span>',
            flag,
            obj.get_language_display()
        )
    language_display.short_description = _('Язык')
    language_display.admin_order_field = 'language'
    
    @admin.action(description=_('Пометить как "Ручной ввод"'))
    def mark_as_manual(self, request, queryset):
        updated = queryset.update(source_type='manual')
        self.message_user(request, f'{updated} источников помечены как "Ручной ввод"')
    
    @admin.action(description=_('Пометить как "Автоматический поиск"'))
    def mark_as_auto(self, request, queryset):
        updated = queryset.update(source_type='auto')
        self.message_user(request, f'{updated} источников помечены как "Автоматический поиск"')
    
    @admin.action(description=_('Пометить как "Гибридный"'))
    def mark_as_hybrid(self, request, queryset):
        updated = queryset.update(source_type='hybrid')
        self.message_user(request, f'{updated} источников помечены как "Гибридный"')
    
    @admin.action(description=_('Запустить поиск новостей для выбранных источников'))
    def discover_selected_resources(self, request, queryset):
        """Запускает поиск новостей для выбранных источников"""
        from news.discovery_service import NewsDiscoveryService
        
        # Получаем выбранный провайдер из POST запроса (может быть передан через action_form)
        provider = request.POST.get('provider', 'auto')
        if provider not in ['auto', 'grok', 'anthropic', 'openai']:
            provider = 'auto'
        
        # Фильтруем только источники с автоматическим или гибридным поиском
        resources = queryset.exclude(source_type=NewsResource.SOURCE_TYPE_MANUAL)
        resource_ids = list(resources.values_list('id', flat=True))
        
        if not resource_ids:
            self.message_user(
                request,
                _('Нет источников для поиска. Все выбранные источники требуют ручного ввода.'),
                level=messages.WARNING
            )
            return
        
        # Создаем статус для отслеживания прогресса
        status_obj = NewsDiscoveryStatus.create_new_status(
            total_count=len(resource_ids),
            search_type='resources',
            provider=provider
        )
        
        # Запускаем поиск в фоне
        import threading
        
        def run_discovery():
            try:
                service = NewsDiscoveryService(user=request.user)
                # Обрабатываем только выбранные источники
                for resource_id in resource_ids:
                    try:
                        resource = NewsResource.objects.get(id=resource_id)
                        service.discover_news_for_resource(resource, provider=provider)
                        # Обновляем прогресс
                        status_obj.processed_count += 1
                        status_obj.save()
                    except NewsResource.DoesNotExist:
                        continue
                    except Exception as e:
                        logger.error(f"Error processing resource {resource_id}: {str(e)}")
                        status_obj.processed_count += 1
                        status_obj.save()
                
                status_obj.status = 'completed'
                status_obj.save()
            except Exception as e:
                logger.error(f"Error during selected resources discovery: {str(e)}")
                status_obj.status = 'error'
                status_obj.save()
        
        thread = threading.Thread(target=run_discovery)
        thread.daemon = True
        thread.start()
        
        provider_display = dict(NewsDiscoveryStatus._meta.get_field('provider').choices).get(provider, provider)
        self.message_user(
            request,
            _('Поиск новостей запущен для {} источников. Провайдер: {}').format(
                len(resource_ids),
                provider_display
            ),
            level=messages.SUCCESS
        )
    
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
        
        @csrf_exempt
        def discover_single_resource_wrapper(request, resource_id):
            """View-обертка для discover_single_resource с JWT поддержкой"""
            return self.discover_single_resource(request, resource_id)
        
        my_urls = [
            path('discover-news/', discover_news_wrapper, name='references_newsresource_discover'),
            path('discover-news-status/', discover_news_status_wrapper, name='references_newsresource_discover_status'),
            path('discover-news-info/', discover_news_info_wrapper, name='references_newsresource_discover_info'),
            path('<int:resource_id>/discover/', discover_single_resource_wrapper, name='references_newsresource_discover_single'),
        ]
        return my_urls + urls
    
    def discover_news(self, request):
        """Запускает поиск новостей для всех источников"""
        from news.discovery_service import NewsDiscoveryService
        
        # Аутентификация через JWT или session
        user = authenticate_jwt_request(request)
        if not user:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': 'Authentication required'}, status=401)
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        
        # Проверка прав администратора
        if not user.is_staff:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': 'Admin privileges required'}, status=403)
            return JsonResponse({'error': 'Permission denied'}, status=403)
        
        # Устанавливаем пользователя для дальнейшего использования
        request.user = user
        
        if request.method == 'POST':
            # Получаем выбранный провайдер из POST запроса
            provider = request.POST.get('provider', 'auto')
            if provider not in ['auto', 'grok', 'anthropic', 'openai']:
                provider = 'auto'
            
            # Создаем статус для отслеживания прогресса
            resource_count = NewsResource.objects.count()
            status_obj = NewsDiscoveryStatus.create_new_status(resource_count, search_type='resources', provider=provider)
            
            # Если это AJAX запрос - запускаем поиск в фоне и возвращаем статус
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                import threading
                
                def run_discovery():
                    try:
                        service = NewsDiscoveryService(user=request.user)
                        service.discover_all_news(status_obj=status_obj)
                    except Exception as e:
                        logger.error(f"Error during news discovery: {str(e)}")
                        status_obj.status = 'error'
                        status_obj.save()
                
                # Запускаем поиск в отдельном потоке
                thread = threading.Thread(target=run_discovery)
                thread.daemon = True
                thread.start()
                
                # Возвращаем начальный статус
                return JsonResponse({
                    'status': 'running',
                    'processed': 0,
                    'total': resource_count,
                    'percent': 0
                })
            
            # Если это обычный POST - запускаем синхронно (для совместимости)
            try:
                service = NewsDiscoveryService(user=request.user)
                stats = service.discover_all_news(status_obj=status_obj)
                
                self.message_user(
                    request,
                    _('Поиск новостей завершен. Создано новостей: {}, ошибок: {}, обработано источников: {}').format(
                        stats['created'], stats['errors'], stats['total_processed']
                    ),
                    level=messages.SUCCESS
                )
            except Exception as e:
                logger.error(f"Error during news discovery: {str(e)}")
                self.message_user(
                    request,
                    _('Ошибка при поиске новостей: {}').format(str(e)),
                    level=messages.ERROR
                )
            
            from django.shortcuts import redirect
            return redirect(request.path)
        
        # GET запрос - показываем страницу подтверждения
        from django.shortcuts import render
        last_search_date = NewsDiscoveryRun.get_last_search_date()
        today = timezone.now().date()
        resource_count = NewsResource.objects.count()
        
        context = {
            'title': _('Поиск новостей'),
            'opts': self.model._meta,
            'last_search_date': last_search_date,
            'today': today,
            'resource_count': resource_count,
        }
        return render(request, 'admin/discover_news.html', context)
    
    def discover_single_resource(self, request, resource_id):
        """Запускает поиск новостей для одного источника"""
        from news.discovery_service import NewsDiscoveryService
        
        # Аутентификация через JWT или session
        user = authenticate_jwt_request(request)
        if not user:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': 'Authentication required'}, status=401)
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        
        # Проверка прав администратора
        if not user.is_staff:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': 'Admin privileges required'}, status=403)
            return JsonResponse({'error': 'Permission denied'}, status=403)
        
        request.user = user
        
        try:
            resource = NewsResource.objects.get(id=resource_id)
        except NewsResource.DoesNotExist:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': 'Resource not found'}, status=404)
            self.message_user(request, _('Источник не найден'), level=messages.ERROR)
            from django.shortcuts import redirect
            return redirect('admin:references_newsresource_changelist')
        
        # Проверяем, что источник не требует ручного ввода
        if resource.source_type == NewsResource.SOURCE_TYPE_MANUAL:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'error': 'Этот источник требует ручного ввода и не может быть обработан автоматически'
                }, status=400)
            self.message_user(
                request,
                _('Источник "{}" требует ручного ввода и не может быть обработан автоматически').format(resource.name),
                level=messages.WARNING
            )
            from django.shortcuts import redirect
            return redirect('admin:references_newsresource_change', resource_id)
        
        if request.method == 'POST':
            # Получаем выбранный провайдер из POST запроса
            provider = request.POST.get('provider', 'auto')
            if provider not in ['auto', 'grok', 'anthropic', 'openai']:
                provider = 'auto'
            
            # Если это AJAX запрос - запускаем поиск в фоне
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                import threading
                
                def run_discovery():
                    try:
                        service = NewsDiscoveryService(user=request.user)
                        created, errors, error_msg = service.discover_news_for_resource(resource, provider=provider)
                        logger.info(f"Discovery completed for resource {resource_id}: created={created}, errors={errors}")
                    except Exception as e:
                        logger.error(f"Error during single resource discovery: {str(e)}")
                
                thread = threading.Thread(target=run_discovery)
                thread.daemon = True
                thread.start()
                
                return JsonResponse({
                    'status': 'running',
                    'resource_id': resource_id,
                    'resource_name': resource.name,
                    'provider': provider,
                    'message': _('Поиск новостей запущен для источника "{}"').format(resource.name)
                })
            
            # Если это обычный POST - запускаем синхронно
            try:
                service = NewsDiscoveryService(user=request.user)
                created, errors, error_msg = service.discover_news_for_resource(resource, provider=provider)
                
                if error_msg:
                    self.message_user(
                        request,
                        _('Ошибка при поиске новостей для источника "{}": {}').format(resource.name, error_msg),
                        level=messages.ERROR
                    )
                else:
                    self.message_user(
                        request,
                        _('Поиск новостей завершен для источника "{}". Создано: {}, ошибок: {}').format(
                            resource.name, created, errors
                        ),
                        level=messages.SUCCESS
                    )
            except Exception as e:
                logger.error(f"Error during single resource discovery: {str(e)}")
                self.message_user(
                    request,
                    _('Ошибка при поиске новостей: {}').format(str(e)),
                    level=messages.ERROR
                )
            
            from django.shortcuts import redirect
            return redirect('admin:references_newsresource_change', resource_id)
        
        # GET запрос - показываем страницу подтверждения (опционально)
        from django.shortcuts import render
        last_search_date = NewsDiscoveryRun.get_last_search_date()
        today = timezone.now().date()
        
        context = {
            'title': _('Поиск новостей для источника'),
            'opts': self.model._meta,
            'resource': resource,
            'last_search_date': last_search_date,
            'today': today,
        }
        return render(request, 'admin/discover_single_resource.html', context)
    
    def get_discovery_status(self, request):
        """API endpoint для получения текущего статуса поиска"""
        # Аутентификация через JWT или session
        user = authenticate_jwt_request(request)
        if not user:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        
        # Проверка прав администратора
        if not user.is_staff:
            return JsonResponse({'error': 'Admin privileges required'}, status=403)
        
        # Получаем последний статус для источников (может быть running или completed)
        status_obj = NewsDiscoveryStatus.objects.filter(search_type='resources').order_by('-created_at').first()
        if status_obj:
            return JsonResponse({
                'processed': status_obj.processed_count,
                'total': status_obj.total_count,
                'status': status_obj.status,
                'percent': status_obj.get_progress_percent()
            })
        else:
            return JsonResponse({
                'processed': 0,
                'total': 0,
                'status': 'none',
                'percent': 0
            })
    
    def discover_news_info(self, request):
        """Получить информацию о последнем поиске новостей"""
        # Аутентификация через JWT или session
        user = authenticate_jwt_request(request)
        if not user:
            logger.warning(f"discover_news_info: Authentication failed. Headers: {dict(request.headers)}")
            return JsonResponse({'error': 'Authentication required'}, status=401)
        
        # Проверка прав администратора
        if not user.is_staff:
            logger.warning(f"discover_news_info: User {user.email} is not staff")
            return JsonResponse({'error': 'Admin privileges required'}, status=403)
        
        logger.debug(f"discover_news_info: Successfully authenticated user {user.email}")
        
        # Последний запуск (любой статус) - берем по created_at
        last_status = NewsDiscoveryStatus.objects.order_by('-created_at').first()
        last_discovery_date = last_status.created_at if last_status else None
        
        # Последний успешный запуск - берем last_search_date из NewsDiscoveryRun
        last_run = NewsDiscoveryRun.objects.first()
        period_start = None
        if last_run and last_run.last_search_date:
            try:
                # Преобразуем date в datetime для начала дня
                period_start = timezone.make_aware(
                    datetime.combine(last_run.last_search_date, datetime.min.time())
                )
            except (AttributeError, TypeError) as e:
                logger.warning(f"Error creating period_start from last_run: {str(e)}")
                period_start = None
        
        # Текущая дата и время
        period_end = timezone.now()
        
        # Количество активных источников (все NewsResource, так как нет поля is_active)
        total_resources = NewsResource.objects.count()
        
        return JsonResponse({
            'last_discovery_date': last_discovery_date.isoformat() if last_discovery_date else None,
            'period_start': period_start.isoformat() if period_start else None,
            'period_end': period_end.isoformat(),
            'total_resources': total_resources
        })
    
    def url_link(self, obj):
        """Отображение URL как ссылки"""
        if obj.url:
            return format_html('<a href="{}" target="_blank">{}</a>', obj.url, obj.url[:50] + '...' if len(obj.url) > 50 else obj.url)
        return '-'
    url_link.short_description = _('URL')
    url_link.admin_order_field = 'url'
    
    def has_logo(self, obj):
        """Проверка наличия логотипа"""
        if obj.logo:
            return format_html('✓')
        return format_html('✗')
    has_logo.short_description = _('Логотип')
    has_logo.boolean = True
    
    def statistics_display(self, obj):
        """Отображение статистики источника"""
        try:
            stats = obj.statistics
            # Подсветка проблемных источников
            is_problematic = stats.error_rate >= 30
            error_style = 'color: #dc3545; font-weight: bold;' if is_problematic else ''
            error_indicator = '⚠️ ' if is_problematic else ''
            
            return format_html(
                '<div style="font-size: 11px;">'
                '📰 Новостей: <strong>{}</strong><br/>'
                '🔍 Поисков: <strong>{}</strong><br/>'
                '✅ Успешность: <strong>{:.1f}%</strong><br/>'
                '<span style="{}">{}Ошибок: <strong>{:.1f}%</strong></span><br/>'
                '📅 За 30 дней: <strong>{}</strong>'
                '</div>',
                stats.total_news_found,
                stats.total_searches,
                stats.success_rate,
                error_style,
                error_indicator,
                stats.error_rate,
                stats.news_last_30_days
            )
        except NewsResourceStatistics.DoesNotExist:
            return format_html('<span style="color: #999;">Нет данных</span>')
    statistics_display.short_description = _('Статистика')
    
    def ranking_score_display(self, obj):
        """Отображение рейтинга"""
        try:
            stats = obj.statistics
            color = '#28a745' if stats.ranking_score >= 50 else '#ffc107' if stats.ranking_score >= 20 else '#dc3545'
            return format_html(
                '<span style="color: {}; font-weight: bold;">{:.1f}</span>',
                color,
                stats.ranking_score
            )
        except NewsResourceStatistics.DoesNotExist:
            return format_html('<span style="color: #999;">-</span>')
    ranking_score_display.short_description = _('Рейтинг')
    ranking_score_display.admin_order_field = 'statistics__ranking_score'
    
    def is_active_display(self, obj):
        """Отображение статуса активности"""
        try:
            stats = obj.statistics
            if stats.is_active:
                return format_html('<span style="color: #28a745;">✓ Активен</span>')
            else:
                return format_html('<span style="color: #dc3545;">✗ Неактивен</span>')
        except NewsResourceStatistics.DoesNotExist:
            return format_html('<span style="color: #999;">-</span>')
    is_active_display.short_description = _('Статус')
    is_active_display.admin_order_field = 'statistics__is_active'


@admin.register(ManufacturerStatistics)
class ManufacturerStatisticsAdmin(admin.ModelAdmin):
    """Админка для статистики производителей (только для просмотра)"""
    list_display = (
        'manufacturer_name',
        'total_news_found',
        'total_searches',
        'success_rate',
        'ranking_score',
        'news_last_30_days',
        'is_active',
        'last_search_date'
    )
    list_filter = ('is_active', 'created_at', 'last_search_date')
    search_fields = ('manufacturer__name', 'manufacturer__region')
    readonly_fields = (
        'manufacturer',
        'total_news_found',
        'total_searches',
        'total_no_news',
        'total_errors',
        'success_rate',
        'error_rate',
        'avg_news_per_search',
        'news_last_30_days',
        'news_last_90_days',
        'searches_last_30_days',
        'ranking_score',
        'priority',
        'is_active',
        'last_search_date',
        'last_news_date',
        'first_search_date',
        'created_at',
        'updated_at'
    )
    ordering = ['-ranking_score', '-total_news_found']
    
    def manufacturer_name(self, obj):
        return obj.manufacturer.name
    manufacturer_name.short_description = _('Производитель')
    manufacturer_name.admin_order_field = 'manufacturer__name'
    
    fieldsets = (
        (_('Производитель'), {
            'fields': ('manufacturer',)
        }),
        (_('Общая статистика'), {
            'fields': (
                'total_news_found',
                'total_searches',
                'total_no_news',
                'total_errors',
            )
        }),
        (_('Метрики'), {
            'fields': (
                'success_rate',
                'error_rate',
                'avg_news_per_search',
            )
        }),
        (_('Периодическая статистика'), {
            'fields': (
                'news_last_30_days',
                'news_last_90_days',
                'searches_last_30_days',
            )
        }),
        (_('Рейтинг и приоритет'), {
            'fields': (
                'ranking_score',
                'priority',
                'is_active',
            )
        }),
        (_('Временные метки'), {
            'fields': (
                'first_search_date',
                'last_search_date',
                'last_news_date',
            ),
            'classes': ('collapse',)
        }),
        (_('Системные'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(NewsResourceStatistics)
class NewsResourceStatisticsAdmin(admin.ModelAdmin):
    """Админка для статистики источников (только для просмотра)"""
    list_display = (
        'resource_name',
        'total_news_found',
        'total_searches',
        'success_rate',
        'ranking_score',
        'news_last_30_days',
        'is_active',
        'last_search_date'
    )
    list_filter = ('is_active', 'created_at', 'last_search_date')
    search_fields = ('resource__name', 'resource__url')
    readonly_fields = (
        'resource',
        'total_news_found',
        'total_searches',
        'total_no_news',
        'total_errors',
        'success_rate',
        'error_rate',
        'avg_news_per_search',
        'news_last_30_days',
        'news_last_90_days',
        'searches_last_30_days',
        'ranking_score',
        'priority',
        'is_active',
        'last_search_date',
        'last_news_date',
        'first_search_date',
        'created_at',
        'updated_at'
    )
    ordering = ['-ranking_score', '-total_news_found']
    
    def resource_name(self, obj):
        return obj.resource.name
    resource_name.short_description = _('Источник')
    resource_name.admin_order_field = 'resource__name'
    
    fieldsets = (
        (_('Источник'), {
            'fields': ('resource',)
        }),
        (_('Общая статистика'), {
            'fields': (
                'total_news_found',
                'total_searches',
                'total_no_news',
                'total_errors',
            )
        }),
        (_('Метрики'), {
            'fields': (
                'success_rate',
                'error_rate',
                'avg_news_per_search',
            )
        }),
        (_('Периодическая статистика'), {
            'fields': (
                'news_last_30_days',
                'news_last_90_days',
                'searches_last_30_days',
            )
        }),
        (_('Рейтинг и приоритет'), {
            'fields': (
                'ranking_score',
                'priority',
                'is_active',
            )
        }),
        (_('Временные метки'), {
            'fields': (
                'first_search_date',
                'last_search_date',
                'last_news_date',
            ),
            'classes': ('collapse',)
        }),
        (_('Системные'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def changelist_view(self, request, extra_context=None):
        # Handle import request
        if request.method == 'POST' and 'import_from_file' in request.POST:
            self.import_from_file(request, None)
            from django.shortcuts import redirect
            return redirect(request.path)
        
        # Handle clear request
        if request.method == 'POST' and 'clear_all' in request.POST:
            count = NewsResource.objects.count()
            NewsResource.objects.all().delete()
            self.message_user(
                request,
                _('Successfully deleted {} resources.').format(count),
                level=messages.SUCCESS
            )
            from django.shortcuts import redirect
            return redirect(request.path)
        
        return super().changelist_view(request, extra_context=extra_context)
    
    def import_from_file(self, request, queryset):
        """Импорт ресурсов из файла Global HVAC & Refrigeration News Resources.md"""
        file_path = os.path.join(settings.BASE_DIR, 'Global HVAC & Refrigeration News Resources.md')
        
        if not os.path.exists(file_path):
            self.message_user(
                request,
                _('File not found: {}').format(file_path),
                level=messages.ERROR
            )
            return
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.readlines()
            
            count_created = 0
            count_updated = 0
            current_region = ''
            
            for line in content:
                line = line.strip()
                
                # Skip empty lines
                if not line:
                    continue
                
                # Track region headers (starting with ###)
                if line.startswith('###'):
                    # Extract region name (remove ### and emoji if present)
                    current_region = re.sub(r'^###\s*[^\s]+\s*', '', line).strip()
                    continue
                
                # Skip other markdown headers
                if line.startswith('#'):
                    continue
                
                # Expected format: "Название" // "ссылка" // "Описание"
                if ' // ' not in line:
                    continue
                
                # Split by " // "
                parts = [part.strip() for part in line.split(' // ')]
                
                # Need at least name and URL
                if len(parts) < 2:
                    continue
                
                name = parts[0].strip()
                url = parts[1].strip() if len(parts) > 1 else ''
                description = parts[2].strip() if len(parts) > 2 else ''
                
                # Clean name (remove quotes if present)
                name = name.strip('"\'')
                
                # Clean URL (remove quotes if present, validate)
                url = url.strip('"\'')
                if not url.startswith('http://') and not url.startswith('https://'):
                    # Skip invalid URLs
                    continue
                
                # Clean description - remove section info if it was added previously
                description = description.strip()
                if description.startswith('[') and ']' in description:
                    # Remove section prefix if present
                    description = re.sub(r'^\[.*?\]\s*', '', description)
                
                # Create or Update
                resource, created = NewsResource.objects.get_or_create(
                    name=name,
                    defaults={
                        'url': url,
                        'description': description,
                        'section': current_region,
                    }
                )
                
                if not created:
                    # Update existing resource
                    resource.url = url
                    resource.description = description
                    resource.section = current_region
                    resource.save()
                    count_updated += 1
                else:
                    count_created += 1
            
            self.message_user(
                request,
                _('Successfully imported {} new resources and updated {} existing resources.').format(
                    count_created, count_updated
                ),
                level=messages.SUCCESS
            )
        except Exception as e:
            self.message_user(
                request,
                _('Error during import: {}').format(str(e)),
                level=messages.ERROR
            )
