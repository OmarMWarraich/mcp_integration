from django.db import models
from django.utils import timezone

# Create your models here.
class GitHubRepository(models.Model):
    owner = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    url = models.URLField(blank=True, null=True)

class GeneratedDocument(models.Model):
    repository = models.ForeignKey("GitHubRepository", on_delete=models.CASCADE)
    content = models.TextField()
    timestamp = models.DateTimeField(default=timezone.now)
    format = models.CharField(max_length=50, default="markdown")