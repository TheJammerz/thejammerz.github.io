#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Régénère la rubrique « Nos prochains lives » de index.html à partir de
l'agenda Google public de The Jammerz (thejammerz64@gmail.com).

Source de vérité = le calendrier. Le script ne fait QUE recopier ce qui s'y
trouve (zéro invention). Il remplace le contenu entre les marqueurs
<!-- AGENDA:AUTO:START ... --> et <!-- AGENDA:AUTO:END --> dans index.html.

Lancé 1x/jour par GitHub Actions (.github/workflows/agenda.yml).
"""
from __future__ import annotations

import html
import re
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from icalendar import Calendar

ICS_URL = (
    "https://calendar.google.com/calendar/ical/"
    "thejammerz64%40gmail.com/public/basic.ics"
)
PARIS = ZoneInfo("Europe/Paris")
MAX_EVENTS = 12
HORIZON_DAYS = 400

START_MARK = "<!-- AGENDA:AUTO:START"
END_MARK = "<!-- AGENDA:AUTO:END -->"

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"

JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
MOIS = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin",
        "Juil", "Août", "Sep", "Oct", "Nov", "Déc"]


# --------------------------------------------------------------------------- #
# Filtre « vrai live » — l'agenda sert AUSSI à l'organisation interne du groupe
# (installations, balances, répètes, réunions...). Seuls les VRAIS concerts /
# lives PUBLICS vont sur le site. On EXCLUT la logistique/prépa (même quand le
# mot « concert » apparaît, ex. « Installation Concert ») et tout ce qui n'est
# pas explicitement un gig public. Zéro invention : on ne publie que ce qui est
# écrit noir sur blanc dans la source. Aligné sur le poller CM
# `jammerz_calendar_poll.py` (même calendrier, même philosophie).
# --------------------------------------------------------------------------- #

# Un event est un GIG public si son titre contient un de ces mots.
GIG_RX = re.compile(
    r"(concert|\blives?\b|\bgig\b|jam[\s-]*session|\bjam\b|showcase|festival|"
    r"f[eê]te\s+de\s+la\s+musique|sur\s+sc[eè]ne|\bsc[eè]ne\b|plateau|"
    r"tremplin|ap[eé]ro[\s-]*concert|guinguette|release\s+party|open\s+mic)",
    re.IGNORECASE)

# Logistique / prépa : JAMAIS sur le site. Cette liste PRIME sur GIG_RX
# (« Installation Concert » contient « concert » mais reste de la prépa).
LOGISTICS_RX = re.compile(
    r"(installation|balance|soundcheck|sound\s?check|r[ée]p[ée]t|montage|"
    r"d[ée]montage|d[ée]ballage|load\s?in|filage|raccord|pr[ée]pa|"
    r"mise\s+en\s+place|r[ée]union|d[ée]brief)",
    re.IGNORECASE)

# Live PRIVÉ (mot ÉCRIT dans la source) : pas de lieu public à montrer,
# donc pas sur le site public. « privé » ne se DÉDUIT jamais (leçon Anaïak 04/07).
PRIVATE_RX = re.compile(
    r"(\bpriv[ée]e?s?\b|sur\s+invitation|huis\s+clos|ferm[ée]s?\s+au\s+public|"
    r"soir[ée]e?\s+priv|invit[ée]s?\s+seulement|\binterne\b)",
    re.IGNORECASE)


def is_public_gig(summary: str, category: str, status: str) -> tuple[bool, str]:
    """True seulement pour un vrai live/concert PUBLIC. Retourne (garde, raison)."""
    if (status or "").upper() == "CANCELLED":
        return False, "annulé"
    text = f"{summary}\n{category}"
    if LOGISTICS_RX.search(text):          # prime : prépa/logistique
        return False, "logistique/prépa (pas un gig public)"
    if PRIVATE_RX.search(text):            # live privé -> pas sur le site public
        return False, "live privé (pas de lieu public)"
    if GIG_RX.search(text):
        return True, "gig public"
    return False, "pas un gig (organisation interne)"


# --------------------------------------------------------------------------- #
# Récupération + parsing du calendrier
# --------------------------------------------------------------------------- #
def fetch_ics() -> bytes:
    req = urllib.request.Request(
        ICS_URL, headers={"User-Agent": "Mozilla/5.0 (jammerz-agenda-bot)"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def occurrences(cal: Calendar, start: datetime, end: datetime) -> list:
    """Liste des occurrences entre start et end, récurrences comprises."""
    try:
        import recurring_ical_events  # type: ignore
        return list(recurring_ical_events.of(cal).between(start, end))
    except Exception as exc:  # pas de lib récurrence -> repli simple
        print(f"[agenda] recurring-ical-events indisponible ({exc}), "
              f"repli sans récurrence", file=sys.stderr)
        return [c for c in cal.walk("VEVENT")]


def as_aware(value) -> datetime:
    """Normalise un DTSTART/DTEND (date ou datetime) en datetime aware UTC."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    # all-day (date) -> minuit Paris
    return datetime(value.year, value.month, value.day, tzinfo=PARIS).astimezone(
        timezone.utc
    )


def collect_events() -> list[dict]:
    cal = Calendar.from_ical(fetch_ics())
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=1)
    window_end = now + timedelta(days=HORIZON_DAYS)

    events: list[dict] = []
    seen: set[tuple] = set()
    for comp in occurrences(cal, window_start, window_end):
        if comp.name != "VEVENT":
            continue
        dtstart = comp.get("DTSTART")
        if dtstart is None:
            continue
        raw_start = dtstart.dt
        all_day = not isinstance(raw_start, datetime)
        start = as_aware(raw_start)

        dtend = comp.get("DTEND")
        end = as_aware(dtend.dt) if dtend is not None else None

        # On garde les évènements pas encore terminés.
        ref_end = end or (start + timedelta(hours=2))
        if ref_end < now:
            continue

        summary = str(comp.get("SUMMARY", "")).strip()
        location = str(comp.get("LOCATION", "")).strip()
        description = str(comp.get("DESCRIPTION", "")).strip()
        status = str(comp.get("STATUS", "")).strip()
        cats = comp.get("CATEGORIES")
        category = ""
        if cats is not None:
            try:
                category = str(cats.cats[0]) if hasattr(cats, "cats") else str(cats)
            except Exception:
                category = ""

        # Filtre : seuls les vrais lives publics (l'agenda contient aussi
        # la logistique et l'organisation interne du groupe).
        keep, why = is_public_gig(summary, category, status)
        if not keep:
            print(f"[agenda] ignoré ({why}) : "
                  f"{start.astimezone(PARIS):%Y-%m-%d %H:%M} | {summary}",
                  file=sys.stderr)
            continue

        key = (summary, start.isoformat())
        if key in seen:
            continue
        seen.add(key)

        events.append({
            "start": start,
            "end": end,
            "all_day": all_day,
            "summary": summary,
            "location": location,
            "description": description,
            "category": category.strip(),
        })

    events.sort(key=lambda e: e["start"])
    return events[:MAX_EVENTS]


# --------------------------------------------------------------------------- #
# Rendu HTML d'une carte
# --------------------------------------------------------------------------- #
def fmt_time(dt_utc: datetime) -> str:
    loc = dt_utc.astimezone(PARIS)
    return f"{loc.hour}h{loc.minute:02d}"


def gcal_dates(ev: dict) -> str:
    if ev["all_day"]:
        d = ev["start"].astimezone(PARIS).date()
        d2 = (ev["end"].astimezone(PARIS).date() if ev["end"] else d + timedelta(days=1))
        return f"{d:%Y%m%d}/{d2:%Y%m%d}"
    s = ev["start"].strftime("%Y%m%dT%H%M%SZ")
    e = (ev["end"] or ev["start"] + timedelta(hours=2)).strftime("%Y%m%dT%H%M%SZ")
    return f"{s}/{e}"


def attr(url: str) -> str:
    """URL prête pour un attribut href HTML (& -> &amp;)."""
    return url.replace("&", "&amp;")


def render_card(ev: dict) -> str:
    paris_start = ev["start"].astimezone(PARIS)
    day = f"{paris_start.day:02d}"
    mon = MOIS[paris_start.month - 1]
    year = paris_start.year
    weekday = JOURS[paris_start.weekday()]

    if ev["all_day"]:
        timeline = f"{weekday} · Toute la journée"
    elif ev["end"]:
        timeline = f"{weekday} · {fmt_time(ev['start'])} – {fmt_time(ev['end'])}"
    else:
        timeline = f"{weekday} · {fmt_time(ev['start'])}"

    title = html.escape(ev["summary"] or "Date à venir")

    badge_html = ""
    if ev["category"]:
        badge_html = f'\n            <span class="gig-badge">{html.escape(ev["category"])}</span>'

    # Lieu : 1er segment = lieu, le reste = adresse
    loc_line = ""
    addr_line = ""
    if ev["location"]:
        parts = [p.strip() for p in ev["location"].split(",") if p.strip()]
        venue = parts[0] if parts else ev["location"]
        loc_line = (
            '\n              <li><span class="gig-ico" aria-hidden="true">📍</span> '
            f'{html.escape(venue)}</li>'
        )
        if len(parts) > 1:
            addr_line = f'\n            <p class="gig-addr">{html.escape(", ".join(parts[1:]))}</p>'

    # Liens (construits à partir des vraies données de l'évènement)
    gcal = (
        "https://calendar.google.com/calendar/render?action=TEMPLATE"
        f"&text={urllib.parse.quote(ev['summary'])}"
        f"&dates={gcal_dates(ev)}"
    )
    if ev["location"]:
        gcal += f"&location={urllib.parse.quote(ev['location'])}"
    if ev["description"]:
        gcal += f"&details={urllib.parse.quote(ev['description'])}"

    actions = (
        f'\n            <a class="gig-btn gig-btn-primary" href="{attr(gcal)}" '
        'target="_blank" rel="noopener">+ Agenda</a>'
    )
    if ev["location"]:
        maps = ("https://www.google.com/maps/search/?api=1&query="
                + urllib.parse.quote(ev["location"]))
        actions += (
            f'\n            <a class="gig-btn gig-btn-ghost" href="{attr(maps)}" '
            'target="_blank" rel="noopener">Itinéraire</a>'
        )

    return (
        '        <article class="gig-card" data-reveal>\n'
        '          <div class="gig-date">\n'
        f'            <span class="gig-day">{day}</span>\n'
        f'            <span class="gig-month">{mon}</span>\n'
        f'            <span class="gig-year">{year}</span>\n'
        '          </div>\n'
        '          <div class="gig-body">'
        f'{badge_html}\n'
        f'            <h3 class="gig-title">{title}</h3>\n'
        '            <ul class="gig-meta">\n'
        '              <li><span class="gig-ico" aria-hidden="true">🕒</span> '
        f'{timeline}</li>'
        f'{loc_line}\n'
        '            </ul>'
        f'{addr_line}\n'
        '          </div>\n'
        '          <div class="gig-actions">'
        f'{actions}\n'
        '          </div>\n'
        '        </article>'
    )


def render_block(events: list[dict]) -> str:
    if not events:
        return (
            '        <p class="gigs-note" data-reveal>Aucune date programmée pour '
            'le moment — revenez bientôt ou <a href="#contact" data-link>réservez '
            'le groupe →</a></p>'
        )
    return "\n".join(render_card(ev) for ev in events)


# --------------------------------------------------------------------------- #
# Injection dans index.html
# --------------------------------------------------------------------------- #
def splice(html_text: str, block: str) -> str:
    s = html_text.find(START_MARK)
    e = html_text.find(END_MARK)
    if s == -1 or e == -1:
        print("[agenda] ERREUR : marqueurs AGENDA:AUTO introuvables dans index.html",
              file=sys.stderr)
        sys.exit(1)
    head_end = html_text.find("-->", s) + len("-->")
    head = html_text[:head_end]
    tail = html_text[e:]
    return f"{head}\n{block}\n        {tail}"


def main() -> int:
    events = collect_events()
    print(f"[agenda] {len(events)} évènement(s) à venir récupéré(s).")
    for ev in events:
        print(f"   - {ev['start'].astimezone(PARIS):%Y-%m-%d %H:%M} | {ev['summary']}")

    original = INDEX.read_text(encoding="utf-8")
    updated = splice(original, render_block(events))

    if updated == original:
        print("[agenda] Aucun changement.")
        return 0

    INDEX.write_text(updated, encoding="utf-8")
    print("[agenda] index.html mis à jour.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
