import os
import shutil
import tempfile
import zipfile
from django.test import TestCase
from django.core.files import File
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import NewsPost, NewsMedia
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
            pub_date=timezone.now() - timezone.timedelta(days=1)
        )
        # Future post
        NewsPost.objects.create(
            title="Future", 
            body="Body", 
            pub_date=timezone.now() + timezone.timedelta(days=1)
        )
        
        response = self.client.get('/api/news/')
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['title'], "Past")
