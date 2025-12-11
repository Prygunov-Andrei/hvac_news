from rest_framework import serializers
from django.utils import timezone
from django.conf import settings
from .models import NewsPost, NewsMedia, Comment, MediaUpload
from users.serializers import UserSerializer
import os

class NewsMediaSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsMedia
        fields = ('id', 'file', 'media_type')

class NewsPostSerializer(serializers.ModelSerializer):
    media = NewsMediaSerializer(many=True, read_only=True)
    author = UserSerializer(read_only=True)

    class Meta:
        model = NewsPost
        fields = (
            'id', 'title', 'title_ru', 'title_en', 'title_de', 'title_pt',
            'body', 'body_ru', 'body_en', 'body_de', 'body_pt',
            'pub_date', 'status', 'source_language', 'created_at', 'updated_at', 'author', 'media'
        )
        read_only_fields = ('id', 'created_at', 'updated_at', 'author', 'title_ru', 'title_en', 'title_de', 'title_pt', 'body_ru', 'body_en', 'body_de', 'body_pt')


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

