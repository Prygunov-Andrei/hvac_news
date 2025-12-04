from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import NewsPostViewSet, CommentViewSet

router = DefaultRouter()
router.register(r'news', NewsPostViewSet, basename='news')
router.register(r'comments', CommentViewSet, basename='comments')

urlpatterns = [
    path('', include(router.urls)),
]

