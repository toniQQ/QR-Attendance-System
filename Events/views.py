import csv
import datetime
import re
from urllib.parse import quote

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Q
from django.db.models.functions import Lower
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone

from .forms import AttendeeForm, CheckInForm, EventForm
from .models import Attendee, Event, EventBrand, EventLogo, Institution, SiteProfile
from .utils import checkin_url, dominant_colors, darken, local_base_url, qr_png_response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _profile():
    return SiteProfile.objects.first()


def _brand(event):
    return EventBrand.objects.get_or_create(event=event)[0]


def _normalise_name(name):
    return re.sub(r"\s+", " ", name.strip()).casefold()


def _match_or_create_attendee(event, name, phone="", email=""):
    target = _normalise_name(name)
    existing = (
        event.attendees.annotate(name_lower=Lower("full_name"))
        .filter(name_lower=target)
        .first()
    )
    if existing:
        return existing, False
    att = Attendee.objects.create(
        event=event,
        full_name=name.strip(),
        phone=phone,
        email=email,
        source=Attendee.Source.WALK_IN,
    )
    return att, True


# ---------------------------------------------------------------------------
# Public pages
# ---------------------------------------------------------------------------

def landing(request):
    profile = _profile()
    events = Event.objects.annotate(
        checked=Count("attendees", filter=Q(attendees__checked_in_at__isnull=False)),
        total=Count("attendees"),
    )
    for event in events:
        event.theme = _brand(event)
    return render(
        request,
        "Events/landing.html",
        {"profile": profile, "events": events},
    )


def event_page(request, slug):
    event = get_object_or_404(Event, slug=slug)
    brand = _brand(event)
    logos = event.logos.all()
    recent = event.attendees.filter(checked_in_at__isnull=False)[:12]
    share_link = checkin_url(event)
    subtitle = (brand.welcome_subtitle or "").strip()
    about_paragraphs = [
        para.strip()
        for para in event.description.splitlines()
        if para.strip() and para.strip() != subtitle
    ]
    return render(
        request,
        "Events/event_page.html",
        {
            "event": event,
            "brand": brand,
            "logos": logos,
            "recent": recent,
            "share_link": share_link,
            "about_paragraphs": about_paragraphs,
        },
    )


def event_qrcode(request, slug):
    event = get_object_or_404(Event, slug=slug)
    brand = _brand(event)
    url = checkin_url(event)
    return qr_png_response(url, fill_color=brand.primary_color)


def event_count_json(request, slug):
    event = get_object_or_404(Event, slug=slug)
    return JsonResponse(
        {
            "registered": event.registered_count,
            "checked_in": event.checked_in_count,
            "capacity": event.capacity,
        }
    )


def register(request, slug):
    event = get_object_or_404(Event, slug=slug)
    brand = _brand(event)
    logos = event.logos.all()
    pre_names = list(
        event.attendees.filter(source=Attendee.Source.PRE_REGISTERED)
        .order_by("full_name")
        .values_list("full_name", flat=True)
    )
    closed = event.status == Event.Status.CLOSED

    if closed:
        return render(
            request,
            "Events/register.html",
            {
                "event": event,
                "brand": brand,
                "logos": logos,
                "closed": True,
            },
        )

    form = CheckInForm(
        request.POST or None,
        institution_choices=[
            (inst.pk, inst.name)
            for inst in event.attending_institutions.all()
        ],
    )

    if request.method == "POST" and form.is_valid():
        name = form.cleaned_data["full_name"].strip()
        att, created = _match_or_create_attendee(
            event,
            name,
            form.cleaned_data.get("phone", ""),
            form.cleaned_data.get("email", ""),
        )
        _save_attendee_institution(att, form)
        was_checked_in = att.checked_in_at is not None
        if not was_checked_in:
            att.checked_in_at = timezone.now()
            att.save(update_fields=["checked_in_at"])
        status = (
            "welcome_back" if was_checked_in else ("matched" if not created else "walk_in")
        )
        return HttpResponseRedirect(
            reverse("events:success", kwargs={"slug": event.slug})
            + f"?name={quote(att.full_name)}&status={status}"
        )

    return render(
        request,
        "Events/register.html",
        {
            "event": event,
            "brand": brand,
            "logos": logos,
            "form": form,
            "pre_names": pre_names,
        },
    )


def success(request, slug):
    event = get_object_or_404(Event, slug=slug)
    brand = _brand(event)
    logos = event.logos.all()
    name = request.GET.get("name", "")
    status = request.GET.get("status", "")
    return render(
        request,
        "Events/success.html",
        {
            "event": event,
            "brand": brand,
            "logos": logos,
            "attendee_name": name,
            "status": status,
        },
    )


# ---------------------------------------------------------------------------
# Control centre (staff-only)
# ---------------------------------------------------------------------------

@staff_member_required(login_url="admin:login")
def control_dashboard(request):
    profile = _profile()
    events = Event.objects.annotate(
        checked=Count("attendees", filter=Q(attendees__checked_in_at__isnull=False)),
        total=Count("attendees"),
    )
    totals = {
        "events": Event.objects.count(),
        "registrations": Attendee.objects.count(),
        "check_ins": Attendee.objects.filter(checked_in_at__isnull=False).count(),
    }
    return render(
        request,
        "Events/control/dashboard.html",
        {"profile": profile, "events": events, "totals": totals},
    )


@staff_member_required(login_url="admin:login")
def control_stats(request):
    events = Event.objects.annotate(
        checked=Count("attendees", filter=Q(attendees__checked_in_at__isnull=False)),
        total=Count("attendees"),
        pre=Count(
            "attendees", filter=Q(attendees__source=Attendee.Source.PRE_REGISTERED)
        ),
        walk=Count(
            "attendees", filter=Q(attendees__source=Attendee.Source.WALK_IN)
        ),
    )
    totals = {
        "events": Event.objects.count(),
        "registrations": sum(e.total for e in events),
        "check_ins": sum(e.checked for e in events),
    }
    if totals["registrations"]:
        totals["conversion"] = round(100 * totals["check_ins"] / totals["registrations"])
    else:
        totals["conversion"] = 0
    live_count = Event.objects.filter(status=Event.Status.LIVE).count()
    draft_count = Event.objects.filter(status=Event.Status.DRAFT).count()
    closed_count = Event.objects.filter(status=Event.Status.CLOSED).count()
    pre_total = Attendee.objects.filter(source=Attendee.Source.PRE_REGISTERED).count()
    walk_total = Attendee.objects.filter(source=Attendee.Source.WALK_IN).count()
    return render(
        request,
        "Events/control/stats.html",
        {
            "events": events,
            "totals": totals,
            "live_count": live_count,
            "draft_count": draft_count,
            "closed_count": closed_count,
            "pre_total": pre_total,
            "walk_total": walk_total,
        },
    )


@staff_member_required(login_url="admin:login")
def stats_csv(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = "attachment; filename=stats.csv"
    writer = csv.writer(response)
    writer.writerow(
        ["Event", "Status", "Date", "Registrations", "Checked in", "Conversion %"]
    )
    for ev in Event.objects.all():
        reg = ev.registered_count
        chk = ev.checked_in_count
        conv = round(100 * chk / reg) if reg else 0
        writer.writerow([ev.name, ev.get_status_display(), ev.date or "", reg, chk, conv])
    return response


@staff_member_required(login_url="admin:login")
def event_create(request):
    if request.method == "POST":
        form = EventForm(request.POST, request.FILES)
        if form.is_valid():
            event = form.save()
            brand = _save_brand(event, form)
            _add_new_institution(event, form)
            _save_logos(event, form.cleaned_data.get("logo"), brand)
            messages.success(request, f"Event '{event.name}' created.")
            return HttpResponseRedirect(
                reverse("events:event_detail", kwargs={"pk": event.pk})
            )
    else:
        form = EventForm()
    return render(
        request,
        "Events/control/event_form.html",
        {"form": form, "editing": False},
    )


@staff_member_required(login_url="admin:login")
def event_detail(request, pk):
    event = get_object_or_404(Event, pk=pk)
    brand = _brand(event)
    q = request.GET.get("q", "").strip()
    attendees = event.attendees.all()
    if q:
        q_target = _normalise_name(q)
        attendees = attendees.annotate(name_lower=Lower("full_name")).filter(
            Q(name_lower__contains=q_target)
            | Q(phone__icontains=q)
            | Q(email__icontains=q)
        )

    add_form = AttendeeForm()
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add_attendee":
            add_form = AttendeeForm(request.POST)
            if add_form.is_valid():
                att = add_form.save(commit=False)
                att.event = event
                att.source = Attendee.Source.PRE_REGISTERED
                att.save()
                messages.success(request, f"Added {att.full_name}.")
                return HttpResponseRedirect(
                    reverse("events:event_detail", kwargs={"pk": pk})
                    + f"?q={quote(q)}#attendees"
                )
        elif action == "toggle_checkin":
            att_id = request.POST.get("attendee_id")
            att = get_object_or_404(Attendee, pk=att_id, event=event)
            att.checked_in_at = timezone.now() if att.checked_in_at is None else None
            att.save(update_fields=["checked_in_at"])
        elif action == "delete_attendee":
            att_id = request.POST.get("attendee_id")
            get_object_or_404(Attendee, pk=att_id, event=event).delete()
        elif action == "set_status":
            new_status = request.POST.get("new_status")
            if new_status in Event.Status.values:
                event.status = new_status
                event.save(update_fields=["status"])
                messages.success(request, f"Status set to {new_status}.")
        return HttpResponseRedirect(
            reverse("events:event_detail", kwargs={"pk": pk}) + f"?q={quote(q)}"
        )

    return render(
        request,
        "Events/control/event_detail.html",
        {
            "event": event,
            "brand": brand,
            "attendees": attendees,
            "q": q,
            "add_form": add_form,
        },
    )


@staff_member_required(login_url="admin:login")
def event_stats(request, pk):
    event = get_object_or_404(Event, pk=pk)
    brand = _brand(event)
    now = timezone.localtime(timezone.now())

    # Per-hour histogram (event day or last 24h)
    hourly = []
    if event.date:
        base = timezone.make_aware(
            timezone.datetime.combine(event.date, event.start_time or datetime.time.min)
        )
    else:
        base = now - datetime.timedelta(hours=24)
    for h in range(25):
        t = base + datetime.timedelta(hours=h)
        t_next = t + datetime.timedelta(hours=1)
        count = event.attendees.filter(
            checked_in_at__gte=t, checked_in_at__lt=t_next
        ).count()
        hourly.append({"label": t.strftime("%H:%M"), "count": count})
    max_hourly = max((b["count"] for b in hourly), default=1) or 1

    pre_count = event.attendees.filter(source=Attendee.Source.PRE_REGISTERED).count()
    walk_count = event.attendees.filter(source=Attendee.Source.WALK_IN).count()
    max_source = max(pre_count, walk_count, 1)

    return render(
        request,
        "Events/control/event_stats.html",
        {
            "event": event,
            "brand": brand,
            "hourly": hourly,
            "max_hourly": max_hourly,
            "pre_count": pre_count,
            "walk_count": walk_count,
            "max_source": max_source,
        },
    )


@staff_member_required(login_url="admin:login")
def event_edit(request, pk):
    event = get_object_or_404(Event, pk=pk)
    brand = _brand(event)
    if request.method == "POST":
        form = EventForm(request.POST, request.FILES, instance=event)
        if form.is_valid():
            form.save()
            brand = _save_brand(event, form)
            _add_new_institution(event, form)
            _save_logos(event, form.cleaned_data.get("logo"), brand)
            messages.success(request, "Event updated.")
            return HttpResponseRedirect(
                reverse("events:event_detail", kwargs={"pk": pk})
            )
    else:
        form = EventForm(
            instance=event,
            initial={
                "primary_color": brand.primary_color,
                "accent_color": brand.accent_color,
                "gradient_from": brand.gradient_from,
                "gradient_to": brand.gradient_to,
                "greeting_message": brand.greeting_message,
                "welcome_subtitle": brand.welcome_subtitle,
                "show_event_info": brand.show_event_info,
                "logo_align": brand.logo_align,
                "attending_institutions": list(
                    event.attending_institutions.all()
                ),
            },
        )
    logos = event.logos.all()
    return render(
        request,
        "Events/control/event_form.html",
        {"form": form, "editing": True, "event": event, "logos": logos},
    )


@staff_member_required(login_url="admin:login")
def event_csv(request, pk):
    event = get_object_or_404(Event, pk=pk)
    response = HttpResponse(content_type="text/csv")
    response[
        "Content-Disposition"
    ] = f"attachment; filename={event.slug}-attendees.csv"
    writer = csv.writer(response)
    writer.writerow(
        [
            "Name",
            "Phone",
            "Email",
            "Institution",
            "Source",
            "Registered at",
            "Checked in",
        ]
    )
    for att in event.attendees.all():
        institution = (
            att.institution.name if att.institution_id else att.institution_other
        )
        writer.writerow(
            [
                att.full_name,
                att.phone,
                att.email,
                institution,
                att.get_source_display(),
                att.registered_at.strftime("%Y-%m-%d %H:%M:%S") if att.registered_at else "",
                att.checked_in_at.strftime("%Y-%m-%d %H:%M:%S") if att.checked_in_at else "",
            ]
        )
    return response


@staff_member_required(login_url="admin:login")
def event_set_status(request, pk):
    event = get_object_or_404(Event, pk=pk)
    new_status = request.POST.get("status", request.GET.get("status"))
    next_url = request.META.get(
        "HTTP_REFERER",
        reverse("events:event_detail", kwargs={"pk": pk}),
    )
    if request.method == "POST" and new_status in Event.Status.values:
        event.status = new_status
        event.save(update_fields=["status"])
        messages.success(request, f"Status set to {new_status}.")
    return HttpResponseRedirect(next_url)


@staff_member_required(login_url="admin:login")
def delete_logo(request, pk):
    logo = get_object_or_404(EventLogo, pk=pk)
    event_pk = logo.event_id
    if request.method == "POST":
        logo.image.delete(save=False)
        logo.delete()
        messages.success(request, "Logo deleted.")
    return HttpResponseRedirect(
        reverse("events:event_edit", kwargs={"pk": event_pk})
    )


@staff_member_required(login_url="admin:login")
def toggle_checkin(request, pk):
    att = get_object_or_404(Attendee, pk=pk)
    if request.method == "POST":
        att.checked_in_at = (
            timezone.now() if att.checked_in_at is None else None
        )
        att.save(update_fields=["checked_in_at"])
    return HttpResponseRedirect(
        reverse("events:event_detail", kwargs={"pk": att.event_id})
        + "#attendees"
    )


@staff_member_required(login_url="admin:login")
def delete_attendee(request, pk):
    att = get_object_or_404(Attendee, pk=pk)
    event_pk = att.event_id
    if request.method == "POST":
        att.delete()
        messages.success(request, f"Removed {att.full_name}.")
    return HttpResponseRedirect(
        reverse("events:event_detail", kwargs={"pk": event_pk}) + "#attendees"
    )


# ---------------------------------------------------------------------------
# Brand + logo helpers
# ---------------------------------------------------------------------------

def _save_brand(event, form):
    brand, _ = EventBrand.objects.get_or_create(event=event)
    color_overridden = False
    for field in ["primary_color", "accent_color", "gradient_from", "gradient_to"]:
        value = form.cleaned_data.get(field) or getattr(brand, field)
        if value and value != getattr(brand, field):
            color_overridden = True
        setattr(brand, field, value)
    for field in ["greeting_message", "welcome_subtitle", "show_event_info", "logo_align"]:
        setattr(
            brand,
            field,
            form.cleaned_data.get(field) or getattr(brand, field),
        )
    if color_overridden:
        brand.auto_theme = False
    brand.save()
    return brand


def _add_new_institution(event, form):
    name = (form.cleaned_data.get("institution_new") or "").strip()
    if not name:
        return
    institution, _ = Institution.objects.get_or_create(name=name)
    event.attending_institutions.add(institution)


def _save_logos(event, logo_file, brand):
    if not logo_file:
        return
    colors = []
    try:
        colors = dominant_colors(logo_file)
    except Exception:
        colors = []
    if hasattr(logo_file, "seek"):
        logo_file.seek(0)
    EventLogo.objects.create(
        event=event,
        image=logo_file,
        alt_text=getattr(logo_file, "name", ""),
        sort_order=EventLogo.objects.filter(event=event).count(),
    )
    if brand and brand.auto_theme and colors:
        primary = colors[0]
        accent = colors[1] if len(colors) > 1 else darken(primary, 0.75)
        brand.primary_color = primary
        brand.accent_color = accent
        brand.gradient_from = primary
        brand.gradient_to = darken(accent, 0.45)
        brand.save(
            update_fields=[
                "primary_color",
                "accent_color",
                "gradient_from",
                "gradient_to",
            ]
        )


def _save_attendee_institution(attendee, form):
    institution = form.cleaned_data.get("institution")
    update_fields = set()
    if institution and institution != "__other__":
        attendee.institution_id = institution
        attendee.institution_other = ""
        update_fields.update(["institution", "institution_other"])
    elif institution == "__other__":
        attendee.institution = None
        attendee.institution_other = (
            form.cleaned_data.get("institution_other") or ""
        ).strip()
        update_fields.update(["institution", "institution_other"])
    if update_fields:
        attendee.save(update_fields=update_fields)