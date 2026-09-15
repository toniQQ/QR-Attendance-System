import datetime
import io
from urllib.parse import urlencode

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import AttendanceLog, Attendee, Event, EventBrand, Institution, MeetingMaterial

from .views import _current_session, _record_check_in


def aware_at(hour, minute=0, day=None):
    day = day or timezone.localdate()
    return timezone.make_aware(datetime.datetime.combine(day, datetime.time(hour, minute)))


def make_logo_png():
    import qrcode

    buffer = io.BytesIO()
    qrcode.make("test").save(buffer, format="PNG")
    return SimpleUploadedFile("logo.png", buffer.getvalue(), content_type="image/png")


class EventFlowTests(TestCase):
    def setUp(self):
        self.event = Event.objects.create(
            name="Hackathon 2025",
            slug="hackathon-2025",
            status=Event.Status.LIVE,
        )

    def test_landing_lists_events(self):
        resp = self.client.get(reverse("events:home"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Hackathon 2025")

    def test_event_page_renders_theme_vars(self):
        resp = self.client.get(
            reverse("events:event_page", kwargs={"slug": self.event.slug})
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "--ev-primary")
        self.assertContains(resp, "Hackathon 2025")
        self.assertContains(resp, "Check in")

    def test_qrcode_endpoint_returns_png(self):
        resp = self.client.get(
            reverse("events:event_qrcode", kwargs={"slug": self.event.slug})
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "image/png")
        self.assertTrue(resp.content[:8].startswith(b"\x89PNG"))

    def test_walk_in_check_in(self):
        url = reverse("events:register", kwargs={"slug": self.event.slug})
        resp = self.client.post(url, {"full_name": "Ada Lovelace"})
        self.assertEqual(resp.status_code, 302)
        att = Attendee.objects.get(event=self.event)
        self.assertEqual(att.full_name, "Ada Lovelace")
        self.assertEqual(att.source, Attendee.Source.WALK_IN)
        self.assertIsNotNone(att.checked_in_at)

    def test_re_scan_matches_pre_registered_and_is_idempotent(self):
        Attendee.objects.create(
            event=self.event,
            full_name="Alan Turing",
            source=Attendee.Source.PRE_REGISTERED,
        )
        url = reverse("events:register", kwargs={"slug": self.event.slug})
        self.client.post(url, {"full_name": " alan turing "})
        attendees = Attendee.objects.filter(event=self.event)
        self.assertEqual(attendees.count(), 1)
        self.assertEqual(attendees.first().source, Attendee.Source.PRE_REGISTERED)
        self.assertIsNotNone(attendees.first().checked_in_at)
        # second scan: still one attendee, still checked in
        self.client.post(url, {"full_name": "Alan Turing"})
        self.assertEqual(Attendee.objects.filter(event=self.event).count(), 1)

    def test_closed_event_rejects_check_in(self):
        self.event.status = Event.Status.CLOSED
        self.event.save()
        url = reverse("events:register", kwargs={"slug": self.event.slug})
        resp = self.client.post(url, {"full_name": "Grace Hopper"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "closed")
        self.assertEqual(Attendee.objects.count(), 0)

    def test_success_page_shows_name(self):
        url = reverse("events:success", kwargs={"slug": self.event.slug})
        resp = self.client.get(url, {"name": "Grace Hopper"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Grace Hopper")

    def test_logos_render_on_event_page(self):
        logo = self.event.logos.create(
            image=make_logo_png(), alt_text="Sponsor logo"
        )
        resp = self.client.get(
            reverse("events:event_page", kwargs={"slug": self.event.slug})
        )
        self.assertContains(resp, "Sponsor logo")
        self.assertContains(resp, logo.image.url)

    def test_register_lists_attending_institutions(self):
        inst = Institution.objects.create(name="Addis Ababa University")
        self.event.attending_institutions.add(inst)
        resp = self.client.get(
            reverse("events:register", kwargs={"slug": self.event.slug})
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Addis Ababa University")
        self.assertContains(resp, "Other")

    def test_register_saves_picked_institution(self):
        inst = Institution.objects.create(name="Addis Ababa University")
        self.event.attending_institutions.add(inst)
        resp = self.client.post(
            reverse("events:register", kwargs={"slug": self.event.slug}),
            {"full_name": "Ada Lovelace", "institution": str(inst.pk)},
        )
        self.assertEqual(resp.status_code, 302)
        att = Attendee.objects.get(event=self.event)
        self.assertEqual(att.institution, inst)
        self.assertEqual(att.institution_other, "")

    def test_register_saves_other_institution(self):
        resp = self.client.post(
            reverse("events:register", kwargs={"slug": self.event.slug}),
            {"full_name": "Ada Lovelace", "institution": "__other__", "institution_other": "My Own School"},
        )
        self.assertEqual(resp.status_code, 302)
        att = Attendee.objects.get(event=self.event)
        self.assertIsNone(att.institution)
        self.assertEqual(att.institution_other, "My Own School")

    def test_register_other_requires_text(self):
        resp = self.client.post(
            reverse("events:register", kwargs={"slug": self.event.slug}),
            {"full_name": "Ada Lovelace", "institution": "__other__", "institution_other": ""},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Please type your institution.")
        self.assertEqual(Attendee.objects.count(), 0)


class ControlAccessTests(TestCase):
    def setUp(self):
        self.event = Event.objects.create(
            name="Workshop", slug="workshop", status=Event.Status.LIVE
        )
        self.staff = User.objects.create_user(
            username="staff", password="pw", is_staff=True
        )

    def test_dashboard_requires_login(self):
        resp = self.client.get(reverse("events:control_dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("admin:login"), resp.url)

    def test_staff_can_open_dashboard(self):
        self.client.login(username="staff", password="pw")
        resp = self.client.get(reverse("events:control_dashboard"))
        self.assertEqual(resp.status_code, 200)

    def test_event_creation_via_control(self):
        self.client.login(username="staff", password="pw")
        resp = self.client.post(
            reverse("events:event_create"),
            {
                "name": "AI Summit",
                "slug": "ai-summit",
                "status": Event.Status.LIVE,
                "sessions": Event.Sessions.SINGLE,
                "greeting_message": "Welcome to the summit!",
            },
        )
        self.assertEqual(resp.status_code, 302)
        ev = Event.objects.get(slug="ai-summit")
        self.assertEqual(ev.brand.greeting_message, "Welcome to the summit!")

    def test_single_logo_upload_plus_auto_theme(self):
        self.client.login(username="staff", password="pw")
        resp = self.client.post(
            reverse("events:event_create"),
            {
                "name": "Launch Night",
                "slug": "launch-night",
                "status": Event.Status.LIVE,
                "sessions": Event.Sessions.SINGLE,
                "logo": make_logo_png(),
            },
        )
        self.assertEqual(resp.status_code, 302)
        ev = Event.objects.get(slug="launch-night")
        self.assertEqual(ev.logos.count(), 1)
        self.assertEqual(ev.brand.logo_align, EventBrand.LogoAlign.CENTER)

    def test_logo_align_saved_and_rendered(self):
        self.client.login(username="staff", password="pw")
        resp = self.client.post(
            reverse("events:event_create"),
            {
                "name": "Launch Night",
                "slug": "launch-night",
                "status": Event.Status.LIVE,
                "sessions": Event.Sessions.SINGLE,
                "logo_align": EventBrand.LogoAlign.RIGHT,
                "attending_institutions": [],
                "logo": make_logo_png(),
            },
        )
        self.assertEqual(resp.status_code, 302)
        ev = Event.objects.get(slug="launch-night")
        self.assertEqual(ev.brand.logo_align, EventBrand.LogoAlign.RIGHT)
        page = self.client.get(
            reverse("events:event_page", kwargs={"slug": ev.slug})
        )
        self.assertContains(page, "logo-row--right")

    def test_event_creation_with_institution(self):
        self.client.login(username="staff", password="pw")
        resp = self.client.post(
            reverse("events:event_create"),
            {
                "name": "AI Summit 2",
                "slug": "ai-summit-2",
                "status": Event.Status.LIVE,
                "sessions": Event.Sessions.SINGLE,
                "institution_new": "Dire Dawa University",
                "attending_institutions": [],
            },
        )
        self.assertEqual(resp.status_code, 302)
        ev = Event.objects.get(slug="ai-summit-2")
        self.assertEqual(
            list(
                ev.attending_institutions.values_list("name", flat=True)
            ),
            ["Dire Dawa University"],
        )

    def test_stats_page_shows_counts(self):
        self.client.login(username="staff", password="pw")
        Attendee.objects.create(
            event=self.event, full_name="A", checked_in_at=timezone.now()
        )
        resp = self.client.get(reverse("events:control_stats"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "1")
        self.assertContains(resp, "Workshop")


class SessionAndMaterialTests(TestCase):
    def setUp(self):
        self.single = Event.objects.create(
            name="Hackathon", slug="hackathon", status=Event.Status.LIVE
        )
        self.split = Event.objects.create(
            name="Workshop Split",
            slug="workshop-split",
            status=Event.Status.LIVE,
            sessions=Event.Sessions.SPLIT,
            morning_label="Morning",
            afternoon_label="Afternoon",
        )
        self.staff = User.objects.create_user(
            username="admin", password="pw", is_staff=True
        )

    def test_register_auto_records_session_for_split(self):
        url = reverse("events:register", kwargs={"slug": self.split.slug})
        resp = self.client.post(url, {"full_name": "Ada"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("session=", resp.url)
        att = Attendee.objects.get(event=self.split)
        logs = list(att.attendance_logs.all())
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].day, timezone.localdate())
        self.assertEqual(logs[0].session, _current_session(self.split))
        self.assertIn(f"session={logs[0].session}", resp.url)
        self.assertIsNotNone(att.checked_in_at)

    def test_duplicate_same_day_same_session_welcome_back(self):
        url = reverse("events:register", kwargs={"slug": self.split.slug})
        self.client.post(url, {"full_name": "Ada"})
        att = Attendee.objects.get(event=self.split)
        original_time = att.attendance_logs.first().checked_in_at
        resp = self.client.post(url, {"full_name": "Ada"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("status=welcome_back", resp.url)
        att.refresh_from_db()
        self.assertEqual(att.attendance_logs.count(), 1)
        self.assertEqual(
            att.attendance_logs.first().checked_in_at, original_time
        )

    def test_single_event_repeat_scan_returns_welcome_back(self):
        url = reverse("events:register", kwargs={"slug": self.single.slug})
        self.client.post(url, {"full_name": "Bob"})
        resp = self.client.post(url, {"full_name": "Bob"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("status=welcome_back", resp.url)
        self.assertEqual(Attendee.objects.filter(event=self.single).count(), 1)

    def test_register_page_shows_today_no_session_choice(self):
        url = reverse("events:register", kwargs={"slug": self.split.slug})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Checking in for")
        self.assertNotContains(resp, "Which session")
        self.assertNotContains(resp, "session-options")

    def test_current_session_boundaries(self):
        self.assertEqual(
            _current_session(self.split, aware_at(11, 59)),
            AttendanceLog.Session.MORNING,
        )
        self.assertEqual(
            _current_session(self.split, aware_at(12, 0)),
            AttendanceLog.Session.AFTERNOON,
        )
        self.assertEqual(
            _current_session(self.split, aware_at(23, 59)),
            AttendanceLog.Session.AFTERNOON,
        )
        self.assertEqual(
            _current_session(self.single, aware_at(12, 0)),
            AttendanceLog.Session.SINGLE,
        )

    def test_single_event_logs_use_single_session(self):
        att = Attendee.objects.create(
            event=self.single, full_name="Grace",
        )
        already, session = _record_check_in(att, now=aware_at(10))
        self.assertFalse(already)
        self.assertEqual(session, AttendanceLog.Session.SINGLE)
        log = att.attendance_logs.get()
        self.assertEqual(log.session, AttendanceLog.Session.SINGLE)
        self.assertEqual(log.day, timezone.localdate())
        already, _ = _record_check_in(att, now=aware_at(15))
        self.assertTrue(already)
        self.assertEqual(att.attendance_logs.count(), 1)

    def test_morning_then_afternoon_same_day(self):
        att = Attendee.objects.create(event=self.split, full_name="Hedy")
        already, session = _record_check_in(att, now=aware_at(9))
        self.assertFalse(already)
        self.assertEqual(session, AttendanceLog.Session.MORNING)
        already, session = _record_check_in(att, now=aware_at(14))
        self.assertFalse(already)
        self.assertEqual(session, AttendanceLog.Session.AFTERNOON)
        self.assertEqual(att.attendance_logs.count(), 2)
        self.assertEqual(att.checked_in_at, aware_at(9))

    def test_next_day_same_session_is_new_checkin(self):
        att = Attendee.objects.create(event=self.split, full_name="Grace")
        day1 = timezone.localdate()
        already, _ = _record_check_in(att, now=aware_at(9))
        self.assertFalse(already)
        day2 = day1 + datetime.timedelta(days=1)
        already, session = _record_check_in(att, now=aware_at(9, day=day2))
        self.assertFalse(already)
        self.assertEqual(session, AttendanceLog.Session.MORNING)
        self.assertEqual(att.attendance_logs.count(), 2)
        self.assertEqual(set(att.attendance_logs.values_list("day", flat=True)), {day1, day2})

    def test_event_create_with_end_date(self):
        self.client.login(username="admin", password="pw")
        start = timezone.localdate()
        end = start + datetime.timedelta(days=2)
        resp = self.client.post(
            reverse("events:event_create"),
            {
                "name": "Weekend Camp",
                "slug": "weekend-camp",
                "status": Event.Status.LIVE,
                "sessions": Event.Sessions.SPLIT,
                "date": start.isoformat(),
                "end_date": end.isoformat(),
            },
        )
        self.assertEqual(resp.status_code, 302)
        ev = Event.objects.get(slug="weekend-camp")
        self.assertEqual(ev.date, start)
        self.assertEqual(ev.end_date, end)

    def test_event_create_rejects_end_before_start(self):
        self.client.login(username="admin", password="pw")
        start = timezone.localdate()
        resp = self.client.post(
            reverse("events:event_create"),
            {
                "name": "Bad Range",
                "slug": "bad-range",
                "status": Event.Status.LIVE,
                "date": start.isoformat(),
                "end_date": (start - datetime.timedelta(days=1)).isoformat(),
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "End date must be on or after")

    def test_event_stats_day_selector(self):
        self.client.login(username="admin", password="pw")
        start = timezone.localdate()
        self.split.date = start
        self.split.end_date = start + datetime.timedelta(days=1)
        self.split.save()
        att = Attendee.objects.create(event=self.split, full_name="Ada")
        _record_check_in(att, now=aware_at(9))
        resp = self.client.get(
            reverse("events:event_stats", kwargs={"pk": self.split.pk})
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Sessions")
        self.assertContains(resp, "Morning")
        today_label = start.strftime("%B %d")
        self.assertContains(resp, today_label)

    def test_materials_page_shows_materials(self):
        self.split.materials.create(
            kind=MeetingMaterial.Kind.WIFI,
            title="Wi-Fi Access",
            body="SSID: NCC-Conf  Password: NCC2024",
        )
        resp = self.client.get(
            reverse("events:event_materials", kwargs={"slug": self.split.slug})
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Wi-Fi Access")
        self.assertContains(resp, "NCC-Conf")

    def test_material_added_via_event_form(self):
        self.client.login(username="admin", password="pw")
        resp = self.client.post(
            reverse("events:event_create"),
            {
                "name": "Mat Event",
                "slug": "mat-event",
                "status": Event.Status.LIVE,
                "sessions": Event.Sessions.SPLIT,
                "morning_label": "AM",
                "afternoon_label": "PM",
                "material_kind": MeetingMaterial.Kind.DOCUMENT,
                "material_title": "Agenda",
                "material_body": "9:00 welcome, 9:30 keynote",
            },
        )
        self.assertEqual(resp.status_code, 302)
        mat = MeetingMaterial.objects.get(event__slug="mat-event")
        self.assertEqual(mat.kind, MeetingMaterial.Kind.DOCUMENT)
        self.assertEqual(mat.title, "Agenda")
        self.assertEqual(mat.body, "9:00 welcome, 9:30 keynote")
        event = Event.objects.get(slug="mat-event")
        self.assertEqual(event.sessions, Event.Sessions.SPLIT)

    def test_attendees_csv_has_sessions_column(self):
        att = Attendee.objects.create(
            event=self.split,
            full_name="Ada",
            source=Attendee.Source.WALK_IN,
            checked_in_at=timezone.now(),
        )
        AttendanceLog.objects.create(
            attendee=att,
            day=timezone.localdate(),
            session=AttendanceLog.Session.MORNING,
            checked_in_at=timezone.now(),
        )
        self.client.login(username="admin", password="pw")
        resp = self.client.get(
            reverse("events:event_csv", kwargs={"pk": self.split.pk})
        )
        content = resp.content.decode()
        self.assertIn("Sessions attended", content)
        self.assertNotIn("Morning checked in", content)