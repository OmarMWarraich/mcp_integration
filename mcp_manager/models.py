from django.db import models
from django.utils import timezone


class GitHubRepository(models.Model):
    owner = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    url = models.URLField(blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner", "name"], name="unique_owner_name"),
        ]
        verbose_name_plural = "GitHub repositories"

    def __str__(self):
        return f"{self.owner}/{self.name}"


class GeneratedDocument(models.Model):
    class Format(models.TextChoices):
        MARKDOWN = "markdown"
        HTML = "html"

    repository = models.ForeignKey("GitHubRepository", on_delete=models.CASCADE, related_name="documents")
    content = models.TextField()
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    format = models.CharField(max_length=50, choices=Format.choices, default=Format.MARKDOWN)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.repository} ({self.format}, {self.timestamp:%Y-%m-%d %H:%M})"