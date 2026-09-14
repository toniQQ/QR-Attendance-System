from django.contrib import admin

from .models import Attendee, Event, EventBrand, EventLogo, Institution, SiteProfile


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


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "status", "date", "registered_count", "checked_in_count")
    list_filter = ("status",)
    search_fields = ("name", "slug", "venue")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [EventBrandInline, EventLogoInline, AttendeeInline]


@admin.register(Attendee)
class AttendeeAdmin(admin.ModelAdmin):
    list_display = ("full_name", "event", "source", "institution", "checked_in_at", "registered_at")
    list_filter = ("event", "source", "checked_in_at")
    search_fields = ("full_name", "phone", "email", "institution__name", "institution_other")


@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):
    list_display = ("name", "event_count")

    def event_count(self, obj):
        return obj.events.count()

    event_count.short_description = "Attending events"


@admin.register(SiteProfile)
class SiteProfileAdmin(admin.ModelAdmin):
    pass