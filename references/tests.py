from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from .models import Manufacturer, Brand, NewsResource

class ReferencesTests(APITestCase):
    def setUp(self):
        # Создаем тестовые данные
        self.manufacturer = Manufacturer.objects.create(
            name="Test Manufacturer",
            description="Test Description RU",
            description_en="Test Description EN"
        )
        self.brand = Brand.objects.create(
            manufacturer=self.manufacturer,
            name="Test Brand",
            description="Brand Description RU",
            description_en="Brand Description EN"
        )
        self.resource = NewsResource.objects.create(
            name="Test Resource",
            url="http://example.com",
            description="Resource Description RU"
        )

    def test_list_manufacturers(self):
        url = reverse('manufacturer-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name'], "Test Manufacturer")

    def test_list_brands(self):
        url = reverse('brand-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name'], "Test Brand")
        self.assertEqual(response.data[0]['manufacturer'], self.manufacturer.id)

    def test_translation_fallback(self):
        # Проверка, что приходят поля переводов (по умолчанию djangorestframework возвращает все поля модели)
        url = reverse('manufacturer-list')
        response = self.client.get(url)
        # modeltranslation добавляет поля description_ru, description_en и т.д.
        self.assertIn('description_ru', response.data[0])
        self.assertIn('description_en', response.data[0])
        self.assertEqual(response.data[0]['description_ru'], "Test Description RU")
        self.assertEqual(response.data[0]['description_en'], "Test Description EN")

    def test_public_access(self):
        # Проверка, что доступ открыт без токена
        url = reverse('newsresource-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
