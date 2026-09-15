from django.contrib import admin

from .models import (
    AttendanceLog,
    Attendee,
    Event,
    EventBrand,
    EventLogo,
    Institution,
    MeetingMaterial,
    SiteProfile,
)


class EventBrandInline(admin.StackedInline):
    model = EventBrand
    extra = 0


class EventLogoInline(admin.TabularInline):
    model = EventLogo
    extra = 0


class AttendeeInline(admin.TabularInline):
    model = Attendee
    extra = 0
    readonly_fields = ("registered_at", "checked_in_at")


class AttendanceLogInline(admin.TabularInline):
    model = AttendanceLog
    extra = 0
    readonly_fields = ("day", "session", "checked_in_at")


class MeetingMaterialInline(admin.TabularInline):
    model = MeetingMaterial
    extra = 0


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "status", "date", "registered_count", "checked_in_count")
    list_filter = ("status",)
    search_fields = ("name", "slug", "venue")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [EventBrandInline, MeetingMaterialInline, EventLogoInline, AttendeeInline]


@admin.register(MeetingMaterial)
class MeetingMaterialAdmin(admin.ModelAdmin):
    list_display = ("title", "event", "kind", "sort_order")
    list_filter = ("event", "kind")
    search_fields = ("title", "event__name")


@admin.register(Attendee)
class AttendeeAdmin(admin.ModelAdmin):
    list_display = ("full_name", "event", "source", "institution", "checked_in_at", "registered_at")
    list_filter = ("event", "source", "checked_in_at")
    search_fields = ("full_name", "phone", "email", "institution__name", "institution_other")
    inlines = [AttendanceLogInline]


@admin.register(AttendanceLog)
class AttendanceLogAdmin(admin.ModelAdmin):
    list_display = ("attendee", "day", "session", "checked_in_at")
    list_filter = ("session", "day", "attendee__event")
    search_fields = ("attendee__full_name", "attendee__event__name")


@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):
    list_display = ("name", "event_count")

    def event_count(self, obj):
        return obj.events.count()

    event_count.short_description = "Attending events"


@admin.register(SiteProfile)
class SiteProfileAdmin(admin.ModelAdmin):
    pass