from django.db import models
from django.utils import timezone


class SiteProfile(models.Model):
    org_name = models.CharField(max_length=200)
    org_logo = models.ImageField(upload_to="site/", blank=True)
    tagline = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = "Site profile"
        verbose_name_plural = "Site profile"

    def __str__(self):
        return self.org_name or "Site profile"

    def clean(self):
        from django.core.exceptions import ValidationError

        if not self.pk and SiteProfile.objects.exists():
            raise ValidationError("Only one site profile is allowed.")


class Institution(models.Model):
    name = models.CharField(max_length=120, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Event(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        LIVE = "live", "Live"
        CLOSED = "closed", "Closed"

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=100, unique=True)
    attending_institutions = models.ManyToManyField(
        Institution, related_name="events", blank=True
    )
    description = models.TextField(blank=True)
    date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    venue = models.CharField(max_length=200, blank=True)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    class Sessions(models.TextChoices):
        SINGLE = "single", "Single session (all-day)"
        SPLIT = "split", "Morning & afternoon"

    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.DRAFT
    )
    sessions = models.CharField(
        max_length=10,
        choices=Sessions.choices,
        default=Sessions.SINGLE,
        help_text="Split the day into separate morning and afternoon check-ins.",
    )
    morning_label = models.CharField(
        max_length=40, default="Morning", blank=True
    )
    afternoon_label = models.CharField(
        max_length=40, default="Afternoon", blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    @property
    def registered_count(self):
        return self.attendees.count()

    @property
    def checked_in_count(self):
        return self.attendees.filter(checked_in_at__isnull=False).count()

    @property
    def checked_in_today_count(self):
        return (
            self.attendees.filter(attendance_logs__day=timezone.localdate())
            .values("pk")
            .distinct()
            .count()
        )

    @property
    def conversion_percent(self):
        total = self.registered_count
        if not total:
            return 0
        return round(100 * self.checked_in_count / total)


class EventBrand(models.Model):
    class LogoAlign(models.TextChoices):
        LEFT = "left", "Left"
        CENTER = "center", "Center"
        RIGHT = "right", "Right"

    event = models.OneToOneField(Event, on_delete=models.CASCADE, related_name="brand")
    primary_color = models.CharField(max_length=7, default="#4f46e5")
    accent_color = models.CharField(max_length=7, default="#14b8a6")
    gradient_from = models.CharField(max_length=7, default="#4f46e5")
    gradient_to = models.CharField(max_length=7, default="#0f172a")
    greeting_message = models.CharField(max_length=300, blank=True)
    welcome_subtitle = models.CharField(max_length=300, blank=True)
    show_event_info = models.BooleanField(default=True)
    logo_align = models.CharField(
        max_length=10,
        choices=LogoAlign.choices,
        default=LogoAlign.CENTER,
        help_text="Alignment of the logo row on the event and check-in pages.",
    )
    auto_theme = models.BooleanField(
        default=True,
        help_text="When on, adding a logo re-derives the theme colors from the logo.",
    )

    def __str__(self):
        return f"Branding for {self.event.name}"


class EventLogo(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="logos")
    image = models.ImageField(upload_to="logos/")
    alt_text = models.CharField(max_length=200, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.alt_text or f"Logo {self.id} for {self.event.name}"


class Attendee(models.Model):
    class Source(models.TextChoices):
        PRE_REGISTERED = "pre_registered", "Pre-registered"
        WALK_IN = "walk_in", "Walk-in"

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="attendees")
    full_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    institution = models.ForeignKey(
        Institution,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attendees",
    )
    institution_other = models.CharField(max_length=120, blank=True)
    source = models.CharField(
        max_length=15, choices=Source.choices, default=Source.WALK_IN
    )
    registered_at = models.DateTimeField(auto_now_add=True)
    checked_in_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-checked_in_at", "full_name"]

    def __str__(self):
        return f"{self.full_name} @ {self.event.name}"


class AttendanceLog(models.Model):
    class Session(models.TextChoices):
        SINGLE = "single", "Single"
        MORNING = "morning", "Morning"
        AFTERNOON = "afternoon", "Afternoon"

    attendee = models.ForeignKey(
        Attendee, on_delete=models.CASCADE, related_name="attendance_logs"
    )
    day = models.DateField()
    session = models.CharField(max_length=10, choices=Session.choices)
    checked_in_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [("attendee", "day", "session")]
        ordering = ["day", "session"]

    def __str__(self):
        return f"{self.attendee.full_name} {self.day} {self.get_session_display()}"


class MeetingMaterial(models.Model):
    class Kind(models.TextChoices):
        DOCUMENT = "document", "Document"
        INSTRUCTIONS = "instructions", "Instructions"
        WIFI = "wifi", "Wi-Fi"
        ROOMS = "rooms", "Rooms"
        ITINERARY = "itinerary", "Itinerary"
        PROGRAMME = "programme", "Programme"

    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="materials"
    )
    kind = models.CharField(
        max_length=15, choices=Kind.choices, default=Kind.DOCUMENT
    )
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    file = models.FileField(upload_to="materials/", blank=True)
    link = models.URLField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.title}"