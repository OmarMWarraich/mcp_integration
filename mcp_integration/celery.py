import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mcp_integration.settings")

app = Celery("mcp_integration")

# Load Celery config from Django settings using the CELERY_ namespace.
# Expected settings: CELERY_BROKER_URL, CELERY_RESULT_BACKEND
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Explicitly import the crew task module to ensure registration.
import mcp_manager.tasks.celery_tasks  # noqa: E402
