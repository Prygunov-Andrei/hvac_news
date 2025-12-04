from rest_framework import serializers
from .models import NewsPost, NewsMedia, Comment
from users.serializers import UserSerializer

class NewsMediaSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsMedia
        fields = ('id', 'file', 'media_type')

class NewsPostSerializer(serializers.ModelSerializer):
    media = NewsMediaSerializer(many=True, read_only=True)

    class Meta:
        model = NewsPost
        fields = (
            'id', 'title', 'title_ru', 'title_en', 'title_de', 'title_pt',
            'body', 'body_ru', 'body_en', 'body_de', 'body_pt',
            'pub_date', 'created_at', 'author', 'media'
        )


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

