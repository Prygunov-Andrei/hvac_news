from rest_framework import serializers
from django.utils import timezone
from django.conf import settings
from .models import (
    NewsPost, NewsMedia, Comment, MediaUpload, 
    SearchConfiguration, NewsDiscoveryRun, DiscoveryAPICall
)
from users.serializers import UserSerializer
import os

class NewsMediaSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsMedia
        fields = ('id', 'file', 'media_type')

class NewsPostSerializer(serializers.ModelSerializer):
    media = NewsMediaSerializer(many=True, read_only=True)
    author = serializers.SerializerMethodField()
    
    # Поля для многоязычности через modeltranslation (безопасная обработка)
    title_ru = serializers.SerializerMethodField()
    title_en = serializers.SerializerMethodField()
    title_de = serializers.SerializerMethodField()
    title_pt = serializers.SerializerMethodField()
    body_ru = serializers.SerializerMethodField()
    body_en = serializers.SerializerMethodField()
    body_de = serializers.SerializerMethodField()
    body_pt = serializers.SerializerMethodField()
    
    def get_author(self, obj):
        """Безопасно возвращает автора или None"""
        if obj.author:
            return UserSerializer(obj.author).data
        return None

    class Meta:
        model = NewsPost
        fields = (
            'id', 'title', 'title_ru', 'title_en', 'title_de', 'title_pt',
            'body', 'body_ru', 'body_en', 'body_de', 'body_pt',
            'pub_date', 'status', 'source_language', 'source_url', 'created_at', 'updated_at', 'author', 'media',
            'is_no_news_found', 'manufacturer'
        )
        read_only_fields = ('id', 'created_at', 'updated_at', 'author', 'title_ru', 'title_en', 'title_de', 'title_pt', 'body_ru', 'body_en', 'body_de', 'body_pt', 'is_no_news_found', 'manufacturer')
    
    def _get_translation_field(self, obj, field_name, lang_code):
        """Безопасно получает значение поля перевода или None"""
        try:
            field_with_lang = f"{field_name}_{lang_code}"
            if hasattr(obj, field_with_lang):
                value = getattr(obj, field_with_lang, None)
                return value if value else None
        except (AttributeError, KeyError):
            pass
        return None
    
    def get_title_ru(self, obj):
        return self._get_translation_field(obj, 'title', 'ru')
    
    def get_title_en(self, obj):
        return self._get_translation_field(obj, 'title', 'en')
    
    def get_title_de(self, obj):
        return self._get_translation_field(obj, 'title', 'de')
    
    def get_title_pt(self, obj):
        return self._get_translation_field(obj, 'title', 'pt')
    
    def get_body_ru(self, obj):
        return self._get_translation_field(obj, 'body', 'ru')
    
    def get_body_en(self, obj):
        return self._get_translation_field(obj, 'body', 'en')
    
    def get_body_de(self, obj):
        return self._get_translation_field(obj, 'body', 'de')
    
    def get_body_pt(self, obj):
        return self._get_translation_field(obj, 'body', 'pt')


class NewsPostWriteSerializer(serializers.ModelSerializer):
    """
    Сериализатор для создания и редактирования новостей.
    Используется только администраторами.
    """
    auto_translate = serializers.BooleanField(write_only=True, required=False, default=False)
    
    class Meta:
        model = NewsPost
        fields = ('title', 'body', 'pub_date', 'status', 'source_language', 'auto_translate')
    
    def validate_title(self, value):
        """Валидация заголовка"""
        if not value or not value.strip():
            raise serializers.ValidationError("Заголовок не может быть пустым.")
        return value.strip()
    
    def validate_body(self, value):
        """Валидация текста новости"""
        if not value or not value.strip():
            raise serializers.ValidationError("Текст новости не может быть пустым.")
        return value.strip()
    
    def validate_status(self, value):
        """Валидация статуса"""
        valid_statuses = [choice[0] for choice in NewsPost.STATUS_CHOICES]
        if value not in valid_statuses:
            valid_str = ', '.join(valid_statuses)
            raise serializers.ValidationError(f"Статус должен быть одним из: {valid_str}.")
        return value
    
    def validate_source_language(self, value):
        """Валидация исходного языка"""
        allowed_languages = [lang[0] for lang in settings.LANGUAGES]
        if value not in allowed_languages:
            allowed_str = ', '.join(allowed_languages)
            raise serializers.ValidationError(f"Исходный язык должен быть одним из: {allowed_str}.")
        return value
    
    def validate(self, attrs):
        """Проверяем логику статуса и даты публикации"""
        status = attrs.get('status', self.instance.status if self.instance else 'draft')
        pub_date = attrs.get('pub_date', self.instance.pub_date if self.instance else None)
        
        # Если статус 'published', но дата в будущем, меняем на 'scheduled'
        if status == 'published' and pub_date and pub_date > timezone.now():
            attrs['status'] = 'scheduled'
        
        # Если статус 'scheduled', но дата в прошлом, меняем на 'published'
        if status == 'scheduled' and pub_date and pub_date <= timezone.now():
            attrs['status'] = 'published'
        
        return attrs


class CommentSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)

    class Meta:
        model = Comment
        fields = ('id', 'news_post', 'author', 'text', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at', 'author')

    def create(self, validated_data):
        # Автор устанавливается автоматически из request.user
        validated_data.pop('author_id', None)
        validated_data['author'] = self.context['request'].user
        return super().create(validated_data)


class MediaUploadSerializer(serializers.ModelSerializer):
    """
    Сериализатор для загрузки медиафайлов.
    Валидирует формат и размер файла.
    """
    url = serializers.SerializerMethodField()
    file_size = serializers.SerializerMethodField()
    
    # Максимальные размеры файлов (в байтах)
    MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB
    MAX_VIDEO_SIZE = 100 * 1024 * 1024  # 100 MB
    
    # Допустимые форматы
    ALLOWED_IMAGE_FORMATS = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
    ALLOWED_VIDEO_FORMATS = ['.mp4', '.webm']
    
    class Meta:
        model = MediaUpload
        fields = ('id', 'file', 'media_type', 'uploaded_by', 'created_at', 'url', 'file_size')
        read_only_fields = ('id', 'uploaded_by', 'created_at', 'url', 'file_size')
    
    def get_url(self, obj):
        """Возвращает полный URL загруженного файла"""
        if obj.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None
    
    def get_file_size(self, obj):
        """Возвращает размер файла в байтах"""
        if obj.file:
            try:
                return obj.file.size
            except (AttributeError, OSError):
                return None
        return None
    
    def _get_file_type(self, file):
        """Определяет тип файла (image/video) по расширению"""
        if not file:
            return None
        
        file_name = file.name.lower()
        file_ext = os.path.splitext(file_name)[1]
        
        if file_ext in self.ALLOWED_IMAGE_FORMATS:
            return 'image'
        elif file_ext in self.ALLOWED_VIDEO_FORMATS:
            return 'video'
        return None
    
    def _validate_file_format_and_size(self, file):
        """Валидация формата и размера файла"""
        if not file:
            raise serializers.ValidationError("Файл обязателен.")
        
        file_type = self._get_file_type(file)
        if not file_type:
            allowed = ', '.join(self.ALLOWED_IMAGE_FORMATS + self.ALLOWED_VIDEO_FORMATS)
            raise serializers.ValidationError(
                f"Недопустимый формат файла. Разрешенные форматы: {allowed}"
            )
        
        # Проверяем размер файла
        file_size = file.size
        if file_type == 'image' and file_size > self.MAX_IMAGE_SIZE:
            raise serializers.ValidationError(
                f"Размер изображения превышает лимит {self.MAX_IMAGE_SIZE / (1024*1024):.0f} MB."
            )
        if file_type == 'video' and file_size > self.MAX_VIDEO_SIZE:
            raise serializers.ValidationError(
                f"Размер видео превышает лимит {self.MAX_VIDEO_SIZE / (1024*1024):.0f} MB."
            )
        
        return file_type
    
    def validate_file(self, value):
        """Валидация файла: формат и размер"""
        self._validate_file_format_and_size(value)
        return value
    
    def validate_media_type(self, value):
        """Валидация типа медиа (опциональное поле)"""
        if value is not None and value not in ['image', 'video']:
            raise serializers.ValidationError("Тип медиа должен быть 'image' или 'video'.")
        return value
    
    def validate(self, attrs):
        """Проверяем соответствие типа медиа и формата файла, определяем тип автоматически"""
        file = attrs.get('file')
        media_type = attrs.get('media_type')
        
        if file:
            detected_type = self._get_file_type(file)
            
            if not detected_type:
                # Это уже проверено в validate_file, но на всякий случай
                allowed = ', '.join(self.ALLOWED_IMAGE_FORMATS + self.ALLOWED_VIDEO_FORMATS)
                raise serializers.ValidationError({
                    'file': f"Недопустимый формат файла. Разрешенные форматы: {allowed}"
                })
            
            # Если тип медиа не указан, определяем автоматически
            if not media_type:
                attrs['media_type'] = detected_type
            else:
                # Проверяем соответствие указанного типа и формата файла
                if media_type != detected_type:
                    raise serializers.ValidationError({
                        'media_type': f'Тип медиа должен быть "{detected_type}" для данного формата файла.'
                    })
        
        return attrs
    
    def create(self, validated_data):
        """Автор устанавливается автоматически из request.user"""
        validated_data['uploaded_by'] = self.context['request'].user
        return super().create(validated_data)


class SearchConfigurationSerializer(serializers.ModelSerializer):
    """Сериализатор для конфигурации поиска"""
    
    class Meta:
        model = SearchConfiguration
        fields = (
            'id', 'name', 'is_active',
            'primary_provider', 'fallback_chain',
            'temperature', 'timeout', 'max_news_per_resource', 'delay_between_requests',
            'max_search_results', 'search_context_size',
            'grok_model', 'anthropic_model', 'gemini_model', 'openai_model',
            'grok_input_price', 'grok_output_price',
            'anthropic_input_price', 'anthropic_output_price',
            'gemini_input_price', 'gemini_output_price',
            'openai_input_price', 'openai_output_price',
            'created_at', 'updated_at'
        )
        read_only_fields = ('id', 'created_at', 'updated_at')


class SearchConfigurationListSerializer(serializers.ModelSerializer):
    """Краткий сериализатор для списка конфигураций"""
    
    class Meta:
        model = SearchConfiguration
        fields = ('id', 'name', 'is_active', 'primary_provider', 'max_search_results', 
                  'temperature', 'updated_at')
        read_only_fields = fields


class DiscoveryAPICallSerializer(serializers.ModelSerializer):
    """Сериализатор для записей API вызовов"""
    resource_name = serializers.SerializerMethodField()
    manufacturer_name = serializers.SerializerMethodField()
    
    class Meta:
        model = DiscoveryAPICall
        fields = (
            'id', 'discovery_run', 'resource', 'resource_name', 
            'manufacturer', 'manufacturer_name',
            'provider', 'model', 'input_tokens', 'output_tokens',
            'cost_usd', 'duration_ms', 'success', 'error_message',
            'news_extracted', 'created_at'
        )
        read_only_fields = fields
    
    def get_resource_name(self, obj):
        return obj.resource.name if obj.resource else None
    
    def get_manufacturer_name(self, obj):
        return obj.manufacturer.name if obj.manufacturer else None


class NewsDiscoveryRunSerializer(serializers.ModelSerializer):
    """Сериализатор для запусков поиска"""
    duration_display = serializers.SerializerMethodField()
    efficiency = serializers.SerializerMethodField()
    api_calls_count = serializers.SerializerMethodField()
    
    class Meta:
        model = NewsDiscoveryRun
        fields = (
            'id', 'last_search_date', 'config_snapshot',
            'started_at', 'finished_at', 'duration_display',
            'total_requests', 'total_input_tokens', 'total_output_tokens',
            'estimated_cost_usd',
            'provider_stats',
            'news_found', 'news_duplicates', 'resources_processed', 'resources_failed',
            'efficiency', 'api_calls_count',
            'created_at', 'updated_at'
        )
        read_only_fields = fields
    
    def get_duration_display(self, obj):
        return obj.get_duration_display()
    
    def get_efficiency(self, obj):
        return obj.get_efficiency()
    
    def get_api_calls_count(self, obj):
        return obj.api_calls.count()


class NewsDiscoveryRunListSerializer(serializers.ModelSerializer):
    """Краткий сериализатор для списка запусков"""
    duration_display = serializers.SerializerMethodField()
    efficiency = serializers.SerializerMethodField()
    config_name = serializers.SerializerMethodField()
    
    class Meta:
        model = NewsDiscoveryRun
        fields = (
            'id', 'last_search_date', 'config_name',
            'started_at', 'finished_at', 'duration_display',
            'total_requests', 'estimated_cost_usd',
            'news_found', 'resources_processed', 'resources_failed',
            'efficiency', 'created_at'
        )
        read_only_fields = fields
    
    def get_duration_display(self, obj):
        return obj.get_duration_display()
    
    def get_efficiency(self, obj):
        return obj.get_efficiency()
    
    def get_config_name(self, obj):
        if obj.config_snapshot:
            return obj.config_snapshot.get('name', 'Unknown')
        return None


class DiscoveryStatsSerializer(serializers.Serializer):
    """Сериализатор для агрегированной статистики"""
    total_runs = serializers.IntegerField()
    total_news_found = serializers.IntegerField()
    total_cost_usd = serializers.DecimalField(max_digits=10, decimal_places=4)
    total_requests = serializers.IntegerField()
    total_input_tokens = serializers.IntegerField()
    total_output_tokens = serializers.IntegerField()
    avg_efficiency = serializers.FloatField()
    avg_cost_per_run = serializers.DecimalField(max_digits=10, decimal_places=4)
    provider_breakdown = serializers.DictField()

