import json
import logging

from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .models import CrewRun, GeneratedDocument
from .services.documentation import extract_owner_repo
from .tasks.celery_tasks import run_crew_task, run_multiple_crews_task

logger = logging.getLogger(__name__)


@require_http_methods(["POST"])
def generate_documentation(request):
    """Dispatch an async crew run for a single repository URL."""
    repo_url = request.POST.get('repo_url', '').strip()
    if not repo_url:
        return render(
            request,
            'mcp_manager/documentation_interface.html',
            {'error': 'Please provide a repository URL.'},
        )

    try:
        owner, repo_name = extract_owner_repo(repo_url)
    except ValueError as e:
        return render(request, 'mcp_manager/documentation_interface.html', {'error': str(e)})

    task = run_crew_task.delay(owner=owner, repo=repo_name)  # type: ignore
    return render(
        request,
        'mcp_manager/documentation_interface.html',
        {
            'task_id': task.id,
            'task_status': 'PENDING',
            'repo_submitted': f'{owner}/{repo_name}',
        },
    )

def documentation_interface(request):
    latest_document = GeneratedDocument.objects.select_related("repository").order_by("-timestamp").first()
    context = {}
    if latest_document is not None:
        context["documentation"] = latest_document.content
        context["repository"] = latest_document.repository
    return render(request, 'mcp_manager/documentation_interface.html', context)


@require_http_methods(["POST"])
def generate_documentation_multiple(request):
    """Parse multiple GitHub URLs from textarea and dispatch a Celery batch task."""
    urls_text = request.POST.get("repo_urls", "").strip()
    if not urls_text:
        return render(
            request,
            "mcp_manager/documentation_interface.html",
            {"error": "Please provide at least one repository URL."},
        )

    repos = []
    errors = []
    for line in urls_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            owner, repo_name = extract_owner_repo(line)
            repos.append({"owner": owner, "repo": repo_name})
        except ValueError as e:
            errors.append(f"{line}: {e}")

    if errors:
        return render(
            request,
            "mcp_manager/documentation_interface.html",
            {"error": "Invalid URL(s): " + "; ".join(errors)},
        )

    if not repos:
        return render(
            request,
            "mcp_manager/documentation_interface.html",
            {"error": "No valid repository URLs found."},
        )

    task = run_multiple_crews_task.delay(repos)  # type: ignore
    return render(
        request,
        "mcp_manager/documentation_interface.html",
        {
            "batch_task_id": task.id,
            "repos_submitted": repos,
            "task_status": "PENDING",
        },
    )


@require_http_methods(["POST"])
def run_crew(request):
    """Trigger an async crew run and return the Celery task ID.

    Expected JSON body for a single repo:
        {"owner": "github", "repo": "github-mcp-server"}

    Expected JSON body for multiple repos:
        {"repos": [{"owner": "github", "repo": "github-mcp-server"}, ...]}
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

    if "repos" in body:
        repos = body["repos"]
        if not isinstance(repos, list) or not repos:
            return JsonResponse({"error": "'repos' must be a non-empty list."}, status=400)

        normalized: list[dict[str, str]] = []
        for i, item in enumerate(repos):
            if not isinstance(item, dict):
                return JsonResponse({"error": f"'repos[{i}]' must be an object with 'owner' and 'repo'."}, status=400)
            owner = str(item.get("owner", "")).strip()
            repo_name = str(item.get("repo", "")).strip()
            if not owner or not repo_name:
                return JsonResponse({"error": f"'repos[{i}]' must include non-empty 'owner' and 'repo'."}, status=400)
            normalized.append({"owner": owner, "repo": repo_name})

        task = run_multiple_crews_task.delay(normalized)  # type: ignore
    elif "owner" in body and "repo" in body:
        owner = str(body["owner"]).strip()
        repo_name = str(body["repo"]).strip()
        if not owner or not repo_name:
            return JsonResponse({"error": "'owner' and 'repo' must be non-empty strings."}, status=400)
        task = run_crew_task.delay(owner=owner, repo=repo_name)  # type: ignore
    else:
        return JsonResponse(
            {"error": "Request must include either 'owner' and 'repo' or 'repos'."},
            status=400,
        )

    return JsonResponse({"task_id": task.id, "status": "PENDING"}, status=202)


@require_http_methods(["GET"])
def report_history(request):
    """Show the most recent generated reports across all repositories."""
    documents = GeneratedDocument.objects.select_related("repository").order_by("-timestamp")[:20]
    return render(request, "mcp_manager/report_history.html", {"documents": documents})


@require_http_methods(["GET"])
def crew_status(request, task_id: str):
    """Return the status and result of a Celery task by ID.

    Possible statuses: PENDING, STARTED, SUCCESS, FAILURE.
    """
    result = run_crew_task.AsyncResult(task_id)  # type: ignore
    response = {
        "task_id": task_id,
        "status": result.status,
    }

    try:
        run = CrewRun.objects.get(task_id=task_id)
        response["repository"] = f"{run.repository.owner}/{run.repository.name}"
        if run.status == CrewRun.Status.FAILURE:
            response["error"] = run.status
            response["message"] = run.error_message
    except CrewRun.DoesNotExist:
        pass

    if result.status == "SUCCESS":
        payload = result.result
        if isinstance(payload, dict):
            response["result"] = payload
        else:
            response["result"] = {"raw_output": str(payload)}
    elif result.status == "FAILURE":
        exc = result.result
        if isinstance(exc, Exception):
            response["error"] = type(exc).__name__
            response["message"] = str(exc)
        else:
            response["error"] = str(exc)

    return JsonResponse(response)
