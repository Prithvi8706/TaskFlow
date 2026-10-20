from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import ProjectForm
from .models import Project, Task


# ---------------------------------------------------------------- projects


@login_required
def project_list(request):
    projects = (
        Project.objects.filter(owner=request.user)
        .annotate(
            total_tasks=Count("tasks"),
            completed_tasks=Count("tasks", filter=Q(tasks__status=Task.Status.COMPLETED)),
        )
        .order_by("deadline", "name")
    )
    return render(request, "tracker/project_list.html", {"projects": projects})


@login_required
def project_detail(request, pk):
    project = get_object_or_404(Project, pk=pk, owner=request.user)
    tasks = project.tasks.select_related("milestone", "category").order_by("deadline", "title")
    milestones = project.milestones.annotate(
        total_tasks=Count("tasks"),
        completed_tasks=Count("tasks", filter=Q(tasks__status=Task.Status.COMPLETED)),
    )
    counts = tasks.aggregate(
        total=Count("task_id"),
        completed=Count("task_id", filter=Q(status=Task.Status.COMPLETED)),
    )
    return render(
        request,
        "tracker/project_detail.html",
        {"project": project, "tasks": tasks, "milestones": milestones, "counts": counts},
    )


@login_required
def project_create(request):
    form = ProjectForm(request.POST or None, owner=request.user)
    if request.method == "POST" and form.is_valid():
        project = form.save()
        messages.success(request, f"Project “{project.name}” created.")
        return redirect("project_detail", pk=project.pk)
    return render(request, "tracker/project_form.html", {"form": form})


@login_required
def project_edit(request, pk):
    project = get_object_or_404(Project, pk=pk, owner=request.user)
    form = ProjectForm(request.POST or None, instance=project, owner=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Project updated.")
        return redirect("project_detail", pk=project.pk)
    return render(request, "tracker/project_form.html", {"form": form, "project": project})


@login_required
def project_delete(request, pk):
    project = get_object_or_404(Project, pk=pk, owner=request.user)
    if request.method == "POST":
        name = project.name
        project.delete()
        messages.success(request, f"Project “{name}” deleted.")
        return redirect("project_list")
    return render(
        request,
        "tracker/confirm_delete.html",
        {
            "object": project,
            "kind": "project",
            "warning": "All of its milestones, tasks and task history will be deleted too.",
            "cancel_url": reverse("project_list"),
        },
    )
