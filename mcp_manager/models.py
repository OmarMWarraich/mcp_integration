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
    task_id = models.CharField(max_length=255, blank=True, db_index=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.repository} ({self.format}, {self.timestamp:%Y-%m-%d %H:%M})"


class CrewRun(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING"
        STARTED = "STARTED"
        SUCCESS = "SUCCESS"
        FAILURE = "FAILURE"

    task_id = models.CharField(max_length=255, unique=True, db_index=True)
    repository = models.ForeignKey("GitHubRepository", on_delete=models.CASCADE, related_name="runs")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.repository} — {self.status} ({self.task_id[:8]})"