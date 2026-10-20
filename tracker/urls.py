from django.urls import path

from . import views

urlpatterns = [
    path("projects/", views.project_list, name="project_list"),
    path("projects/new/", views.project_create, name="project_create"),
    path("projects/<int:pk>/", views.project_detail, name="project_detail"),
    path("projects/<int:pk>/edit/", views.project_edit, name="project_edit"),
    path("projects/<int:pk>/delete/", views.project_delete, name="project_delete"),
    path("projects/<int:project_pk>/milestones/new/", views.milestone_create, name="milestone_create"),
    path("milestones/<int:pk>/edit/", views.milestone_edit, name="milestone_edit"),
    path("milestones/<int:pk>/delete/", views.milestone_delete, name="milestone_delete"),
]
