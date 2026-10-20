from django import forms

from .models import Category, Milestone, Project, Tag, Task, TaskDependency


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


class ProjectCreateForm(ProjectForm):
    """Project form with optional initial milestones, saved atomically by the view."""

    initial_milestones = forms.CharField(
        required=False,
        label="Initial milestones",
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Design\nBuild\nLaunch"}),
        help_text="One per line. The project and its milestones are created in a single transaction.",
    )

    def clean_initial_milestones(self):
        names, seen = [], set()
        for line in self.cleaned_data["initial_milestones"].splitlines():
            name = line.strip()
            if not name:
                continue
            if len(name) > 120:
                raise forms.ValidationError(f"“{name[:30]}…” is longer than 120 characters.")
            if name.lower() in seen:
                raise forms.ValidationError(f"“{name}” is listed twice.")
            seen.add(name.lower())
            names.append(name)
        return names


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
        if cleaned.get("status") == Task.Status.COMPLETED and self.instance.pk:
            open_prereqs = self.instance.open_prerequisites()
            if open_prereqs:
                names = ", ".join(t.title for t in open_prereqs)
                self.add_error("status", f"Finish its prerequisites first: {names}.")
        return cleaned


class TagForm(OwnedNameMixin, forms.ModelForm):
    class Meta:
        model = Tag
        fields = ["name"]
        widgets = {"name": forms.TextInput(attrs={"placeholder": "e.g. urgent"})}


def find_dependency_path(start_id, target_id, edges):
    """
    Depth-first search over prerequisite edges (task_id -> [depends_on_task_id]).
    Returns the list of task ids from start to target if target is reachable,
    otherwise None.
    """
    stack = [(start_id, [start_id])]
    seen = set()
    while stack:
        node, path = stack.pop()
        if node == target_id:
            return path
        if node in seen:
            continue
        seen.add(node)
        for nxt in edges.get(node, ()):
            stack.append((nxt, path + [nxt]))
    return None


class TaskDependencyForm(forms.Form):
    depends_on_task = forms.ModelChoiceField(queryset=Task.objects.none(), label="Prerequisite task")

    def __init__(self, *args, task, **kwargs):
        super().__init__(*args, **kwargs)
        self.task = task
        # The task itself stays selectable on purpose: picking it shows the
        # self-dependency rejection instead of silently hiding the option.
        self.fields["depends_on_task"].queryset = Task.objects.filter(project=task.project).order_by("title")

    def clean_depends_on_task(self):
        prereq = self.cleaned_data["depends_on_task"]
        if prereq.pk == self.task.pk:
            raise forms.ValidationError("A task cannot depend on itself.")
        if TaskDependency.objects.filter(task=self.task, depends_on_task=prereq).exists():
            raise forms.ValidationError("This prerequisite is already linked.")

        # Adding task -> prereq creates a cycle if task is already reachable from prereq.
        edges = {}
        for t_id, d_id in TaskDependency.objects.filter(task__project=self.task.project).values_list(
            "task_id", "depends_on_task_id"
        ):
            edges.setdefault(t_id, []).append(d_id)
        path = find_dependency_path(prereq.pk, self.task.pk, edges)
        if path:
            titles = dict(Task.objects.filter(pk__in=path).values_list("pk", "title"))
            chain = " → ".join(titles[i] for i in [self.task.pk] + path)
            raise forms.ValidationError(f"That would create a cycle: {chain}.")
        return prereq

    def save(self):
        return TaskDependency.objects.create(task=self.task, depends_on_task=self.cleaned_data["depends_on_task"])


class TaskFilterForm(forms.Form):
    SORT_CHOICES = [
        ("deadline", "Deadline (soonest first)"),
        ("priority", "Priority (highest first)"),
        ("created", "Created (newest first)"),
    ]

    q = forms.CharField(required=False, widget=forms.TextInput(attrs={"type": "search", "placeholder": "Search title or description"}))
    status = forms.ChoiceField(required=False, choices=[("", "Any status")] + Task.Status.choices)
    priority = forms.ChoiceField(required=False, choices=[("", "Any priority")] + Task.Priority.choices)
    project = forms.ModelChoiceField(required=False, queryset=Project.objects.none(), empty_label="Any project")
    category = forms.ModelChoiceField(required=False, queryset=Category.objects.none(), empty_label="Any category")
    tag = forms.ModelChoiceField(required=False, queryset=Tag.objects.none(), empty_label="Any tag")
    sort = forms.ChoiceField(required=False, choices=SORT_CHOICES)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["project"].queryset = Project.objects.filter(owner=user)
        self.fields["category"].queryset = Category.objects.filter(owner=user)
        self.fields["tag"].queryset = Tag.objects.filter(owner=user)
