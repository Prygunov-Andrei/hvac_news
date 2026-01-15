from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    NewsPostViewSet, CommentViewSet, MediaUploadViewSet,
    SearchConfigurationViewSet, NewsDiscoveryRunViewSet, DiscoveryAPICallViewSet
)

router = DefaultRouter()
router.register(r'news', NewsPostViewSet, basename='news')
router.register(r'comments', CommentViewSet, basename='comments')
router.register(r'media', MediaUploadViewSet, basename='media')
router.register(r'search-config', SearchConfigurationViewSet, basename='search-config')
router.register(r'discovery-runs', NewsDiscoveryRunViewSet, basename='discovery-runs')
router.register(r'discovery-calls', DiscoveryAPICallViewSet, basename='discovery-calls')

urlpatterns = [
    path('', include(router.urls)),
]

