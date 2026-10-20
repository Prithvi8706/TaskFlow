from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import MilestoneForm, ProjectForm
from .models import Milestone, Project, Task


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


# -------------------------------------------------------------- milestones


@login_required
def milestone_create(request, project_pk):
    project = get_object_or_404(Project, pk=project_pk, owner=request.user)
    form = MilestoneForm(request.POST or None, project=project)
    if request.method == "POST" and form.is_valid():
        milestone = form.save()
        messages.success(request, f"Milestone “{milestone.name}” added.")
        return redirect("project_detail", pk=project.pk)
    return render(request, "tracker/milestone_form.html", {"form": form, "project": project})


@login_required
def milestone_edit(request, pk):
    milestone = get_object_or_404(Milestone, pk=pk, project__owner=request.user)
    project = milestone.project
    form = MilestoneForm(request.POST or None, instance=milestone, project=project)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Milestone updated.")
        return redirect("project_detail", pk=project.pk)
    return render(
        request, "tracker/milestone_form.html", {"form": form, "project": project, "milestone": milestone}
    )


@login_required
def milestone_delete(request, pk):
    milestone = get_object_or_404(Milestone, pk=pk, project__owner=request.user)
    project = milestone.project
    if request.method == "POST":
        milestone.delete()
        messages.success(request, f"Milestone “{milestone.name}” deleted.")
        return redirect("project_detail", pk=project.pk)
    return render(
        request,
        "tracker/confirm_delete.html",
        {
            "object": milestone,
            "kind": "milestone",
            "warning": "Its tasks stay in the project but are no longer linked to a milestone.",
            "cancel_url": reverse("project_detail", args=[project.pk]),
        },
    )
