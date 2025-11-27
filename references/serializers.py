from rest_framework import serializers
from .models import Manufacturer, Brand, NewsResource

class ManufacturerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Manufacturer
        fields = '__all__'

class BrandSerializer(serializers.ModelSerializer):
    manufacturer_name = serializers.ReadOnlyField(source='manufacturer.name')

    class Meta:
        model = Brand
        fields = '__all__'

class NewsResourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsResource
        fields = '__all__'

