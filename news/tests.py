import os
import shutil
import tempfile
import zipfile
from io import BytesIO
from unittest.mock import patch, MagicMock
from PIL import Image
from django.test import TestCase
from django.core.files import File
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status
from .models import NewsPost, NewsMedia, Comment, MediaUpload
from .services import NewsImportService

User = get_user_model()

class NewsImportTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='test@news.com', password='password')
        self.temp_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_import_service(self):
        # Create a dummy zip file content
        md_content = """---
date: 2023-12-25 12:00
---

# [RU]
# Заголовок
Текст новости с картинкой ![Img](test.jpg)

# [EN]
# Title
News body with video [[video.mp4]]
"""
        # Create files
        md_path = os.path.join(self.temp_dir, 'post.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
            
        img_path = os.path.join(self.temp_dir, 'test.jpg')
        with open(img_path, 'wb') as f:
            f.write(b'fakeimage')
            
        vid_path = os.path.join(self.temp_dir, 'video.mp4')
        with open(vid_path, 'wb') as f:
            f.write(b'fakevideo')

        # Zip them
        zip_path = os.path.join(self.temp_dir, 'test.zip')
        with zipfile.ZipFile(zip_path, 'w') as z:
            z.write(md_path, 'post.md')
            z.write(img_path, 'test.jpg')
            z.write(vid_path, 'video.mp4')

        # Run Service
        service = NewsImportService(zip_path, user=self.user)
        news_post = service.process()

        # Assertions
        self.assertEqual(NewsPost.objects.count(), 1)
        self.assertEqual(news_post.title_ru, 'Заголовок')
        self.assertEqual(news_post.title_en, 'Title')
        
        # Check Media
        self.assertEqual(news_post.media.count(), 2)
        
        # Check link replacement
        self.assertIn('/media/news/', news_post.body_ru)
        self.assertIn('video', news_post.body_en)
        self.assertIn('src="/media/news/', news_post.body_en)

    def test_future_post_visibility(self):
        # Past post
        NewsPost.objects.create(
            title="Past", 
            body="Body", 
            status='published',
            pub_date=timezone.now() - timezone.timedelta(days=1)
        )
        # Future post
        NewsPost.objects.create(
            title="Future", 
            body="Body", 
            status='published',
            pub_date=timezone.now() + timezone.timedelta(days=1)
        )
        
        response = self.client.get('/api/news/')
        data = response.data
        if isinstance(data, dict) and 'results' in data:
            results = data['results']
        else:
            results = data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['title'], "Past")


class CommentTest(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(email='user1@test.com', password='password')
        self.user2 = User.objects.create_user(email='user2@test.com', password='password')
        self.news_post = NewsPost.objects.create(
            title="Test News",
            body="Test Body",
            status='published',
            pub_date=timezone.now() - timezone.timedelta(days=1)
        )
        self.client = APIClient()

    def test_create_comment_requires_auth(self):
        """Незарегистрированный пользователь не может создать комментарий"""
        response = self.client.post('/api/comments/', {
            'news_post': self.news_post.id,
            'text': 'Test comment'
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_comment_authenticated(self):
        """Авторизованный пользователь может создать комментарий"""
        self.client.force_authenticate(user=self.user1)
        response = self.client.post('/api/comments/', {
            'news_post': self.news_post.id,
            'text': 'Test comment'
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Comment.objects.count(), 1)
        self.assertEqual(Comment.objects.first().author, self.user1)

    def test_read_comments_public(self):
        """Все пользователи могут читать комментарии"""
        comment = Comment.objects.create(
            news_post=self.news_post,
            author=self.user1,
            text='Public comment'
        )
        response = self.client.get('/api/comments/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Проверяем, есть ли пагинация или это просто список
        data = response.data
        if isinstance(data, dict) and 'results' in data:
            self.assertEqual(len(data['results']), 1)
        else:
            self.assertEqual(len(data), 1)

    def test_update_own_comment(self):
        """Пользователь может редактировать только свои комментарии"""
        comment = Comment.objects.create(
            news_post=self.news_post,
            author=self.user1,
            text='Original text'
        )
        self.client.force_authenticate(user=self.user1)
        response = self.client.patch(f'/api/comments/{comment.id}/', {
            'text': 'Updated text'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        comment.refresh_from_db()
        self.assertEqual(comment.text, 'Updated text')

    def test_cannot_update_other_comment(self):
        """Пользователь не может редактировать чужие комментарии"""
        comment = Comment.objects.create(
            news_post=self.news_post,
            author=self.user1,
            text='Original text'
        )
        self.client.force_authenticate(user=self.user2)
        response = self.client.patch(f'/api/comments/{comment.id}/', {
            'text': 'Hacked text'
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_own_comment(self):
        """Пользователь может удалять только свои комментарии"""
        comment = Comment.objects.create(
            news_post=self.news_post,
            author=self.user1,
            text='To be deleted'
        )
        self.client.force_authenticate(user=self.user1)
        response = self.client.delete(f'/api/comments/{comment.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Comment.objects.count(), 0)

    def test_filter_comments_by_news(self):
        """Фильтрация комментариев по новости"""
        news_post2 = NewsPost.objects.create(
            title="News 2",
            body="Body 2",
            status='published',
            pub_date=timezone.now()
        )
        Comment.objects.create(
            news_post=self.news_post,
            author=self.user1,
            text='Comment 1'
        )
        Comment.objects.create(
            news_post=news_post2,
            author=self.user1,
            text='Comment 2'
        )
        response = self.client.get(f'/api/comments/?news_post={self.news_post.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Проверяем, есть ли пагинация или это просто список
        data = response.data
        if isinstance(data, dict) and 'results' in data:
            self.assertEqual(len(data['results']), 1)
        else:
            self.assertEqual(len(data), 1)


class NewsPostCRUDTest(TestCase):
    """Тесты для CRUD операций с новостями (Этап 5.1)"""
    
    def setUp(self):
        self.client = APIClient()
        self.admin_user = User.objects.create_user(
            email='admin@test.com',
            password='password',
            is_staff=True,
            is_superuser=True
        )
        self.regular_user = User.objects.create_user(
            email='user@test.com',
            password='password'
        )
        self.news_post = NewsPost.objects.create(
            title="Test News",
            body="Test Body",
            status='published',
            pub_date=timezone.now() - timezone.timedelta(days=1),
            author=self.admin_user
        )
    
    def test_admin_can_create_news(self):
        """Админ может создать новость через API"""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post('/api/news/', {
            'title': 'New News',
            'body': 'New Body',
            'pub_date': timezone.now().isoformat()
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(NewsPost.objects.count(), 2)
        news = NewsPost.objects.get(title='New News')
        self.assertEqual(news.author, self.admin_user)
        self.assertEqual(news.body, 'New Body')
    
    def test_regular_user_cannot_create_news(self):
        """Обычный пользователь получает 403 при попытке создать новость"""
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.post('/api/news/', {
            'title': 'Hacked News',
            'body': 'Hacked Body',
            'pub_date': timezone.now().isoformat()
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(NewsPost.objects.count(), 1)
    
    def test_unauthenticated_user_cannot_create_news(self):
        """Неавторизованный пользователь не может создать новость"""
        response = self.client.post('/api/news/', {
            'title': 'Anonymous News',
            'body': 'Anonymous Body',
            'pub_date': timezone.now().isoformat()
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(NewsPost.objects.count(), 1)
    
    def test_admin_can_update_news(self):
        """Админ может редактировать существующую новость"""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.patch(f'/api/news/{self.news_post.id}/', {
            'title': 'Updated Title',
            'body': 'Updated Body'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.news_post.refresh_from_db()
        self.assertEqual(self.news_post.title, 'Updated Title')
        self.assertEqual(self.news_post.body, 'Updated Body')
    
    def test_regular_user_cannot_update_news(self):
        """Обычный пользователь не может редактировать новость"""
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.patch(f'/api/news/{self.news_post.id}/', {
            'title': 'Hacked Title'
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.news_post.refresh_from_db()
        self.assertEqual(self.news_post.title, 'Test News')
    
    def test_admin_can_delete_news(self):
        """Админ может удалить новость"""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.delete(f'/api/news/{self.news_post.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(NewsPost.objects.count(), 0)
    
    def test_regular_user_cannot_delete_news(self):
        """Обычный пользователь не может удалить новость"""
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.delete(f'/api/news/{self.news_post.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(NewsPost.objects.count(), 1)
    
    def test_deleted_news_not_in_list(self):
        """После удаления новость не появляется в списке"""
        self.client.force_authenticate(user=self.admin_user)
        # Удаляем новость
        self.client.delete(f'/api/news/{self.news_post.id}/')
        # Проверяем, что её нет в списке
        response = self.client.get('/api/news/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        if isinstance(data, dict) and 'results' in data:
            self.assertEqual(len(data['results']), 0)
        else:
            self.assertEqual(len(data), 0)
    
    def test_admin_sees_all_news(self):
        """Админ видит все новости, включая будущие"""
        # Создаём новость из будущего
        future_news = NewsPost.objects.create(
            title="Future News",
            body="Future Body",
            status='published',
            pub_date=timezone.now() + timezone.timedelta(days=1),
            author=self.admin_user
        )
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get('/api/news/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        if isinstance(data, dict) and 'results' in data:
            results = data['results']
        else:
            results = data
        self.assertEqual(len(results), 2)  # Обе новости видны админу
    
    def test_regular_user_sees_only_published_news(self):
        """Обычный пользователь видит только опубликованные новости"""
        # Создаём новость из будущего
        future_news = NewsPost.objects.create(
            title="Future News",
            body="Future Body",
            status='published',
            pub_date=timezone.now() + timezone.timedelta(days=1),
            author=self.admin_user
        )
        response = self.client.get('/api/news/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        if isinstance(data, dict) and 'results' in data:
            results = data['results']
        else:
            results = data
        self.assertEqual(len(results), 1)  # Только опубликованная новость (будущая не показывается)
        self.assertEqual(results[0]['title'], 'Test News')
    
    def test_create_news_validation(self):
        """Валидация при создании новости"""
        self.client.force_authenticate(user=self.admin_user)
        
        # Пустой заголовок
        response = self.client.post('/api/news/', {
            'title': '',
            'body': 'Body',
            'pub_date': timezone.now().isoformat()
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        # Пустой текст
        response = self.client.post('/api/news/', {
            'title': 'Title',
            'body': '',
            'pub_date': timezone.now().isoformat()
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class MediaUploadTest(TestCase):
    """Тесты для загрузки медиафайлов (Этап 5.2)"""
    
    def setUp(self):
        self.client = APIClient()
        self.admin_user = User.objects.create_user(
            email='admin@test.com',
            password='password',
            is_staff=True,
            is_superuser=True
        )
        self.regular_user = User.objects.create_user(
            email='user@test.com',
            password='password'
        )
    
    def create_test_image(self, size=(100, 100), format='PNG'):
        """Создает тестовое изображение"""
        img = Image.new('RGB', size, color='red')
        img_io = BytesIO()
        img.save(img_io, format=format)
        img_io.seek(0)
        return SimpleUploadedFile(
            name='test.png',
            content=img_io.getvalue(),
            content_type='image/png'
        )
    
    def create_test_video(self, size_kb=100):
        """Создает тестовое видео (фейковое)"""
        content = b'fake video content' * (size_kb * 1024 // 18)
        return SimpleUploadedFile(
            name='test.mp4',
            content=content,
            content_type='video/mp4'
        )
    
    def test_admin_can_upload_image(self):
        """Админ может загрузить изображение и получить URL"""
        self.client.force_authenticate(user=self.admin_user)
        image = self.create_test_image()
        response = self.client.post('/api/media/', {
            'file': image,
            'media_type': 'image'
        }, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(MediaUpload.objects.count(), 1)
        self.assertIn('url', response.data)
        self.assertIn('file_size', response.data)
        self.assertEqual(response.data['media_type'], 'image')
        self.assertIsNotNone(response.data['url'])
    
    def test_admin_can_upload_video(self):
        """Админ может загрузить видео и получить URL"""
        self.client.force_authenticate(user=self.admin_user)
        video = self.create_test_video(size_kb=500)  # 500 KB
        response = self.client.post('/api/media/', {
            'file': video,
            'media_type': 'video'
        }, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(MediaUpload.objects.count(), 1)
        self.assertEqual(response.data['media_type'], 'video')
        self.assertIsNotNone(response.data['url'])
    
    def test_auto_detect_media_type(self):
        """Тип медиа определяется автоматически по расширению файла"""
        self.client.force_authenticate(user=self.admin_user)
        image = self.create_test_image()
        response = self.client.post('/api/media/', {
            'file': image
        }, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['media_type'], 'image')
    
    def test_regular_user_cannot_upload(self):
        """Обычный пользователь не может загружать файлы"""
        self.client.force_authenticate(user=self.regular_user)
        image = self.create_test_image()
        response = self.client.post('/api/media/', {
            'file': image,
            'media_type': 'image'
        }, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(MediaUpload.objects.count(), 0)
    
    def test_unauthenticated_user_cannot_upload(self):
        """Неавторизованный пользователь не может загружать файлы"""
        image = self.create_test_image()
        response = self.client.post('/api/media/', {
            'file': image,
            'media_type': 'image'
        }, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(MediaUpload.objects.count(), 0)
    
    def test_invalid_file_format(self):
        """Загрузка файла недопустимого формата возвращает 400"""
        self.client.force_authenticate(user=self.admin_user)
        invalid_file = SimpleUploadedFile(
            name='test.txt',
            content=b'not an image or video',
            content_type='text/plain'
        )
        response = self.client.post('/api/media/', {
            'file': invalid_file,
            'media_type': 'image'
        }, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('file', response.data)
    
    def test_image_size_limit(self):
        """Загрузка изображения больше лимита возвращает 400"""
        self.client.force_authenticate(user=self.admin_user)
        # Создаем большое изображение (>10MB)
        large_image = SimpleUploadedFile(
            name='large.png',
            content=b'x' * (11 * 1024 * 1024),  # 11 MB
            content_type='image/png'
        )
        response = self.client.post('/api/media/', {
            'file': large_image,
            'media_type': 'image'
        }, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('file', response.data)
    
    def test_video_size_limit(self):
        """Загрузка видео больше лимита возвращает 400"""
        self.client.force_authenticate(user=self.admin_user)
        # Создаем большое видео (>100MB)
        large_video = SimpleUploadedFile(
            name='large.mp4',
            content=b'x' * (101 * 1024 * 1024),  # 101 MB
            content_type='video/mp4'
        )
        response = self.client.post('/api/media/', {
            'file': large_video,
            'media_type': 'video'
        }, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('file', response.data)
    
    def test_mismatched_media_type(self):
        """Несоответствие типа медиа и формата файла возвращает 400"""
        self.client.force_authenticate(user=self.admin_user)
        image = self.create_test_image()
        response = self.client.post('/api/media/', {
            'file': image,
            'media_type': 'video'  # Неправильный тип
        }, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('media_type', response.data)
    
    def test_admin_can_delete_media(self):
        """Админ может удалить загруженный файл"""
        self.client.force_authenticate(user=self.admin_user)
        image = self.create_test_image()
        response = self.client.post('/api/media/', {
            'file': image,
            'media_type': 'image'
        }, format='multipart')
        media_id = response.data['id']
        
        response = self.client.delete(f'/api/media/{media_id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(MediaUpload.objects.count(), 0)
    
    def test_admin_can_list_media(self):
        """Админ может получить список загруженных файлов"""
        self.client.force_authenticate(user=self.admin_user)
        # Загружаем несколько файлов
        image1 = self.create_test_image()
        image2 = self.create_test_image()
        self.client.post('/api/media/', {'file': image1, 'media_type': 'image'}, format='multipart')
        self.client.post('/api/media/', {'file': image2, 'media_type': 'image'}, format='multipart')
        
        response = self.client.get('/api/media/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        if isinstance(data, dict) and 'results' in data:
            self.assertEqual(len(data['results']), 2)
        else:
            self.assertEqual(len(data), 2)


class NewsPostStatusTest(TestCase):
    """Тесты для статусов новостей и отложенной публикации (Этап 5.4)"""
    
    def setUp(self):
        self.client = APIClient()
        self.admin_user = User.objects.create_user(
            email='admin@test.com',
            password='password',
            is_staff=True,
            is_superuser=True
        )
        self.regular_user = User.objects.create_user(
            email='user@test.com',
            password='password'
        )
    
    def test_draft_not_in_public_api(self):
        """Черновик не появляется в публичном API"""
        draft = NewsPost.objects.create(
            title="Draft News",
            body="Draft Body",
            status='draft',
            pub_date=timezone.now() - timezone.timedelta(days=1),
            author=self.admin_user
        )
        response = self.client.get('/api/news/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        if isinstance(data, dict) and 'results' in data:
            results = data['results']
        else:
            results = data
        # Черновик не должен быть в списке
        news_ids = [item['id'] for item in results]
        self.assertNotIn(draft.id, news_ids)
    
    def test_scheduled_not_in_public_api_until_date(self):
        """Запланированная новость не появляется до наступления pub_date"""
        future_date = timezone.now() + timezone.timedelta(days=1)
        scheduled = NewsPost.objects.create(
            title="Scheduled News",
            body="Scheduled Body",
            status='scheduled',
            pub_date=future_date,
            author=self.admin_user
        )
        response = self.client.get('/api/news/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        if isinstance(data, dict) and 'results' in data:
            results = data['results']
        else:
            results = data
        # Запланированная новость не должна быть в списке
        news_ids = [item['id'] for item in results]
        self.assertNotIn(scheduled.id, news_ids)
    
    def test_admin_sees_drafts(self):
        """Админ видит все свои черновики через /api/news/drafts/"""
        draft1 = NewsPost.objects.create(
            title="Draft 1",
            body="Body 1",
            status='draft',
            author=self.admin_user
        )
        draft2 = NewsPost.objects.create(
            title="Draft 2",
            body="Body 2",
            status='draft',
            author=self.admin_user
        )
        published = NewsPost.objects.create(
            title="Published",
            body="Body",
            status='published',
            pub_date=timezone.now() - timezone.timedelta(days=1),
            author=self.admin_user
        )
        
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get('/api/news/drafts/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        draft_ids = [item['id'] for item in response.data]
        self.assertIn(draft1.id, draft_ids)
        self.assertIn(draft2.id, draft_ids)
        self.assertNotIn(published.id, draft_ids)
    
    def test_admin_sees_scheduled(self):
        """Админ видит все запланированные новости через /api/news/scheduled/"""
        future_date = timezone.now() + timezone.timedelta(days=1)
        scheduled1 = NewsPost.objects.create(
            title="Scheduled 1",
            body="Body 1",
            status='scheduled',
            pub_date=future_date,
            author=self.admin_user
        )
        scheduled2 = NewsPost.objects.create(
            title="Scheduled 2",
            body="Body 2",
            status='scheduled',
            pub_date=future_date,
            author=self.admin_user
        )
        published = NewsPost.objects.create(
            title="Published",
            body="Body",
            status='published',
            pub_date=timezone.now() - timezone.timedelta(days=1),
            author=self.admin_user
        )
        
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get('/api/news/scheduled/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        scheduled_ids = [item['id'] for item in response.data]
        self.assertIn(scheduled1.id, scheduled_ids)
        self.assertIn(scheduled2.id, scheduled_ids)
        self.assertNotIn(published.id, scheduled_ids)
    
    def test_regular_user_cannot_access_drafts(self):
        """Обычный пользователь не может получить доступ к черновикам"""
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.get('/api/news/drafts/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_regular_user_cannot_access_scheduled(self):
        """Обычный пользователь не может получить доступ к запланированным"""
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.get('/api/news/scheduled/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_manual_publish_endpoint(self):
        """Ручная публикация через /api/news/<id>/publish/ работает"""
        draft = NewsPost.objects.create(
            title="Draft",
            body="Body",
            status='draft',
            pub_date=timezone.now() + timezone.timedelta(days=1),  # Дата в будущем
            author=self.admin_user
        )
        
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post(f'/api/news/{draft.id}/publish/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'published')
        
        draft.refresh_from_db()
        self.assertEqual(draft.status, 'published')
        # Дата должна быть обновлена на текущую, если была в будущем
        self.assertLessEqual(draft.pub_date, timezone.now())
    
    def test_regular_user_cannot_publish(self):
        """Обычный пользователь не может опубликовать новость"""
        draft = NewsPost.objects.create(
            title="Draft",
            body="Body",
            status='draft',
            author=self.admin_user
        )
        
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.post(f'/api/news/{draft.id}/publish/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        draft.refresh_from_db()
        self.assertEqual(draft.status, 'draft')
    
    def test_create_with_status(self):
        """Можно создать новость со статусом"""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post('/api/news/', {
            'title': 'Scheduled News',
            'body': 'Body',
            'status': 'scheduled',
            'pub_date': (timezone.now() + timezone.timedelta(days=1)).isoformat()
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        news = NewsPost.objects.get(title='Scheduled News')
        self.assertEqual(news.status, 'scheduled')
    
    def test_published_with_future_date_becomes_scheduled(self):
        """Если статус published, но дата в будущем, статус меняется на scheduled"""
        self.client.force_authenticate(user=self.admin_user)
        future_date = timezone.now() + timezone.timedelta(days=1)
        response = self.client.post('/api/news/', {
            'title': 'Future News',
            'body': 'Body',
            'status': 'published',
            'pub_date': future_date.isoformat()
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        news = NewsPost.objects.get(title='Future News')
        # Статус должен быть автоматически изменен на scheduled
        self.assertEqual(news.status, 'scheduled')
    
    def test_scheduled_with_past_date_becomes_published(self):
        """Если статус scheduled, но дата в прошлом, статус меняется на published"""
        self.client.force_authenticate(user=self.admin_user)
        past_date = timezone.now() - timezone.timedelta(days=1)
        response = self.client.post('/api/news/', {
            'title': 'Past News',
            'body': 'Body',
            'status': 'scheduled',
            'pub_date': past_date.isoformat()
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        news = NewsPost.objects.get(title='Past News')
        # Статус должен быть автоматически изменен на published
        self.assertEqual(news.status, 'published')


class NewsPostTranslationTest(TestCase):
    """Тесты для автоперевода новостей (Этап 5.3)"""
    
    def setUp(self):
        self.client = APIClient()
        self.admin_user = User.objects.create_user(
            email='admin@test.com',
            password='password',
            is_staff=True,
            is_superuser=True
        )
        # Мокируем ответ OpenAI
        self.mock_openai_response = MagicMock()
        self.mock_openai_response.choices = [MagicMock()]
        self.mock_openai_response.choices[0].message.content = "Translated text"
    
    @patch('news.views.TranslationService')
    def test_create_news_with_auto_translate(self, mock_translation_service):
        """При создании новости с auto_translate=true заполняются все языковые поля"""
        # Настраиваем мок сервиса перевода
        mock_service_instance = MagicMock()
        mock_translation_service.return_value = mock_service_instance
        mock_service_instance.translate_news.return_value = {
            'en': {'title': 'English Title', 'body': 'English Body'},
            'de': {'title': 'German Title', 'body': 'German Body'},
            'pt': {'title': 'Portuguese Title', 'body': 'Portuguese Body'},
        }
        
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post('/api/news/', {
            'title': 'Test Title',
            'body': 'Test Body',
            'source_language': 'ru',
            'auto_translate': True,
            'pub_date': timezone.now().isoformat()
        })
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        news = NewsPost.objects.get(title='Test Title')
        
        # Проверяем, что сервис перевода был вызван
        mock_service_instance.translate_news.assert_called_once()
        
        # Проверяем, что source_language установлен
        self.assertEqual(news.source_language, 'ru')
    
    @patch('news.views.TranslationService')
    def test_auto_translate_false_no_translation(self, mock_translation_service):
        """При auto_translate=false переводы не выполняются"""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post('/api/news/', {
            'title': 'Test Title',
            'body': 'Test Body',
            'source_language': 'ru',
            'auto_translate': False,
            'pub_date': timezone.now().isoformat()
        })
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Проверяем, что сервис перевода не вызывался
        mock_translation_service.assert_not_called()
    
    @patch('news.views.TranslationService')
    def test_translation_error_does_not_block_creation(self, mock_translation_service):
        """Ошибка API перевода не блокирует создание новости"""
        # Настраиваем мок для выброса ошибки
        mock_service_instance = MagicMock()
        mock_translation_service.return_value = mock_service_instance
        mock_service_instance.translate_news.side_effect = Exception("API Error")
        
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post('/api/news/', {
            'title': 'Test Title',
            'body': 'Test Body',
            'source_language': 'ru',
            'auto_translate': True,
            'pub_date': timezone.now().isoformat()
        })
        
        # Новость должна быть создана даже при ошибке перевода
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(NewsPost.objects.count(), 1)
    
    @patch('news.views.TranslationService')
    def test_update_news_with_auto_translate(self, mock_translation_service):
        """При обновлении новости с auto_translate=true выполняется перевод"""
        # Создаем новость
        news = NewsPost.objects.create(
            title="Original Title",
            body="Original Body",
            source_language='ru',
            status='published',
            pub_date=timezone.now() - timezone.timedelta(days=1),
            author=self.admin_user
        )
        
        # Настраиваем мок сервиса перевода
        mock_service_instance = MagicMock()
        mock_translation_service.return_value = mock_service_instance
        mock_service_instance.translate_news.return_value = {
            'en': {'title': 'English Title', 'body': 'English Body'},
            'de': {'title': 'German Title', 'body': 'German Body'},
            'pt': {'title': 'Portuguese Title', 'body': 'Portuguese Body'},
        }
        
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.patch(f'/api/news/{news.id}/', {
            'title': 'Updated Title',
            'body': 'Updated Body',
            'auto_translate': True
        })
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Проверяем, что сервис перевода был вызван
        mock_service_instance.translate_news.assert_called_once()
    
    def test_source_language_validation(self):
        """Валидация исходного языка"""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post('/api/news/', {
            'title': 'Test Title',
            'body': 'Test Body',
            'source_language': 'invalid',
            'pub_date': timezone.now().isoformat()
        })
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('source_language', response.data)
