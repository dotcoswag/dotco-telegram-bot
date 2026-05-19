"""
scraper.py
----------
Core API logic for DotCo Swag lead scraper.
Calls RapidAPI local-business-data, paginates, deduplicates, saves to CSV.
"""

import csv
import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("RAPIDAPI_KEY")
URL = "https://local-business-data.p.rapidapi.com/search"
HEADERS = {
    "x-rapidapi-key": API_KEY,
    "x-rapidapi-host": "local-business-data.p.rapidapi.com",
}

# ── Config ────────────────────────────────────────────────────
LIMIT_POR_LLAMADA = 500
DELAY_SEGUNDOS = 1
PAGINATION_PARAM = "offset"
# ─────────────────────────────────────────────────────────────


class QuotaExhausted(Exception):
    """Raised when RapidAPI returns a permanent quota-exceeded error (non-retryable).

    Distinguishable from transient 429 rate-limits, which the caller retries.
    Callers should stop the entire scrape job — retrying won't help.
    """

COLUMNAS_CSV = [
    # Identity
    "business_id",
    "nombre",
    "tipo",
    "subtipo",
    # Quality
    "rating",
    "review_count",
    "verified",
    "business_status",
    "lead_score",
    "photos_count",
    # Location
    "direccion",
    "city",
    "state",
    "district",
    "latitude",
    "longitude",
    # Contact
    "telefono",
    "email",
    "website",
    # Social
    "instagram",
    "facebook",
    "linkedin",
    "twitter",
    "youtube",
    "emails_extra",
    # Links
    "link_google_maps",
    "booking_link",
    "menu_link",
    "order_link",
    # Search metadata
    "localidad_buscada",
    "categoria_buscada",
    "provincia",
]


def calcular_lead_score(negocio, contactos, email_principal):
    """Score 0–7 based on contact completeness and quality."""
    score = 0
    if negocio.get("phone_number"):
        score += 1
    if negocio.get("website"):
        score += 1
    try:
        if float(negocio.get("rating", 0)) >= 4.0:
            score += 1
    except (ValueError, TypeError):
        pass
    try:
        if int(negocio.get("review_count", 0)) >= 20:
            score += 1
    except (ValueError, TypeError):
        pass
    if negocio.get("verified"):
        score += 1
    if email_principal:
        score += 1
    if contactos.get("instagram") or contactos.get("facebook") or contactos.get("linkedin"):
        score += 1
    return score


def _interruptible_sleep(seconds, cancel_event):
    """Sleep that returns early if cancel_event is set. Returns True iff cancelled."""
    if cancel_event is None:
        time.sleep(seconds)
        return False
    return cancel_event.wait(timeout=seconds)


def llamar_api(query, limit, pagina_offset, max_retries=3, cancel_event=None):
    params = {
        "query": query,
        "limit": limit,
        PAGINATION_PARAM: pagina_offset,
        "region": "us",
        "language": "en",
        "zoom": "13",
        "extract_emails_and_contacts": "true",
    }

    for attempt in range(max_retries + 1):
        if cancel_event is not None and cancel_event.is_set():
            return []
        try:
            resp = requests.get(URL, headers=HEADERS, params=params, timeout=30)

            # Handle rate limiting
            if resp.status_code == 429:
                quota_msg = ""
                try:
                    quota_msg = (resp.json().get("message") or "")
                except (ValueError, AttributeError):
                    pass
                qm = quota_msg.lower()
                if "exceeded" in qm and ("quota" in qm or "plan" in qm):
                    # Permanent quota error — don't retry, abort the entire scrape.
                    raise QuotaExhausted(quota_msg)
                wait_time = int(resp.headers.get("Retry-After", 30))
                if attempt < max_retries:
                    print(f"      ⏳ Rate limited (429). Waiting {wait_time}s before retry...", flush=True)
                    if _interruptible_sleep(wait_time, cancel_event):
                        return []
                    continue
                else:
                    print(f"      ⚠️  Rate limited after {max_retries} retries. Skipping.", flush=True)
                    return []

            resp.raise_for_status()
            data = resp.json()
            return data.get("data", [])

        except QuotaExhausted:
            # Permanent quota error — must propagate; the generic `except Exception`
            # below would otherwise swallow it as a "network error".
            raise
        except requests.exceptions.HTTPError as e:
            if attempt < max_retries:
                wait_time = 2 ** attempt
                print(f"      ⚠️  HTTP Error {resp.status_code}. Retry {attempt+1}/{max_retries} in {wait_time}s...", flush=True)
                if _interruptible_sleep(wait_time, cancel_event):
                    return []
            else:
                print(f"      ⚠️  HTTP Error {resp.status_code} after {max_retries} retries: {e}", flush=True)
                return []
        except Exception as e:
            if attempt < max_retries:
                wait_time = 2 ** attempt
                print(f"      ⚠️  Network error. Retry {attempt+1}/{max_retries} in {wait_time}s...", flush=True)
                if _interruptible_sleep(wait_time, cancel_event):
                    return []
            else:
                print(f"      ⚠️  Network error after {max_retries} retries: {e}", flush=True)
                return []

    return []


def negocio_a_fila(negocio, localidad, categoria, provincia):
    subtypes = negocio.get("subtypes", [])
    subtipo_str = " | ".join(subtypes) if isinstance(subtypes, list) else str(subtypes or "")

    place_link = negocio.get("place_link", "")
    place_id = negocio.get("place_id", "")
    if not place_link and place_id:
        place_link = f"https://www.google.com/maps/place/?q=place_id:{place_id}"

    contactos = negocio.get("emails_and_contacts") or {}
    if not isinstance(contactos, dict):
        contactos = {}

    emails_lista = contactos.get("emails") or []
    if not isinstance(emails_lista, list):
        emails_lista = []

    email_principal = negocio.get("email", "") or (emails_lista[0] if emails_lista else "")
    emails_extra = " | ".join(emails_lista)

    return {
        "business_id": negocio.get("business_id", ""),
        "nombre": negocio.get("name", ""),
        "tipo": negocio.get("type", ""),
        "subtipo": subtipo_str,
        "rating": negocio.get("rating", ""),
        "review_count": negocio.get("review_count", ""),
        "verified": negocio.get("verified", ""),
        "business_status": negocio.get("business_status", ""),
        "lead_score": calcular_lead_score(negocio, contactos, email_principal),
        "photos_count": negocio.get("photos_count", ""),
        "direccion": negocio.get("full_address", ""),
        "city": negocio.get("city", ""),
        "state": negocio.get("state", ""),
        "district": negocio.get("district", ""),
        "latitude": negocio.get("latitude", ""),
        "longitude": negocio.get("longitude", ""),
        "telefono": negocio.get("phone_number", ""),
        "email": email_principal,
        "website": negocio.get("website", ""),
        "instagram": contactos.get("instagram", ""),
        "facebook": contactos.get("facebook", ""),
        "linkedin": contactos.get("linkedin", ""),
        "twitter": contactos.get("twitter", ""),
        "youtube": contactos.get("youtube", ""),
        "emails_extra": emails_extra,
        "link_google_maps": place_link,
        "booking_link": negocio.get("booking_link", ""),
        "menu_link": negocio.get("menu_link", ""),
        "order_link": negocio.get("order_link", ""),
        "localidad_buscada": localidad,
        "categoria_buscada": categoria,
        "provincia": provincia,
    }


def guardar_en_csv(negocios, archivo_csv, localidad, categoria, provincia):
    archivo_nuevo = not os.path.exists(archivo_csv)
    with open(archivo_csv, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNAS_CSV)
        if archivo_nuevo:
            writer.writeheader()
        for negocio in negocios:
            fila = negocio_a_fila(negocio, localidad, categoria, provincia)
            writer.writerow(fila)


def guardar_en_csv_filas(filas, archivo_csv):
    """Save pre-built row dicts directly to CSV (used when filtering by min_score)."""
    archivo_nuevo = not os.path.exists(archivo_csv)
    with open(archivo_csv, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNAS_CSV)
        if archivo_nuevo:
            writer.writeheader()
        for fila in filas:
            writer.writerow(fila)


def scrape_combinacion(localidad, categoria, provincia, archivo_csv, seen_ids, limite_total, min_score=0, cancel_event=None):
    query = f"{categoria} in {localidad}, {provincia}"
    offset = 0
    total_nuevos = 0
    total_duplicados = 0
    total_skipped_score = 0

    while True:
        if cancel_event is not None and cancel_event.is_set():
            break
        if limite_total is not None and len(seen_ids) >= limite_total:
            break

        negocios = llamar_api(query, LIMIT_POR_LLAMADA, offset, cancel_event=cancel_event)

        if not negocios:
            break

        nuevos = []
        for n in negocios:
            bid = n.get("business_id", n.get("place_id", ""))
            if bid and bid not in seen_ids:
                if limite_total is not None and len(seen_ids) >= limite_total:
                    break
                seen_ids.add(bid)
                # Convert to row and check lead_score before adding to nuevos
                fila = negocio_a_fila(n, localidad, categoria, provincia)
                if fila.get("lead_score", 0) >= min_score:
                    nuevos.append(fila)
                else:
                    total_skipped_score += 1
            else:
                total_duplicados += 1

        if nuevos:
            guardar_en_csv_filas(nuevos, archivo_csv)
            total_nuevos += len(nuevos)

        if len(negocios) < LIMIT_POR_LLAMADA:
            break

        offset += LIMIT_POR_LLAMADA
        if _interruptible_sleep(DELAY_SEGUNDOS, cancel_event):
            break

    return total_nuevos, total_duplicados, total_skipped_score
