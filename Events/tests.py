import io
from urllib.parse import urlencode

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Attendee, Event, EventBrand, Institution


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