import logging
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Sum, Avg, Count, Q
from django.utils import timezone
from datetime import timedelta
from .models import Manufacturer, Brand, NewsResource, NewsResourceStatistics, ManufacturerStatistics

logger = logging.getLogger(__name__)
from .serializers import (
    ManufacturerSerializer, BrandSerializer, NewsResourceSerializer, NewsResourceStatisticsSerializer,
    ManufacturerStatisticsSerializer
)

class ManufacturerViewSet(viewsets.ModelViewSet):
    """
    ViewSet для производителей с поддержкой CRUD операций.
    Чтение доступно всем, создание/редактирование/удаление - только аутентифицированным пользователям.
    """
    queryset = Manufacturer.objects.select_related('statistics').prefetch_related('brands').all()
    serializer_class = ManufacturerSerializer
    
    def get_permissions(self):
        """
        Разрешает чтение всем, но требует аутентификации для записи.
        """
        if self.action in ['list', 'retrieve', 'statistics_summary', 'search_brands']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]
    
    def get_queryset(self):
        """Поддерживает фильтрацию и сортировку по статистике"""
        queryset = super().get_queryset()
        
        # Сортировка по рейтингу
        ordering = self.request.query_params.get('ordering', None)
        if ordering == 'ranking_score':
            queryset = queryset.order_by('-statistics__ranking_score')
        elif ordering == '-ranking_score':
            queryset = queryset.order_by('statistics__ranking_score')
        elif ordering == 'total_news':
            queryset = queryset.order_by('-statistics__total_news_found')
        elif ordering == '-total_news':
            queryset = queryset.order_by('statistics__total_news_found')
        
        # Фильтр по активности
        is_active = self.request.query_params.get('is_active', None)
        if is_active is not None:
            is_active_bool = is_active.lower() in ('true', '1', 'yes')
            queryset = queryset.filter(statistics__is_active=is_active_bool)
        
        return queryset
    
    @action(detail=False, methods=['get'])
    def statistics_summary(self, request):
        """
        Возвращает общую статистику по всем производителям для инфографики.
        Используется на фронтенде для отображения дашборда.
        """
        # Получаем все статистики
        all_stats = ManufacturerStatistics.objects.all()
        
        # Общая статистика
        total_manufacturers = Manufacturer.objects.count()
        manufacturers_with_stats = all_stats.count()
        active_manufacturers = all_stats.filter(is_active=True).count()
        
        # Агрегированная статистика
        total_news_all = all_stats.aggregate(Sum('total_news_found'))['total_news_found__sum'] or 0
        total_searches_all = all_stats.aggregate(Sum('total_searches'))['total_searches__sum'] or 0
        total_no_news_all = all_stats.aggregate(Sum('total_no_news'))['total_no_news__sum'] or 0
        total_errors_all = all_stats.aggregate(Sum('total_errors'))['total_errors__sum'] or 0
        
        # Средние значения
        avg_success_rate = all_stats.aggregate(Avg('success_rate'))['success_rate__avg'] or 0.0
        avg_news_per_search = all_stats.aggregate(Avg('avg_news_per_search'))['avg_news_per_search__avg'] or 0.0
        avg_ranking_score = all_stats.aggregate(Avg('ranking_score'))['ranking_score__avg'] or 0.0
        
        # Статистика за последние 30 дней
        news_last_30d_all = all_stats.aggregate(Sum('news_last_30_days'))['news_last_30_days__sum'] or 0
        
        # Топ производители
        top_by_news = all_stats.order_by('-total_news_found')[:10]
        top_by_ranking = all_stats.order_by('-ranking_score')[:10]
        top_by_activity = all_stats.order_by('-news_last_30_days')[:10]
        
        # Категории производителей
        high_performers = all_stats.filter(ranking_score__gte=50).count()
        medium_performers = all_stats.filter(ranking_score__gte=20, ranking_score__lt=50).count()
        low_performers = all_stats.filter(ranking_score__lt=20).count()
        
        # Проблемные производители (высокий процент ошибок)
        problematic = all_stats.filter(error_rate__gte=30).count()
        
        return Response({
            'overview': {
                'total_manufacturers': total_manufacturers,
                'manufacturers_with_stats': manufacturers_with_stats,
                'active_manufacturers': active_manufacturers,
                'inactive_manufacturers': total_manufacturers - active_manufacturers,
            },
            'aggregated': {
                'total_news_found': total_news_all,
                'total_searches': total_searches_all,
                'total_no_news': total_no_news_all,
                'total_errors': total_errors_all,
                'news_last_30_days': news_last_30d_all,
            },
            'averages': {
                'success_rate': round(avg_success_rate, 2),
                'avg_news_per_search': round(avg_news_per_search, 2),
                'avg_ranking_score': round(avg_ranking_score, 2),
            },
            'categories': {
                'high_performers': high_performers,
                'medium_performers': medium_performers,
                'low_performers': low_performers,
                'problematic': problematic,
            },
            'top_manufacturers': {
                'by_news': [
                    {
                        'id': stat.manufacturer.id,
                        'name': stat.manufacturer.name,
                        'total_news': stat.total_news_found,
                        'ranking_score': stat.ranking_score,
                    }
                    for stat in top_by_news
                ],
                'by_ranking': [
                    {
                        'id': stat.manufacturer.id,
                        'name': stat.manufacturer.name,
                        'ranking_score': stat.ranking_score,
                        'total_news': stat.total_news_found,
                    }
                    for stat in top_by_ranking
                ],
                'by_activity': [
                    {
                        'id': stat.manufacturer.id,
                        'name': stat.manufacturer.name,
                        'news_last_30_days': stat.news_last_30_days,
                        'ranking_score': stat.ranking_score,
                    }
                    for stat in top_by_activity
                ],
            }
        })
    
    @action(detail=False, methods=['get'])
    def search_brands(self, request):
        """
        Поиск брендов для использования при редактировании производителя.
        Параметры:
        - search: строка поиска (поиск по названию бренда)
        - manufacturer_id: фильтр по производителю (опционально)
        - limit: ограничение количества результатов (по умолчанию 20)
        """
        search_query = request.query_params.get('search', '').strip()
        manufacturer_id = request.query_params.get('manufacturer_id', None)
        limit = int(request.query_params.get('limit', 20))
        
        queryset = Brand.objects.select_related('manufacturer').all()
        
        # Фильтр по поисковому запросу
        if search_query:
            queryset = queryset.filter(name__icontains=search_query)
        
        # Фильтр по производителю
        if manufacturer_id:
            try:
                queryset = queryset.filter(manufacturer_id=int(manufacturer_id))
            except (ValueError, TypeError):
                pass
        
        # Ограничение и сортировка
        queryset = queryset.order_by('name')[:limit]
        
        serializer = BrandSerializer(queryset, many=True)
        return Response(serializer.data)

class BrandViewSet(viewsets.ModelViewSet):
    """
    ViewSet для брендов с поддержкой CRUD операций.
    Чтение доступно всем, создание/редактирование/удаление - только аутентифицированным пользователям.
    """
    queryset = Brand.objects.select_related('manufacturer').all()
    serializer_class = BrandSerializer
    
    def get_permissions(self):
        """
        Разрешает чтение всем, но требует аутентификации для записи.
        """
        if self.action in ['list', 'retrieve', 'search_manufacturers']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]
    
    @action(detail=False, methods=['get'])
    def search_manufacturers(self, request):
        """
        Поиск производителей для использования при создании/редактировании бренда.
        Параметры:
        - search: строка поиска (поиск по названию производителя или региону)
        - limit: ограничение количества результатов (по умолчанию 20)
        """
        search_query = request.query_params.get('search', '').strip()
        limit = int(request.query_params.get('limit', 20))
        
        queryset = Manufacturer.objects.all()
        
        # Фильтр по поисковому запросу
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) | 
                Q(region__icontains=search_query)
            )
        
        # Ограничение и сортировка
        queryset = queryset.order_by('name')[:limit]
        
        # Упрощенный сериализатор для поиска (без статистики)
        results = [
            {
                'id': m.id,
                'name': m.name,
                'region': m.region,
                'website_1': m.website_1,
            }
            for m in queryset
        ]
        
        return Response(results)

class NewsResourceViewSet(viewsets.ModelViewSet):
    """
    ViewSet для источников новостей с поддержкой CRUD операций.
    Чтение доступно всем, создание/редактирование/удаление - только аутентифицированным пользователям.
    """
    queryset = NewsResource.objects.select_related('statistics').all()
    serializer_class = NewsResourceSerializer
    
    def get_permissions(self):
        """
        Разрешает чтение всем, но требует аутентификации для записи.
        """
        if self.action in ['list', 'retrieve', 'statistics_summary', 'available_providers']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]
    
    @action(detail=False, methods=['get'])
    def available_providers(self, request):
        """
        Возвращает список доступных провайдеров LLM для поиска новостей.
        """
        from django.conf import settings
        
        providers = []
        
        # Проверяем доступность каждого провайдера
        if getattr(settings, 'XAI_API_KEY', ''):
            providers.append({
                'id': 'grok',
                'name': 'Grok 4.1 Fast',
                'description': 'Самый экономичный вариант (~$0.13 за 220 ресурсов)',
                'available': True
            })
        else:
            providers.append({
                'id': 'grok',
                'name': 'Grok 4.1 Fast',
                'description': 'Самый экономичный вариант (~$0.13 за 220 ресурсов)',
                'available': False
            })
        
        if getattr(settings, 'ANTHROPIC_API_KEY', ''):
            providers.append({
                'id': 'anthropic',
                'name': 'Anthropic Claude Haiku 4.5',
                'description': 'Экономичный вариант от Anthropic (~$4.26 за 220 ресурсов)',
                'available': True
            })
        else:
            providers.append({
                'id': 'anthropic',
                'name': 'Anthropic Claude Haiku 4.5',
                'description': 'Экономичный вариант от Anthropic (~$4.26 за 220 ресурсов)',
                'available': False
            })
        
        if getattr(settings, 'TRANSLATION_API_KEY', ''):
            providers.append({
                'id': 'openai',
                'name': 'OpenAI GPT-5.2',
                'description': 'Резервный вариант (~$6.35 за 220 ресурсов)',
                'available': True
            })
        else:
            providers.append({
                'id': 'openai',
                'name': 'OpenAI GPT-5.2',
                'description': 'Резервный вариант (~$6.35 за 220 ресурсов)',
                'available': False
            })
        
        # Всегда доступен автоматический выбор
        providers.insert(0, {
            'id': 'auto',
            'name': 'Автоматический выбор (цепочка)',
            'description': 'Использует цепочку: Grok → Anthropic → OpenAI',
            'available': True
        })
        
        return Response({
            'providers': providers,
            'default': 'auto'
        })
    
    @action(detail=True, methods=['post'])
    def discover_news(self, request, pk=None):
        """
        Запускает поиск новостей для конкретного источника.
        
        Параметры POST:
        - provider (string, опционально): ID провайдера ('auto', 'grok', 'anthropic', 'openai')
        """
        from news.discovery_service import NewsDiscoveryService
        from news.models import NewsDiscoveryStatus
        
        resource = self.get_object()
        
        # Проверяем, что источник не требует ручного ввода
        if resource.source_type == NewsResource.SOURCE_TYPE_MANUAL:
            return Response({
                'error': 'Этот источник требует ручного ввода и не может быть обработан автоматически'
            }, status=400)
        
        # Получаем выбранный провайдер
        provider = request.data.get('provider', 'auto')
        if provider not in ['auto', 'grok', 'anthropic', 'openai']:
            provider = 'auto'
        
        # Запускаем поиск в фоне
        import threading
        
        def run_discovery():
            try:
                service = NewsDiscoveryService(user=request.user)
                created, errors, error_msg = service.discover_news_for_resource(resource, provider=provider)
                logger.info(f"Discovery completed for resource {resource.id}: created={created}, errors={errors}, provider={provider}")
            except Exception as e:
                logger.error(f"Error during single resource discovery: {str(e)}")
        
        thread = threading.Thread(target=run_discovery)
        thread.daemon = True
        thread.start()
        
        return Response({
            'status': 'running',
            'resource_id': resource.id,
            'resource_name': resource.name,
            'provider': provider,
            'message': f'Поиск новостей запущен для источника "{resource.name}"'
        })
    
    def get_queryset(self):
        """Поддерживает фильтрацию и сортировку по статистике"""
        queryset = super().get_queryset()
        
        # Сортировка по рейтингу
        ordering = self.request.query_params.get('ordering', None)
        if ordering == 'ranking_score':
            queryset = queryset.order_by('-statistics__ranking_score')
        elif ordering == '-ranking_score':
            queryset = queryset.order_by('statistics__ranking_score')
        elif ordering == 'total_news':
            queryset = queryset.order_by('-statistics__total_news_found')
        elif ordering == '-total_news':
            queryset = queryset.order_by('statistics__total_news_found')
        
        # Фильтр по активности
        is_active = self.request.query_params.get('is_active', None)
        if is_active is not None:
            is_active_bool = is_active.lower() in ('true', '1', 'yes')
            queryset = queryset.filter(statistics__is_active=is_active_bool)
        
        # Фильтр по проблемным источникам
        is_problematic = self.request.query_params.get('is_problematic', None)
        if is_problematic is not None:
            is_problematic_bool = is_problematic.lower() in ('true', '1', 'yes')
            if is_problematic_bool:
                queryset = queryset.filter(statistics__error_rate__gte=30)
            else:
                queryset = queryset.filter(Q(statistics__error_rate__lt=30) | Q(statistics__error_rate__isnull=True))
        
        # Фильтр по типу источника
        source_type = self.request.query_params.get('source_type', None)
        if source_type in ['auto', 'manual', 'hybrid']:
            queryset = queryset.filter(source_type=source_type)
        
        # Фильтр по автоматически обрабатываемым источникам
        is_auto_searchable = self.request.query_params.get('is_auto_searchable', None)
        if is_auto_searchable is not None:
            is_auto_searchable_bool = is_auto_searchable.lower() in ('true', '1', 'yes')
            if is_auto_searchable_bool:
                queryset = queryset.exclude(source_type='manual')
            else:
                queryset = queryset.filter(source_type='manual')
        
        return queryset
    
    @action(detail=False, methods=['get'])
    def statistics_summary(self, request):
        """
        Возвращает общую статистику по всем источникам для инфографики.
        Используется на фронтенде для отображения дашборда.
        """
        # Получаем все статистики
        all_stats = NewsResourceStatistics.objects.all()
        
        # Общая статистика
        total_resources = NewsResource.objects.count()
        resources_with_stats = all_stats.count()
        active_resources = all_stats.filter(is_active=True).count()
        
        # Агрегированная статистика
        total_news_all = all_stats.aggregate(Sum('total_news_found'))['total_news_found__sum'] or 0
        total_searches_all = all_stats.aggregate(Sum('total_searches'))['total_searches__sum'] or 0
        total_no_news_all = all_stats.aggregate(Sum('total_no_news'))['total_no_news__sum'] or 0
        total_errors_all = all_stats.aggregate(Sum('total_errors'))['total_errors__sum'] or 0
        
        # Средние значения
        avg_success_rate = all_stats.aggregate(Avg('success_rate'))['success_rate__avg'] or 0.0
        avg_news_per_search = all_stats.aggregate(Avg('avg_news_per_search'))['avg_news_per_search__avg'] or 0.0
        avg_ranking_score = all_stats.aggregate(Avg('ranking_score'))['ranking_score__avg'] or 0.0
        
        # Статистика за последние 30 дней
        news_last_30d_all = all_stats.aggregate(Sum('news_last_30_days'))['news_last_30_days__sum'] or 0
        
        # Топ источники
        top_by_news = all_stats.order_by('-total_news_found')[:10]
        top_by_ranking = all_stats.order_by('-ranking_score')[:10]
        top_by_activity = all_stats.order_by('-news_last_30_days')[:10]
        
        # Категории источников
        high_performers = all_stats.filter(ranking_score__gte=50).count()
        medium_performers = all_stats.filter(ranking_score__gte=20, ranking_score__lt=50).count()
        low_performers = all_stats.filter(ranking_score__lt=20).count()
        
        # Проблемные источники (высокий процент ошибок)
        problematic = all_stats.filter(error_rate__gte=30).count()
        
        # Статистика по типам источников
        auto_sources = NewsResource.objects.filter(source_type='auto').count()
        manual_sources = NewsResource.objects.filter(source_type='manual').count()
        hybrid_sources = NewsResource.objects.filter(source_type='hybrid').count()
        
        return Response({
            'overview': {
                'total_resources': total_resources,
                'resources_with_stats': resources_with_stats,
                'active_resources': active_resources,
                'inactive_resources': total_resources - active_resources,
            },
            'source_types': {
                'auto': auto_sources,
                'manual': manual_sources,
                'hybrid': hybrid_sources,
                'auto_searchable': auto_sources + hybrid_sources,  # Всего для автопоиска
            },
            'aggregated': {
                'total_news_found': total_news_all,
                'total_searches': total_searches_all,
                'total_no_news': total_no_news_all,
                'total_errors': total_errors_all,
                'news_last_30_days': news_last_30d_all,
            },
            'averages': {
                'success_rate': round(avg_success_rate, 2),
                'avg_news_per_search': round(avg_news_per_search, 2),
                'avg_ranking_score': round(avg_ranking_score, 2),
            },
            'categories': {
                'high_performers': high_performers,
                'medium_performers': medium_performers,
                'low_performers': low_performers,
                'problematic': problematic,
            },
            'top_sources': {
                'by_news': [
                    {
                        'id': stat.resource.id,
                        'name': stat.resource.name,
                        'total_news': stat.total_news_found,
                        'ranking_score': stat.ranking_score,
                    }
                    for stat in top_by_news
                ],
                'by_ranking': [
                    {
                        'id': stat.resource.id,
                        'name': stat.resource.name,
                        'ranking_score': stat.ranking_score,
                        'total_news': stat.total_news_found,
                    }
                    for stat in top_by_ranking
                ],
                'by_activity': [
                    {
                        'id': stat.resource.id,
                        'name': stat.resource.name,
                        'news_last_30_days': stat.news_last_30_days,
                        'ranking_score': stat.ranking_score,
                    }
                    for stat in top_by_activity
                ],
            }
        })
