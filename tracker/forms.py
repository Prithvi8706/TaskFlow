from django import forms

from .models import Milestone, Project


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
