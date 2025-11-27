from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ManufacturerViewSet, BrandViewSet, NewsResourceViewSet

router = DefaultRouter()
router.register(r'manufacturers', ManufacturerViewSet)
router.register(r'brands', BrandViewSet)
router.register(r'resources', NewsResourceViewSet)

urlpatterns = [
    path('', include(router.urls)),
]

