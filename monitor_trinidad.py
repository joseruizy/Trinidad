#!/usr/bin/env python3
"""
Monitor diario de Mercado Público para Trinidad Callejas Bello.

Consulta la API oficial, detecta licitaciones nuevas que coinciden con
los perfiles configurados (lógica AND dentro de cada perfil, OR entre
perfiles), y envía un correo con el resumen.

Configuración: ver config.py
"""

import json
import os
import smtplib
import sys
import time
import unicodedata
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from config import CODIGOS_TIPO, PERFILES

# ---------- Constantes ----------
TZ = ZoneInfo("America/Santiago")
API_BASE = "https://api.mercadopublico.cl/servicios/v1/Publico/Licitaciones.json"
FICHA_URL = (
    "https://www.mercadopublico.cl/Procurement/Modules/RFB/"
    "DetailsAcquisition.aspx?idlicitacion={code}"
)
SEEN_FILE = Path("seen.json")
MAX_SEEN = 5000
THROTTLE_S = 0.05
MAX_DETALLES_POR_RUN = 800
CODIGO_ESTADO_PUBLICADA_ACTIVA = 5


# ---------- Utilidades ----------
def normalize(text: str) -> str:
    """Quita tildes y pasa a minúsculas para comparación robusta."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def get_codigo_tipo(licitacion: dict) -> str:
    if isinstance(licitacion.get("Tipo"), str):
        return licitacion["Tipo"].upper()
    if isinstance(licitacion.get("Tipo"), dict):
        return str(licitacion["Tipo"].get("Codigo", "")).upper()
    if licitacion.get("CodigoTipo"):
        return str(licitacion["CodigoTipo"]).upper()
    return ""


def get_nombre_organismo(licitacion: dict) -> str:
    if licitacion.get("NombreOrganismo"):
        return licitacion["NombreOrganismo"]
    comprador = licitacion.get("Comprador") or {}
    if isinstance(comprador, dict):
        return comprador.get("NombreOrganismo", "")
    return ""


def perfil_matchea(licitacion: dict, palabras: list[str]) -> bool:
    """True si TODAS las palabras del perfil están en Nombre o Descripcion (AND)."""
    if not palabras:
        return False
    haystack = normalize(
        f"{licitacion.get('Nombre', '')} {licitacion.get('Descripcion', '')}"
    )
    return all(normalize(p) in haystack for p in palabras)


def perfiles_que_matchean(licitacion: dict, perfiles: list[dict]) -> list[str]:
    """Retorna los nombres de los perfiles que matchean (puede ser >1)."""
    return [
        p["nombre"]
        for p in perfiles
        if perfil_matchea(licitacion, p["palabras"])
    ]


def is_publicada_activa(licitacion: dict) -> bool:
    return licitacion.get("CodigoEstado") == CODIGO_ESTADO_PUBLICADA_ACTIVA


# ---------- API ----------
def api_call(ticket: str, params: dict, retries: int = 3) -> list[dict]:
    params = {**params, "ticket": ticket}
    backoff = 2
    for intento in range(retries):
        try:
            r = requests.get(API_BASE, params=params, timeout=60)
            if r.status_code == 200:
                data = r.json()
                return data.get("Listado", []) or []
            if r.status_code == 429:
                print(f"[WARN] Rate limit (intento {intento+1}); espero {backoff}s")
                time.sleep(backoff)
                backoff *= 2
                continue
            print(f"[ERROR] HTTP {r.status_code}: {r.text[:200]}")
            return []
        except requests.RequestException as e:
            print(f"[WARN] Error de red (intento {intento+1}): {e}")
            time.sleep(backoff)
            backoff *= 2
    return []


def fecha_api(d: datetime) -> str:
    return d.strftime("%d%m%Y")


def fetch_listado_publicadas(ticket: str, fecha: datetime) -> list[dict]:
    return api_call(ticket, {"estado": "publicada", "fecha": fecha_api(fecha)})


def fetch_detalle(ticket: str, codigo: str) -> dict | None:
    items = api_call(ticket, {"codigo": codigo})
    return items[0] if items else None


# ---------- Persistencia ----------
def load_seen() -> tuple[set[str], bool]:
    if not SEEN_FILE.exists():
        return set(), True
    try:
        with SEEN_FILE.open() as f:
            data = json.load(f)
        ids = set(data.get("ids", []))
        is_first = data.get("updated") is None
        return ids, is_first
    except (json.JSONDecodeError, OSError):
        return set(), True


def save_seen(seen: set[str]) -> None:
    ids = list(seen)
    if len(ids) > MAX_SEEN:
        ids = ids[-MAX_SEEN:]
    with SEEN_FILE.open("w") as f:
        json.dump({"ids": ids, "updated": datetime.now(TZ).isoformat()}, f, indent=2)


# ---------- HTML ----------
def build_email_html(date_str: str, total: int, items: list[dict]) -> str:
    if not items:
        cuerpo = "<p><em>Sin novedades hoy.</em></p>"
    else:
        filas = []
        for it in items:
            code = it.get("CodigoExterno", "")
            nombre = it.get("Nombre", "")
            org = get_nombre_organismo(it)
            cierre = (it.get("FechaCierre") or "")[:10]
            tipo = get_codigo_tipo(it)
            link = FICHA_URL.format(code=code)
            perfiles_match = it.get("_perfiles_match", [])
            coincidencias = ", ".join(
                f"<strong>{p}</strong>" for p in perfiles_match
            ) or "—"
            filas.append(
                f"<tr>"
                f"<td style='padding:6px; border:1px solid #ddd;'>"
                f"<a href='{link}'>{code}</a></td>"
                f"<td style='padding:6px; border:1px solid #ddd;'>{tipo}</td>"
                f"<td style='padding:6px; border:1px solid #ddd;'>{nombre}</td>"
                f"<td style='padding:6px; border:1px solid #ddd;'>{org}</td>"
                f"<td style='padding:6px; border:1px solid #ddd;'>{cierre}</td>"
                f"<td style='padding:6px; border:1px solid #ddd;'>{coincidencias}</td>"
                f"</tr>"
            )
        cuerpo = (
            "<table style='width:100%; border-collapse:collapse; font-size:13px;'>"
            "<tr style='background:#f0f4f8; text-align:left;'>"
            "<th style='padding:6px; border:1px solid #ddd;'>Código</th>"
            "<th style='padding:6px; border:1px solid #ddd;'>Tipo</th>"
            "<th style='padding:6px; border:1px solid #ddd;'>Nombre</th>"
            "<th style='padding:6px; border:1px solid #ddd;'>Organismo</th>"
            "<th style='padding:6px; border:1px solid #ddd;'>Cierre</th>"
            "<th style='padding:6px; border:1px solid #ddd;'>Perfil(es)</th>"
            "</tr>"
            + "".join(filas)
            + "</table>"
        )

    # Listado de perfiles configurados (para que Trinidad sepa qué busca)
    perfiles_list = "".join(
        f"<li><strong>{p['nombre']}</strong>: {' + '.join(p['palabras'])}</li>"
        for p in PERFILES
    )

    return f"""
    <html><body style='font-family: Arial, sans-serif; color:#222;'>
    <p>Monitor Mercado Público — Trinidad Callejas — <strong>{date_str}</strong></p>
    <p>Se detectaron <strong>{total}</strong> licitación(es) nueva(s).</p>
    <h2 style='color:#1a1a1a; border-bottom:2px solid #0066cc;'>Resultados</h2>
    {cuerpo}
    <h3 style='margin-top:30px; color:#666; font-size:14px;'>Perfiles de búsqueda monitoreados</h3>
    <ul style='font-size:12px; color:#666;'>{perfiles_list}</ul>
    <hr style='margin-top:30px; border:none; border-top:1px solid #eee;'>
    <p style='font-size:11px; color:#888;'>
    Generado automáticamente por monitor-mp-trinidad en GitHub Actions.
    Las palabras dentro de cada perfil se buscan con lógica AND
    (deben aparecer todas en el nombre o descripción de la licitación).
    </p>
    </body></html>
    """


# ---------- Correo ----------
def send_email(subject: str, body_html: str) -> bool:
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    to = os.environ.get("NOTIFY_TO")

    if not all([host, user, password, to]):
        print("[INFO] Variables SMTP no configuradas: omito envío de correo.")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    recipients = [r.strip() for r in to.split(",") if r.strip()]

    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(user, password)
        server.sendmail(user, recipients, msg.as_string())
    print(f"[OK] Correo enviado a {len(recipients)} destinatario(s): {to}")
    return True


# ---------- Main ----------
def main() -> int:
    today = datetime.now(TZ)
    date_str = today.strftime("%d-%m-%Y")
    print(f"[INFO] Ejecutando monitor MP — Trinidad — {date_str}")

    ticket = os.environ.get("MP_TICKET")
    if not ticket:
        print("[ERROR] Falta variable de entorno MP_TICKET", file=sys.stderr)
        return 1

    seen, is_first_run = load_seen()
    print(f"[INFO] IDs ya notificados anteriormente: {len(seen)}")
    if is_first_run:
        print("[INFO] Primera ejecución detectada (modo bootstrap).")

    fechas_a_consultar = [today]
    if today.weekday() == 0:  # lunes
        fechas_a_consultar = [
            today,
            today - timedelta(days=3),
            today - timedelta(days=2),
        ]
    print(
        f"[INFO] Fechas a consultar: "
        f"{[f.strftime('%d-%m-%Y') for f in fechas_a_consultar]}"
    )

    # Descargar listado general
    listado_general: list[dict] = []
    for fecha in fechas_a_consultar:
        print(f"[INFO] Descargando listado general fecha {fecha.strftime('%d-%m-%Y')}")
        parte = fetch_listado_publicadas(ticket, fecha)
        parte_activa = [l for l in parte if is_publicada_activa(l)]
        print(f"  → {len(parte)} traídas ({len(parte_activa)} activas)")
        listado_general.extend(parte_activa)

    listado_general = list(
        {l["CodigoExterno"]: l for l in listado_general}.values()
    )
    print(f"[INFO] Total listado general (únicos, activos): {len(listado_general)}")

    nuevos_general = [
        l for l in listado_general if l.get("CodigoExterno") not in seen
    ]
    print(f"  → {len(nuevos_general)} no notificados antes")

    # Bootstrap
    if is_first_run:
        ids_para_guardar = {l["CodigoExterno"] for l in nuevos_general}
        save_seen(seen | ids_para_guardar)
        print(
            f"[OK] Bootstrap completado. {len(ids_para_guardar)} IDs guardados. "
            "El siguiente run notificará solo licitaciones nuevas."
        )
        return 0

    # Consultar detalle
    ids_a_detallar = {l["CodigoExterno"] for l in nuevos_general}
    if len(ids_a_detallar) > MAX_DETALLES_POR_RUN:
        print(
            f"[WARN] Hay {len(ids_a_detallar)} IDs por detallar; "
            f"limitando a {MAX_DETALLES_POR_RUN} por seguridad."
        )
        ids_a_detallar = set(list(ids_a_detallar)[:MAX_DETALLES_POR_RUN])

    print(f"[INFO] Consultando detalle de {len(ids_a_detallar)} licitaciones")
    detalles: dict[str, dict] = {}
    for i, codigo in enumerate(ids_a_detallar, 1):
        det = fetch_detalle(ticket, codigo)
        if det:
            detalles[codigo] = det
        if i % 50 == 0:
            print(f"  → {i}/{len(ids_a_detallar)}")
        time.sleep(THROTTLE_S)
    print(f"[INFO] Detalles obtenidos: {len(detalles)}")

    # Aplicar filtros: tipo correcto + algún perfil matchea
    tipos_validos = {t.upper() for t in CODIGOS_TIPO}
    items_matchados: list[dict] = []
    for codigo, det in detalles.items():
        if get_codigo_tipo(det) not in tipos_validos:
            continue
        perfiles_match = perfiles_que_matchean(det, PERFILES)
        if perfiles_match:
            det["_perfiles_match"] = perfiles_match
            items_matchados.append(det)

    # Diagnóstico por perfil
    print("[INFO] Resumen de coincidencias por perfil:")
    for p in PERFILES:
        n = sum(1 for it in items_matchados if p["nombre"] in it["_perfiles_match"])
        print(f"  → {p['nombre']}: {n}")

    total = len(items_matchados)
    print(f"[INFO] Total licitaciones a notificar: {total}")

    notify_always = os.environ.get("NOTIFY_ALWAYS", "0") == "1"

    if total == 0 and not notify_always:
        print("[OK] Sin novedades. No envío correo.")
        seen.update(detalles.keys())
        save_seen(seen)
        return 0

    subject = f"[MP-Trinidad {date_str}] {total} licitación(es) nueva(s)"
    body = build_email_html(date_str, total, items_matchados)
    try:
        send_email(subject, body)
    except Exception as e:
        print(f"[ERROR] Falló envío de correo: {e}", file=sys.stderr)
        return 1

    seen.update(it["CodigoExterno"] for it in items_matchados)
    seen.update(detalles.keys())
    save_seen(seen)
    print("[OK] seen.json actualizado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
