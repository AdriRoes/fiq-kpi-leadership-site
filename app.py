#!/usr/bin/env python3
"""
FIQ KPI — Leadership site
==========================
Tiny read-only web app hosted on Render. It does exactly one thing: show
the most recently published copy of the KPI dashboard (the same HTML that
Scripts/generate_dashboard.py already builds on Adriana's Mac every day),
protected by a shared username/password.

Where the data comes from:
    Adriana's Mac runs the normal daily automation (Auto Download KPI /
    Update KPI). At the end, Scripts/publish_dashboard.py copies the
    finished HTML into the "published_dashboard" table in the shared
    "fiq_kpi" Postgres database on Render. This app just reads that table
    — it never touches Adriana's computer and never regenerates anything
    itself, so it stays up (and shows the latest report) even if her Mac
    is off.

Environment variables this service needs (set in the Render dashboard,
never in this code):
    DATABASE_URL   — the fiq_kpi database's connection string
                      (use the Postgres instance's Internal Connection
                      String if this service lives in the same Render
                      account/region — it's free and faster than external)
    SITE_USER      — shared login username for leadership (any value you pick)
    SITE_PASSWORD  — shared login password for leadership (any value you pick)
"""

import os
from functools import wraps

import psycopg2
from flask import Flask, Response, request

app = Flask(__name__)


def _env(name, default=None, required=False):
    val = os.environ.get(name, default)
    if required and not val:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val


def check_auth(username, password):
    return (
        username == _env("SITE_USER", required=True)
        and password == _env("SITE_PASSWORD", required=True)
    )


def authenticate():
    return Response(
        "Acceso restringido. Ingresa el usuario y contraseña del reporte de KPIs.",
        401,
        {"WWW-Authenticate": 'Basic realm="FIQ KPI Leadership Report"'},
    )


def requires_auth(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return view(*args, **kwargs)
    return wrapped


def fetch_html(slug):
    """Returns (html_content, updated_at) for the given slug, or None if
    nothing has been published yet."""
    conn = psycopg2.connect(_env("DATABASE_URL", required=True))
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT html_content, updated_at FROM published_dashboard WHERE slug = %s",
                (slug,),
            )
            return cur.fetchone()
    finally:
        conn.close()


PLACEHOLDER = """<!DOCTYPE html><html><body style="font-family:sans-serif;
padding:40px;text-align:center;color:#444">
<h2>Todavía no se ha publicado ningún reporte.</h2>
<p>Esto aparece antes de la primera vez que se corre el proceso de
descarga diario en la computadora de Adriana. Debería actualizarse solo
en la próxima corrida.</p>
</body></html>"""


@app.route("/")
@requires_auth
def desktop_report():
    row = fetch_html("main")
    if not row:
        return PLACEHOLDER, 200
    html, _updated_at = row
    return html


@app.route("/mobile")
@requires_auth
def mobile_report():
    row = fetch_html("mobile")
    if not row:
        return PLACEHOLDER, 200
    html, _updated_at = row
    return html


@app.route("/healthz")
def healthz():
    # Unauthenticated on purpose — lets Render's own health checks pass
    # without needing credentials, and reveals no report data.
    return "ok", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
