from django.urls import path

from . import views

app_name = "events"

urlpatterns = [
    # public
    path("", views.landing, name="home"),
    path("events/<slug:slug>/", views.event_page, name="event_page"),
    path("events/<slug:slug>/qr.png", views.event_qrcode, name="event_qrcode"),
    path("events/<slug:slug>/count.json", views.event_count_json, name="event_count"),
    path("events/<slug:slug>/register/", views.register, name="register"),
    path("events/<slug:slug>/success/", views.success, name="success"),
    path("events/<slug:slug>/materials/", views.event_materials, name="event_materials"),
    # control centre
    path("control/", views.control_dashboard, name="control_dashboard"),
    path("control/stats/", views.control_stats, name="control_stats"),
    path("control/stats.csv", views.stats_csv, name="stats_csv"),
    path("control/events/new/", views.event_create, name="event_create"),
    path("control/events/<int:pk>/", views.event_detail, name="event_detail"),
    path("control/events/<int:pk>/stats/", views.event_stats, name="event_stats"),
    path("control/events/<int:pk>/edit/", views.event_edit, name="event_edit"),
    path("control/events/<int:pk>/attendees.csv", views.event_csv, name="event_csv"),
    path("control/events/<int:pk>/status/", views.event_set_status, name="event_set_status"),
    path("control/logo/<int:pk>/delete/", views.delete_logo, name="delete_logo"),
    path("control/material/<int:pk>/delete/", views.delete_material, name="delete_material"),
    path("control/attendee/<int:pk>/toggle/", views.toggle_checkin, name="toggle_checkin"),
    path("control/attendee/<int:pk>/delete/", views.delete_attendee, name="delete_attendee"),
]