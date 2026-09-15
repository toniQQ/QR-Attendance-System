import re

from django import forms
from django.core.exceptions import ValidationError
from django.utils.text import slugify

from .models import Attendee, Event, EventBrand, Institution, MeetingMaterial

HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}){1,2}$")


def _validate_hex(value):
    if value and not HEX_RE.match(value):
        raise ValidationError("Enter a valid hex color (e.g. #4f46e5).")


class EventForm(forms.ModelForm):
    # branding fields
    primary_color = forms.CharField(
        required=False, validators=[_validate_hex], initial="#4f46e5"
    )
    accent_color = forms.CharField(
        required=False, validators=[_validate_hex], initial="#14b8a6"
    )
    gradient_from = forms.CharField(
        required=False, validators=[_validate_hex], initial="#4f46e5"
    )
    gradient_to = forms.CharField(
        required=False, validators=[_validate_hex], initial="#0f172a"
    )
    greeting_message = forms.CharField(
        required=False, max_length=300, widget=forms.Textarea(attrs={"rows": 2})
    )
    welcome_subtitle = forms.CharField(
        required=False, max_length=300, widget=forms.Textarea(attrs={"rows": 2})
    )
    show_event_info = forms.BooleanField(required=False, initial=True)
    logo_align = forms.ChoiceField(
        required=False,
        choices=[("", "Default (center)")] + EventBrand.LogoAlign.choices,
        initial=EventBrand.LogoAlign.CENTER,
    )

    logo = forms.ImageField(
        required=False,
        widget=forms.FileInput,
        help_text="Add one logo at a time. Save again to add another.",
    )

    attending_institutions = forms.ModelMultipleChoiceField(
        queryset=Institution.objects.all(),
        required=False,
        label="Institutions attending",
        widget=forms.SelectMultiple,
        help_text="Attendees can pick from this list on the check-in page.",
    )
    institution_new = forms.CharField(
        required=False,
        max_length=120,
        label="…or add a new institution",
        widget=forms.TextInput(attrs={"placeholder": "New institution name"}),
    )

    material_kind = forms.ChoiceField(
        required=False,
        choices=MeetingMaterial.Kind.choices,
        label="Material type",
    )
    material_title = forms.CharField(
        required=False, max_length=200, label="Title"
    )
    material_body = forms.CharField(
        required=False,
        label="Details",
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    material_file = forms.FileField(required=False, label="File (optional)")
    material_link = forms.URLField(required=False, label="Link (optional)")

    class Meta:
        model = Event
        fields = [
            "name",
            "slug",
            "description",
            "date",
            "end_date",
            "start_time",
            "end_time",
            "venue",
            "capacity",
            "status",
            "sessions",
            "morning_label",
            "afternoon_label",
            "attending_institutions",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
            "description": forms.Textarea(attrs={"rows": 4}),
        }

    def clean(self):
        cleaned = super().clean()
        for key in ("primary_color", "accent_color", "gradient_from", "gradient_to"):
            value = cleaned.get(key)
            if value:
                cleaned[key] = value.lower()
        material_used = any(
            cleaned.get(key)
            for key in ("material_kind", "material_body", "material_file", "material_link")
        )
        if material_used and not (cleaned.get("material_title") or "").strip():
            self.add_error("material_title", "Add a title for the material.")
        start = cleaned.get("date")
        end = cleaned.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", "End date must be on or after the start date.")
        return cleaned

    def clean_slug(self):
        slug = self.cleaned_data.get("slug")
        if not slug:
            slug = slugify(self.cleaned_data.get("name", ""))
        if not slug:
            raise ValidationError("Enter a name or custom slug.")
        if Event.objects.filter(slug=slug).exclude(pk=self.instance.pk).exists():
            raise ValidationError("That slug is already taken.")
        return slug


class CheckInForm(forms.Form):
    full_name = forms.CharField(
        max_length=120,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Your full name",
                "autocomplete": "name",
            }
        ),
    )
    phone = forms.CharField(
        required=False,
        max_length=20,
        widget=forms.TextInput(
            attrs={"placeholder": "Phone (optional)", "autocomplete": "tel"}
        ),
    )
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(
            attrs={"placeholder": "Email (optional)", "autocomplete": "email"}
        ),
    )
    institution_other = forms.CharField(
        required=False,
        max_length=120,
        label="Your institution",
        widget=forms.TextInput(
            attrs={"placeholder": "Type your institution", "data-institution-other": "true"}
        ),
    )

    def __init__(self, *args, institution_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["institution"] = forms.ChoiceField(
            required=False,
            label="Institution",
            widget=forms.Select(attrs={"data-institution-select": "true"}),
        )
        choices = [("", "Select your institution (optional)")]
        choices += [(pk, name) for pk, name in (institution_choices or [])]
        choices.append(("__other__", "Other — type it below"))
        self.fields["institution"].choices = choices

    def clean(self):
        cleaned = super().clean()
        if (
            cleaned.get("institution") == "__other__"
            and not (cleaned.get("institution_other") or "").strip()
        ):
            self.add_error("institution_other", "Please type your institution.")
        return cleaned


class AttendeeForm(forms.ModelForm):
    class Meta:
        model = Attendee
        fields = [
            "full_name",
            "phone",
            "email",
            "source",
            "institution",
            "institution_other",
        ]
        widgets = {
            "full_name": forms.TextInput(attrs={"placeholder": "Full name"}),
            "phone": forms.TextInput(attrs={"placeholder": "Phone"}),
            "email": forms.EmailInput(attrs={"placeholder": "Email"}),
            "institution_other": forms.TextInput(
                attrs={"placeholder": "Institution (if not listed)"}
            ),
        }