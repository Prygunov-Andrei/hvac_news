from rest_framework import serializers
from .models import Manufacturer, Brand, NewsResource, NewsResourceStatistics, ManufacturerStatistics

class BrandSerializer(serializers.ModelSerializer):
    """Сериализатор для бренда с информацией о производителе"""
    manufacturer_name = serializers.ReadOnlyField(source='manufacturer.name')
    manufacturer_region = serializers.ReadOnlyField(source='manufacturer.region', read_only=True)
    
    class Meta:
        model = Brand
        fields = '__all__'
    
    def validate_name(self, value):
        """Проверка уникальности названия бренда в рамках одного производителя"""
        manufacturer = self.initial_data.get('manufacturer') or (self.instance.manufacturer.id if self.instance else None)
        
        if manufacturer:
            if self.instance:
                # При обновлении - исключаем текущий объект
                if Brand.objects.filter(name=value, manufacturer_id=manufacturer).exclude(pk=self.instance.pk).exists():
                    raise serializers.ValidationError("Бренд с таким названием уже существует у этого производителя.")
            else:
                # При создании
                if Brand.objects.filter(name=value, manufacturer_id=manufacturer).exists():
                    raise serializers.ValidationError("Бренд с таким названием уже существует у этого производителя.")
        
        return value
    
    def validate_manufacturer(self, value):
        """Проверка существования производителя"""
        if not value:
            raise serializers.ValidationError("Производитель обязателен для указания.")
        return value

class NewsResourceStatisticsSerializer(serializers.ModelSerializer):
    """Сериализатор для статистики источника"""
    class Meta:
        model = NewsResourceStatistics
        fields = (
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
        )
        read_only_fields = fields


class NewsResourceSerializer(serializers.ModelSerializer):
    """Сериализатор для источника новостей с включенной статистикой"""
    statistics = NewsResourceStatisticsSerializer(read_only=True)
    is_problematic = serializers.SerializerMethodField()
    is_auto_searchable = serializers.SerializerMethodField()
    requires_manual_input = serializers.SerializerMethodField()
    
    class Meta:
        model = NewsResource
        fields = '__all__'
    
    def get_is_problematic(self, obj):
        """Возвращает True, если источник проблемный (error_rate >= 30%)"""
        try:
            from .models import NewsResourceStatistics
            return obj.statistics.error_rate >= 30
        except (AttributeError, NewsResourceStatistics.DoesNotExist):
            return False
    
    def get_is_auto_searchable(self, obj):
        """Возвращает True, если источник поддерживает автоматический поиск"""
        return obj.is_auto_searchable
    
    def get_requires_manual_input(self, obj):
        """Возвращает True, если источник требует ручного ввода"""
        return obj.requires_manual_input
    
    def validate_name(self, value):
        """Проверка уникальности названия источника"""
        if self.instance:
            # При обновлении - исключаем текущий объект
            if NewsResource.objects.filter(name=value).exclude(pk=self.instance.pk).exists():
                raise serializers.ValidationError("Источник с таким названием уже существует.")
        else:
            # При создании
            if NewsResource.objects.filter(name=value).exists():
                raise serializers.ValidationError("Источник с таким названием уже существует.")
        return value
    
    def validate_url(self, value):
        """Проверка корректности URL"""
        if value and not (value.startswith('http://') or value.startswith('https://')):
            raise serializers.ValidationError("URL должен начинаться с http:// или https://")
        return value


class ManufacturerStatisticsSerializer(serializers.ModelSerializer):
    """Сериализатор для статистики производителя"""
    class Meta:
        model = ManufacturerStatistics
        fields = (
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
        )
        read_only_fields = fields


class ManufacturerSerializer(serializers.ModelSerializer):
    """Сериализатор для производителя с включенной статистикой и брендами"""
    statistics = ManufacturerStatisticsSerializer(read_only=True)
    brands = BrandSerializer(many=True, read_only=True)
    brands_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Manufacturer
        fields = '__all__'
    
    def get_brands_count(self, obj):
        """Возвращает количество брендов производителя"""
        return obj.brands.count()
    
    def validate_name(self, value):
        """Проверка уникальности названия производителя"""
        if self.instance:
            # При обновлении - исключаем текущий объект
            if Manufacturer.objects.filter(name=value).exclude(pk=self.instance.pk).exists():
                raise serializers.ValidationError("Производитель с таким названием уже существует.")
        else:
            # При создании
            if Manufacturer.objects.filter(name=value).exists():
                raise serializers.ValidationError("Производитель с таким названием уже существует.")
        return value

