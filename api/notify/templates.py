"""Human-written message templates: one per group and posture.

Every message has seven parts: what is happening, whether it applies to you,
what to do, the effective period, the next update, how to acknowledge, and the
default if no update arrives (silence is not an all-clear).

Variants: "standard" (English), "large_print" (English, one part per block,
capitals for headings) and "spanish". If a variant is missing we return the
English text with needs_translation=True, never silent English.
Acknowledgment means "received", never "understood".

Spanish text is a team draft and has not been reviewed by a native speaker.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from api.clock import parse_iso

VARIANTS = ("standard", "large_print", "spanish")

HEADINGS = {
    "en": ["What is happening", "Does this apply to you", "What to do", "Effective",
           "Next update", "Acknowledge", "If no update arrives"],
    "es": ["Qué está pasando", "Le aplica a usted", "Qué hacer", "Vigencia",
           "Próxima actualización", "Confirme la recepción", "Si no llega ninguna actualización"],
}

ACK = {
    "en": "Reply OK or press Acknowledge to confirm you received this message.",
    "es": "Responda OK o pulse Confirmar para indicar que recibió este mensaje.",
}

POSTURE_NAME = {
    "en": {"delayed_arrival": "Delayed arrival", "early_dismissal": "Early dismissal",
           "unscheduled_leave_or_telework": "Unscheduled leave or telework",
           "closure": "Facility closed", "normal_operations": "Normal operations"},
    "es": {"closure": "Instalación cerrada"},
}

_ES_MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def fmt_time(value: str | None, tz_name: str, lang: str = "en") -> str:
    """Local, human time. None becomes a clear 'not set' phrase."""
    if not value:
        return "not set yet" if lang == "en" else "sin definir"
    local: datetime = parse_iso(value).astimezone(ZoneInfo(tz_name))
    if lang == "es":
        return f"{local.day} {_ES_MONTHS[local.month - 1]}, {local:%H:%M}"
    return f"{local:%a %b} {local.day}, {local:%I:%M %p}".replace(" 0", " ")


# ---------------------------------------------------------------- English body
# Each entry returns (applies, what_to_do, default_if_no_update) for a group.

def _en_parts(group: str, posture: str, t: dict) -> tuple[str, str, str] | None:
    if group == "essential":
        return ("Yes. You are essential staff.",
                "Report as scheduled. Allow extra travel time and travel only if it is safe.",
                "Keep reporting as scheduled and follow your supervisor.")
    if group == "contractor":
        return ("Yes, as site status. Your work status goes through your contract lead.",
                "Contact your contract lead before coming on site.",
                "Check with your contract lead before coming on site.")
    # DEPRECATED(closureiq) START: teleworkers only had a closure message; changed hours now included.
    # if group == "already_teleworking":
    #     if posture != "closure":
    #         return None
    #     return ("For information only. You are already teleworking.",
    #             "Keep teleworking as planned. Do not come to the building.",
    #             "Keep teleworking and do not come to the building.")
    # DEPRECATED(closureiq) END
    building = {
        "closure": f"The building is closed from {t['closed_from']} until {t['closed_until']}.",
        "delayed_arrival": f"The building opens late, at {t['delay_until']}.",
        "early_dismissal": f"The building closes early, at {t['dismiss_at']}.",
    }.get(posture)
    if group == "already_teleworking":
        if building is None:
            return None
        return ("For information only. You are already teleworking.",
                f"{building} Keep teleworking as planned; you do not need to come in.",
                "Keep teleworking as planned.")
    if group == "on_leave_or_off":
        if building is None:
            return None
        return ("For information only. You are on leave or off today.",
                f"{building} No action is needed from you today.",
                "No action needed. Check for an update before your next shift.")
    eligible = group == "onsite_telework_eligible"
    if posture == "delayed_arrival":
        return ("Yes. You are assigned onsite today.",
                f"Arrive no earlier than {t['delay_until']}."
                + (" You may telework instead." if eligible else ""),
                "Keep the delayed arrival time. Do not come in earlier.")
    if posture == "early_dismissal":
        return ("Yes. You are assigned onsite today.",
                f"Leave the building at {t['dismiss_at']}."
                + (" You may finish the day by telework." if eligible else ""),
                "Leave at the stated time.")
    if posture == "unscheduled_leave_or_telework":
        if eligible:
            return ("Yes. You are assigned onsite today and telework-eligible.",
                    "Telework today, or take unscheduled leave per policy. Tell your supervisor which.",
                    "Keep teleworking or on leave until told otherwise.")
        return ("Yes. You are assigned onsite today.",
                "Report unless your supervisor tells you otherwise. If you cannot travel safely, "
                "ask your supervisor about unscheduled leave per policy.",
                "Follow your supervisor's direction. Do not travel if it is unsafe.")
    if posture == "closure":
        return ("Yes. You are assigned onsite today.",
                "Do not report to the building. "
                + ("Telework or take leave per policy." if eligible else "Take leave per policy."),
                "Stay closed. Do not report until you receive a notice that the facility has reopened.")
    return None


# ---------------------------------------------------------------- Spanish body
# Only closure is written so far. Anything else returns None -> needs translation.

def _es_parts(group: str, posture: str, t: dict) -> tuple[str, str, str] | None:
    if posture != "closure":
        return None
    if group == "essential":
        return ("Sí. Usted es personal esencial.",
                "Preséntese según su horario. Calcule tiempo extra y viaje solo si es seguro.",
                "Siga presentándose según su horario y siga las indicaciones de su supervisor.")
    if group == "contractor":
        return ("Sí, como estado del sitio. Su situación laboral se coordina con su jefe de contrato.",
                "Comuníquese con su jefe de contrato antes de venir al sitio.",
                "Consulte con su jefe de contrato antes de venir al sitio.")
    if group == "already_teleworking":
        return ("Solo para su información. Usted ya está en teletrabajo.",
                "Siga en teletrabajo. No venga al edificio.",
                "Siga en teletrabajo y no venga al edificio.")
    eligible = group == "onsite_telework_eligible"
    return ("Sí. Usted tiene asignado trabajo presencial hoy.",
            "No se presente en el edificio. "
            + ("Haga teletrabajo o tome licencia según la política." if eligible
               else "Tome licencia según la política."),
            "La instalación sigue cerrada. No se presente hasta recibir un aviso de reapertura.")


# ---------------------------------------------------------------- assembly

def _effective(posture: str, t: dict, lang: str) -> str:
    if lang == "es":
        return f"Desde {t['closed_from']} hasta {t['closed_until']}."
    return {
        "delayed_arrival": f"Start of shift until {t['delay_until']}.",
        "early_dismissal": f"From {t['dismiss_at']} until the end of the day.",
        "unscheduled_leave_or_telework": "From now until the next update.",
        "closure": f"From {t['closed_from']} until {t['closed_until']}.",
    }.get(posture, "Until the next update.")


def _times(parameters: dict, tz_name: str, lang: str) -> dict:
    keys = ("delay_until", "dismiss_at", "closed_from", "closed_until", "next_update")
    return {k: fmt_time(parameters.get(k), tz_name, lang) for k in keys}


def _join(headings: list[str], values: list[str], large_print: bool) -> str:
    if large_print:
        return "\n\n".join(f"{h.upper()}:\n{v}" for h, v in zip(headings, values))
    return "\n".join(f"{h}: {v}" for h, v in zip(headings, values))


def render_message(group: str, posture: str, parameters: dict, facility_name: str,
                   tz_name: str, variant: str = "standard") -> dict | None:
    """Return {text, variant, needs_translation}, or None if this group gets no message.

    A missing Spanish template falls back to English text with needs_translation=True.
    """
    lang = "es" if variant == "spanish" else "en"
    parts = (_es_parts if lang == "es" else _en_parts)(group, posture, _times(parameters, tz_name, lang))
    if parts is None and lang == "es":
        english = render_message(group, posture, parameters, facility_name, tz_name, "standard")
        if english is None:
            return None
        return {"text": english["text"], "variant": "spanish", "needs_translation": True}
    if parts is None:
        return None
    t = _times(parameters, tz_name, lang)
    applies, todo, default = parts
    values = [f"{facility_name}: {POSTURE_NAME[lang][posture]}.", applies, todo,
              _effective(posture, t, lang), t["next_update"], ACK[lang], default]
    text = _join(HEADINGS[lang], values, large_print=variant == "large_print")
    return {"text": text, "variant": variant, "needs_translation": False}


# ---------------------------------------------------------------- shelter in place

SHELTER_TEXT = {
    "en": ("SHELTER IN PLACE NOW at {facility}. A warning is in effect for this site. "
           "Move to the interior shelter area away from windows. Stay there until an all-clear "
           "message arrives. If no update arrives, keep sheltering. "
           "Reply OK to confirm you received this message."),
    "es": ("REFÚGIESE AHORA en {facility}. Hay una alerta vigente para este sitio. "
           "Vaya al área de refugio interior, lejos de las ventanas. Permanezca allí hasta recibir "
           "un mensaje de que el peligro pasó. Si no llega ninguna actualización, siga refugiado. "
           "Responda OK para indicar que recibió este mensaje."),
}


def render_shelter(facility_name: str, variant: str = "standard") -> dict:
    lang = "es" if variant == "spanish" else "en"
    text = SHELTER_TEXT[lang].format(facility=facility_name)
    if variant == "large_print":
        text = text.replace(". ", ".\n\n")
    return {"text": text, "variant": variant, "needs_translation": False}


def variant_for(comm_needs: list[str] | None) -> str:
    """Pick the message variant for one person's comm_needs flags."""
    needs = comm_needs or []
    if "spanish" in needs:
        return "spanish"
    if "large_print" in needs:
        return "large_print"
    return "standard"
