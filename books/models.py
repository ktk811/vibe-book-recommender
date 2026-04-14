from django.db import models

class User(models.Model):
    username = models.CharField(max_length=150, primary_key=True)
    password = models.CharField(max_length=128)
    class Meta:
        db_table = 'users'

class Book(models.Model):
    title = models.CharField(max_length=500, db_index=True)
    authors = models.CharField(max_length=500, blank=True)
    description = models.TextField(blank=True)
    avg_rating = models.FloatField(default=0)
    ratings_count = models.IntegerField(default=0)
    url = models.URLField(max_length=1000, blank=True)
    image_url = models.URLField(max_length=1000, blank=True)
    genres = models.CharField(max_length=500, blank=True)
    embedding = models.TextField(blank=True)  # JSON list of floats
    class Meta:
        db_table = 'books'

class Library(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_column='username', to_field='username')
    title = models.CharField(max_length=500)
    url = models.CharField(max_length=1000, blank=True)
    class Meta:
        db_table = 'library'
        unique_together = ('user', 'title')
