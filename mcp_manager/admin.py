from django.contrib import admin

from .models import CrewRun, GeneratedDocument, GitHubRepository


@admin.register(GitHubRepository)
class GitHubRepositoryAdmin(admin.ModelAdmin):
    list_display = ("owner", "name", "url")
    search_fields = ("owner", "name")


@admin.register(GeneratedDocument)
class GeneratedDocumentAdmin(admin.ModelAdmin):
    list_display = ("repository", "format", "timestamp")
    list_filter = ("format", "timestamp")
    search_fields = ("repository__owner", "repository__name")


@admin.register(CrewRun)
class CrewRunAdmin(admin.ModelAdmin):
    list_display = ("repository", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("repository__owner", "repository__name", "task_id")
