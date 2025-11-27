from rest_framework import serializers
from .models import NewsPost, NewsMedia

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

