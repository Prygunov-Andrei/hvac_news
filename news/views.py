from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from .models import NewsPost, Comment
from .serializers import NewsPostSerializer, CommentSerializer


class NewsPostViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NewsPostSerializer
    permission_classes = [permissions.AllowAny]
    
    def get_queryset(self):
        return NewsPost.objects.filter(pub_date__lte=timezone.now())


class CommentViewSet(viewsets.ModelViewSet):
    """
    ViewSet для комментариев.
    - Создание: только авторизованные пользователи
    - Чтение: все пользователи
    - Обновление/Удаление: только автор комментария или администратор
    """
    serializer_class = CommentSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        queryset = Comment.objects.select_related('author', 'news_post').all()
        # Фильтрация по новости, если передан параметр
        news_post_id = self.request.query_params.get('news_post', None)
        if news_post_id:
            queryset = queryset.filter(news_post_id=news_post_id)
        return queryset

    def get_permissions(self):
        """
        Переопределяем права доступа для разных действий.
        """
        if self.action in ['create']:
            return [permissions.IsAuthenticated()]
        elif self.action in ['update', 'partial_update', 'destroy']:
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def perform_create(self, serializer):
        """Автор устанавливается автоматически из request.user"""
        serializer.save(author=self.request.user)

    def get_serializer_context(self):
        """Передаем request в контекст сериализатора"""
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    def update(self, request, *args, **kwargs):
        """Проверяем, что пользователь может редактировать только свои комментарии"""
        instance = self.get_object()
        if instance.author != request.user and not request.user.is_staff:
            return Response(
                {'detail': 'You do not have permission to edit this comment.'},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """Проверяем, что пользователь может удалять только свои комментарии или является админом"""
        instance = self.get_object()
        if instance.author != request.user and not request.user.is_staff:
            return Response(
                {'detail': 'You do not have permission to delete this comment.'},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=['get'], url_path='by-news/(?P<news_id>[^/.]+)')
    def by_news(self, request, news_id=None):
        """Получить все комментарии для конкретной новости"""
        comments = self.get_queryset().filter(news_post_id=news_id)
        serializer = self.get_serializer(comments, many=True)
        return Response(serializer.data)
