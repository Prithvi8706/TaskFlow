from django import forms

from .models import Category, Milestone, Project, Tag, Task


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, **kwargs):
        super().__init__(format="%Y-%m-%d", **kwargs)


class OwnedNameMixin:
    """
    Enforce UNIQUE(owner, name) with a friendly message. `owner` is not a form
    field, so Django's own constraint validation skips this constraint.
    """

    name_field = "name"

    def __init__(self, *args, owner, **kwargs):
        self.owner = owner
        super().__init__(*args, **kwargs)

    def clean_name(self):
        name = self.cleaned_data[self.name_field].strip()
        qs = self._meta.model.objects.filter(owner=self.owner, name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f"You already have a {self._meta.model._meta.verbose_name} with this name.")
        return name

    def save(self, commit=True):
        self.instance.owner = self.owner
        return super().save(commit=commit)


class ProjectForm(OwnedNameMixin, forms.ModelForm):
    class Meta:
        model = Project
        fields = ["name", "description", "status", "start_date", "deadline"]
        widgets = {
            "start_date": DateInput(),
            "deadline": DateInput(),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        cleaned = super().clean()
        start, deadline = cleaned.get("start_date"), cleaned.get("deadline")
        if start and deadline and deadline < start:
            self.add_error("deadline", "Deadline cannot be before the start date.")
        return cleaned


class MilestoneForm(forms.ModelForm):
    class Meta:
        model = Milestone
        fields = ["name", "description", "status", "deadline"]
        widgets = {"deadline": DateInput(), "description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, project, **kwargs):
        self.project = project
        super().__init__(*args, **kwargs)

    def clean_name(self):
        # UNIQUE(project_id, name): `project` is not a form field, so check it here.
        name = self.cleaned_data["name"].strip()
        qs = Milestone.objects.filter(project=self.project, name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("This project already has a milestone with this name.")
        return name

    def save(self, commit=True):
        self.instance.project = self.project
        return super().save(commit=commit)


class CategoryForm(OwnedNameMixin, forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name"]
        widgets = {"name": forms.TextInput(attrs={"placeholder": "e.g. Backend"})}


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ["title", "description", "project", "milestone", "category", "priority", "status", "deadline", "tags"]
        widgets = {
            "deadline": DateInput(),
            "description": forms.Textarea(attrs={"rows": 4}),
            "tags": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        # Only offer rows the user owns, so a forged POST cannot attach foreign rows.
        self.fields["project"].queryset = Project.objects.filter(owner=user)
        self.fields["milestone"].queryset = Milestone.objects.filter(project__owner=user).select_related("project")
        self.fields["milestone"].label_from_instance = lambda m: f"{m.project.name} · {m.name}"
        self.fields["category"].queryset = Category.objects.filter(owner=user)
        self.fields["tags"].queryset = Tag.objects.filter(owner=user)
        self.fields["tags"].help_text = "Rows are stored in the task_tag junction table."

    def clean(self):
        cleaned = super().clean()
        project, milestone, deadline = cleaned.get("project"), cleaned.get("milestone"), cleaned.get("deadline")
        if project and milestone and milestone.project_id != project.pk:
            self.add_error("milestone", "This milestone belongs to a different project.")
        if project and deadline and deadline < project.start_date:
            self.add_error("deadline", f"Deadline is before the project starts ({project.start_date:%b %d, %Y}).")
        return cleaned


class TagForm(OwnedNameMixin, forms.ModelForm):
    class Meta:
        model = Tag
        fields = ["name"]
        widgets = {"name": forms.TextInput(attrs={"placeholder": "e.g. urgent"})}
