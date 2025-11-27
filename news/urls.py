from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import NewsPostViewSet

router = DefaultRouter()
router.register(r'news', NewsPostViewSet, basename='news')

urlpatterns = [
    path('', include(router.urls)),
]

