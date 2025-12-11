from rest_framework import viewsets, permissions
from .models import Manufacturer, Brand, NewsResource
from .serializers import ManufacturerSerializer, BrandSerializer, NewsResourceSerializer

class ManufacturerViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Manufacturer.objects.all()
    serializer_class = ManufacturerSerializer
    permission_classes = [permissions.AllowAny] # Доступно всем для чтения

class BrandViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Brand.objects.select_related('manufacturer').all()
    serializer_class = BrandSerializer
    permission_classes = [permissions.AllowAny]

class NewsResourceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = NewsResource.objects.all()
    serializer_class = NewsResourceSerializer
    permission_classes = [permissions.AllowAny]
