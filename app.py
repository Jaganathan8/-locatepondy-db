"""
LOCATEPONDY - Discover Food Shops Across Pondicherry
=====================================================
SINGLE-FILE full-stack Flask application. Backend (routes, models, auth,
admin panel) and frontend (HTML templates + CSS + JS, all inlined) live
entirely in this one app.py — no templates/ or static/ folders needed.

Run:
    pip install -r requirements.txt
    python app.py

Then open http://127.0.0.1:5000

On first run a default admin account is seeded from config (ADMIN_USERNAME /
ADMIN_PASSWORD, or the matching environment variables). Log in to it at
/admin/login and change the password immediately if you kept the default.
"""

import os
import random
import string
import uuid
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, abort
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func


# ----------------------------------------------------------------------
# Config (inlined — was config.py)
# ----------------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Recognized as "unsafe" — if this is still the SECRET_KEY at startup, app.py
# will print a loud warning telling you to set a real one before deploying.
_DEV_SECRET = "locatepondy-dev-secret-change-in-production"


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", _DEV_SECRET)

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'locatepondy.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # 20 MB total request (up to 5 photos x ~4MB)
    MAX_PHOTOS_PER_SHOP = 5
    SHOP_NAME_MAX_LENGTH = 150

    # ---- Google OAuth (fill these in to enable real Google Sign-In) ----
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

    # ---- SMS/OTP gateway (fill these in to enable real phone OTP) ----
    SMS_GATEWAY_API_KEY = os.environ.get("SMS_GATEWAY_API_KEY", "")
    OTP_EXPIRY_SECONDS = 300          # 5 minutes
    OTP_MAX_ATTEMPTS = 5

    # ---- Admin account (seeded automatically on first run) ----
    # Change these via environment variables before deploying anywhere real.
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "ChangeMe@123")

    # ---- Login security ----
    MAX_FAILED_LOGIN_ATTEMPTS = 5
    ACCOUNT_LOCKOUT_MINUTES = 15

    # ---- Session / cookie security ----
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Set FORCE_HTTPS=1 in production (behind HTTPS) to mark cookies secure-only.
    SESSION_COOKIE_SECURE = os.environ.get("FORCE_HTTPS", "0") == "1"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 4  # 4 hours

    # ---- CSRF ----
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None


# ----------------------------------------------------------------------
# Templates (inlined — was templates/*.html). CSS + JS are inlined inside
# the "base.html" entry itself, so no static/css or static/js files
# are needed either. Served via a Jinja2 DictLoader below.
# ----------------------------------------------------------------------
TEMPLATES = {
  "base.html": "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n{% import \"_icons.html\" as icons %}\n  <meta charset=\"UTF-8\">\n  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n  <meta name=\"theme-color\" content=\"#FAF6EF\">\n  <title>{% block title %}LocatePondy — Food Shops of Pondicherry{% endblock %}</title>\n  <style>\n/* ==========================================================================\n   LOCATEPONDY — Design System\n   \"White Town, iOS glass\" — French-colonial Pondicherry palette rendered\n   through an Apple/iOS-style interface language: frosted blur bars, large\n   titles, pill buttons, segmented controls and continuous-corner cards.\n   ========================================================================== */\n\n:root {\n  /* ---- Pondicherry White Town palette ---- */\n  --bg:              #FAF6EF;   /* whitewashed wall */\n  --bg-elevated:     #FFFFFF;\n  --surface:         #FFFFFF;\n  --surface-alt:     #F4ECDA;   /* sun-warmed plaster */\n  --hairline:        rgba(43, 34, 24, 0.09);\n  --hairline-strong: rgba(43, 34, 24, 0.14);\n\n  --ink:             #2B2420;   /* colonial teak charcoal */\n  --ink-soft:        #6E6157;\n  --ink-faint:       #A79A8C;\n\n  --blue:            #1C6E8C;   /* shutter blue */\n  --blue-dark:       #144F64;\n  --blue-tint:       #E4F0F3;\n\n  --pink:            #D9527A;   /* bougainvillea */\n  --pink-dark:       #B23A5F;\n  --pink-tint:       #FBE9EE;\n\n  --mustard:         #E3A431;   /* facade ochre */\n  --mustard-dark:    #B87F1F;\n  --mustard-tint:    #FBF0DA;\n\n  --terracotta:      #C1592E;   /* tiled roof */\n  --terracotta-tint: #FBE8DE;\n\n  --green:           #3F8F5F;\n  --green-tint:      #E5F3EA;\n  --red:             #D93B2B;\n  --red-tint:        #FCEAE7;\n\n  /* ---- iOS-style system chrome ---- */\n  --blur-bg: rgba(250, 246, 239, 0.72);\n  --blur-bg-strong: rgba(255, 255, 255, 0.82);\n  --radius-lg: 22px;\n  --radius-md: 16px;\n  --radius-sm: 12px;\n  --radius-pill: 999px;\n  --shadow-card: 0 1px 2px rgba(43,34,24,0.04), 0 8px 24px rgba(43,34,24,0.07);\n  --shadow-pop: 0 12px 32px rgba(43,34,24,0.16);\n  --nav-h: 52px;\n  --tabbar-h: 58px;\n\n  --font-system: -apple-system, BlinkMacSystemFont, \"SF Pro Display\", \"SF Pro Text\",\n    \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif;\n  --font-display: Georgia, \"Iowan Old Style\", \"Palatino Linotype\", \"Book Antiqua\", serif;\n}\n\nsvg { display: block; }\n.icon-14 { width: 14px; height: 14px; }\n.icon-16 { width: 16px; height: 16px; }\n.icon-18 { width: 18px; height: 18px; }\n.icon-20 { width: 20px; height: 20px; }\n.icon-24 { width: 24px; height: 24px; }\n.icon-28 { width: 28px; height: 28px; }\n.brand-pin-icon { width: 18px; height: 18px; display: inline-block; }\n\n* { box-sizing: border-box; }\n\nhtml { -webkit-text-size-adjust: 100%; }\n\nbody {\n  margin: 0;\n  font-family: var(--font-system);\n  background: var(--bg);\n  color: var(--ink);\n  -webkit-font-smoothing: antialiased;\n  padding-top: var(--nav-h);\n  padding-bottom: calc(var(--tabbar-h) + env(safe-area-inset-bottom, 0px));\n  min-height: 100vh;\n}\n\na { color: inherit; text-decoration: none; }\nimg { max-width: 100%; display: block; }\nbutton { font-family: inherit; }\n\n::selection { background: var(--pink-tint); color: var(--pink-dark); }\n\n@media (prefers-reduced-motion: reduce) {\n  * { animation-duration: 0.001ms !important; transition-duration: 0.001ms !important; }\n}\n\n/* ==========================================================================\n   Top nav — frosted \"large title\" bar, iOS-style\n   ========================================================================== */\n\n.ios-navbar {\n  position: fixed;\n  top: 0; left: 0; right: 0;\n  z-index: 100;\n  height: var(--nav-h);\n  display: flex;\n  align-items: center;\n  justify-content: space-between;\n  padding: 0 16px;\n  background: var(--blur-bg);\n  -webkit-backdrop-filter: saturate(180%) blur(20px);\n  backdrop-filter: saturate(180%) blur(20px);\n  border-bottom: 0.5px solid var(--hairline-strong);\n}\n\n.ios-navbar .brand {\n  display: flex;\n  align-items: baseline;\n  gap: 6px;\n  font-family: var(--font-display);\n  font-weight: 700;\n  font-size: 19px;\n  color: var(--blue-dark);\n  letter-spacing: 0.2px;\n}\n\n.ios-navbar .brand .pin {\n  color: var(--pink);\n  font-family: var(--font-system);\n}\n\n.nav-actions { display: flex; align-items: center; gap: 14px; }\n\n.nav-icon-btn {\n  width: 34px; height: 34px;\n  display: flex; align-items: center; justify-content: center;\n  border-radius: var(--radius-pill);\n  background: rgba(43,34,24,0.05);\n  color: var(--blue-dark);\n}\n.nav-icon-btn:active { background: rgba(43,34,24,0.1); }\n\n/* Large-title page header, like an iOS nav large title beneath the bar */\n.large-title {\n  padding: 20px 20px 4px;\n}\n.large-title h1 {\n  font-family: var(--font-display);\n  font-weight: 700;\n  font-size: 32px;\n  margin: 0;\n  color: var(--ink);\n  letter-spacing: 0.1px;\n}\n.large-title p {\n  margin: 4px 0 0;\n  color: var(--ink-soft);\n  font-size: 15px;\n}\n\n/* ==========================================================================\n   Bottom tab bar — frosted glass, SF-symbol-style line icons\n   ========================================================================== */\n\n.ios-tabbar {\n  position: fixed;\n  bottom: 0; left: 0; right: 0;\n  z-index: 100;\n  height: calc(var(--tabbar-h) + env(safe-area-inset-bottom, 0px));\n  padding-bottom: env(safe-area-inset-bottom, 0px);\n  display: flex;\n  background: var(--blur-bg-strong);\n  -webkit-backdrop-filter: saturate(180%) blur(20px);\n  backdrop-filter: saturate(180%) blur(20px);\n  border-top: 0.5px solid var(--hairline-strong);\n}\n\n.tab-item {\n  flex: 1;\n  display: flex;\n  flex-direction: column;\n  align-items: center;\n  justify-content: center;\n  gap: 2px;\n  color: var(--ink-faint);\n  font-size: 10.5px;\n  font-weight: 500;\n  padding-top: 6px;\n}\n.tab-item svg { width: 24px; height: 24px; stroke: var(--ink-faint); fill: none; }\n.tab-item.active { color: var(--blue); }\n.tab-item.active svg { stroke: var(--blue); }\n.tab-item:active { opacity: 0.6; }\n\n/* ==========================================================================\n   Layout\n   ========================================================================== */\n\n.app-content { max-width: 720px; margin: 0 auto; padding: 0 0 24px; }\n.container { padding: 0 16px; }\n.section { padding: 20px 16px; }\n.section-title {\n  font-size: 13px;\n  font-weight: 600;\n  text-transform: uppercase;\n  letter-spacing: 0.6px;\n  color: var(--ink-soft);\n  margin: 0 0 10px 2px;\n}\n\n/* ==========================================================================\n   Toast / flash messages — iOS notification-banner style\n   ========================================================================== */\n\n.toast-stack {\n  position: fixed;\n  top: calc(var(--nav-h) + 8px);\n  left: 0; right: 0;\n  z-index: 200;\n  display: flex;\n  flex-direction: column;\n  align-items: center;\n  gap: 8px;\n  padding: 0 16px;\n  pointer-events: none;\n}\n.toast {\n  pointer-events: auto;\n  width: 100%;\n  max-width: 480px;\n  background: var(--blur-bg-strong);\n  -webkit-backdrop-filter: blur(20px);\n  backdrop-filter: blur(20px);\n  border-radius: var(--radius-md);\n  box-shadow: var(--shadow-pop);\n  padding: 12px 14px;\n  display: flex;\n  align-items: flex-start;\n  gap: 10px;\n  font-size: 14px;\n  line-height: 1.4;\n  border: 0.5px solid var(--hairline-strong);\n  animation: toast-in 0.35s cubic-bezier(.25,1.4,.4,1);\n}\n@keyframes toast-in {\n  from { transform: translateY(-12px); opacity: 0; }\n  to { transform: translateY(0); opacity: 1; }\n}\n.toast .dot { width: 8px; height: 8px; border-radius: 50%; margin-top: 5px; flex: none; }\n.toast.success .dot { background: var(--green); }\n.toast.danger .dot { background: var(--red); }\n.toast.info .dot { background: var(--blue); }\n.toast .msg { flex: 1; color: var(--ink); }\n.toast .close { color: var(--ink-faint); font-size: 16px; line-height: 1; }\n\n/* ==========================================================================\n   Cards — continuous-corner, soft-shadow \"postcard\" style\n   ========================================================================== */\n\n.card {\n  background: var(--surface);\n  border-radius: var(--radius-lg);\n  box-shadow: var(--shadow-card);\n  border: 0.5px solid var(--hairline);\n  overflow: hidden;\n}\n\n.shop-card {\n  display: block;\n  background: var(--surface);\n  border-radius: var(--radius-lg);\n  box-shadow: var(--shadow-card);\n  border: 0.5px solid var(--hairline);\n  overflow: hidden;\n  margin-bottom: 14px;\n  transition: transform 0.15s ease;\n}\n.shop-card:active { transform: scale(0.98); }\n\n.shop-card .photo-wrap {\n  position: relative;\n  aspect-ratio: 16/10;\n  background: linear-gradient(135deg, var(--surface-alt), #EFE3C8);\n  overflow: hidden;\n}\n.shop-card .photo-wrap img { width: 100%; height: 100%; object-fit: cover; }\n.shop-card .photo-wrap .no-photo {\n  width: 100%; height: 100%;\n  display: flex; align-items: center; justify-content: center;\n  color: var(--mustard-dark);\n}\n.shop-card .photo-wrap .no-photo svg { width: 40px; height: 40px; opacity: 0.5; }\n\n.shutter-strip {\n  position: absolute; left: 0; right: 0; bottom: 0; height: 6px;\n  background: repeating-linear-gradient(90deg, var(--blue) 0 18px, var(--mustard) 18px 36px);\n  opacity: 0.9;\n}\n\n.badge {\n  display: inline-flex; align-items: center; gap: 4px;\n  font-size: 11.5px; font-weight: 600;\n  padding: 4px 10px;\n  border-radius: var(--radius-pill);\n}\n.badge.verified { background: var(--blue-tint); color: var(--blue-dark); }\n.badge.pending { background: var(--mustard-tint); color: var(--mustard-dark); }\n.badge.rejected { background: var(--red-tint); color: var(--red); }\n.badge.approved { background: var(--green-tint); color: var(--green); }\n\n.badge-float {\n  position: absolute; top: 10px; right: 10px;\n  backdrop-filter: blur(8px);\n  background: rgba(255,255,255,0.85);\n}\n\n.offer-marquee {\n  position: absolute; left: 0; right: 0; bottom: 6px;\n  overflow: hidden;\n  background: rgba(28,110,140,0.82);\n  color: #fff;\n  font-size: 12px;\n  font-weight: 600;\n  padding: 5px 0;\n  white-space: nowrap;\n}\n.offer-marquee span {\n  display: inline-block;\n  padding-left: 100%;\n  animation: marquee 11s linear infinite;\n}\n@keyframes marquee {\n  from { transform: translateX(0); }\n  to { transform: translateX(-100%); }\n}\n\n.shop-card .body { padding: 12px 14px 14px; }\n.shop-card .name { font-size: 16.5px; font-weight: 700; color: var(--ink); margin: 0 0 3px; }\n.shop-card .meta { font-size: 13px; color: var(--ink-soft); display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }\n.shop-card .meta .dot-sep::before { content: \"·\"; margin: 0 2px; }\n\n.stars { display: inline-flex; align-items: center; gap: 2px; color: var(--mustard-dark); }\n.stars svg { width: 14px; height: 14px; }\n.rating-count { color: var(--ink-faint); font-size: 12.5px; }\n\n/* ==========================================================================\n   Buttons — pill-shaped, iOS-style\n   ========================================================================== */\n\n.btn {\n  display: inline-flex; align-items: center; justify-content: center; gap: 6px;\n  border: none;\n  border-radius: var(--radius-pill);\n  padding: 13px 20px;\n  font-size: 15.5px;\n  font-weight: 600;\n  cursor: pointer;\n  transition: opacity 0.15s ease, transform 0.1s ease;\n  -webkit-tap-highlight-color: transparent;\n}\n.btn:active { transform: scale(0.97); opacity: 0.9; }\n.btn.block { width: 100%; }\n.btn.small { padding: 8px 14px; font-size: 13.5px; }\n\n.btn-primary { background: var(--blue); color: #fff; }\n.btn-primary:active { background: var(--blue-dark); }\n\n.btn-pink { background: var(--pink); color: #fff; }\n.btn-mustard { background: var(--mustard); color: #fff; }\n\n.btn-secondary { background: rgba(28,110,140,0.1); color: var(--blue-dark); }\n.btn-ghost { background: transparent; color: var(--blue); }\n.btn-outline { background: transparent; color: var(--ink); border: 1.3px solid var(--hairline-strong); }\n\n.btn-danger { background: var(--red-tint); color: var(--red); }\n.btn-success { background: var(--green-tint); color: var(--green); }\n\n.btn-icon {\n  width: 40px; height: 40px; border-radius: 50%; padding: 0;\n  background: rgba(43,34,24,0.05); color: var(--ink);\n}\n\n/* ==========================================================================\n   Forms — iOS grouped-list style inputs\n   ========================================================================== */\n\n.form-group { margin-bottom: 16px; }\n.form-label {\n  display: block;\n  font-size: 13px;\n  font-weight: 600;\n  color: var(--ink-soft);\n  margin-bottom: 6px;\n  padding-left: 2px;\n}\n.form-control {\n  width: 100%;\n  font-family: inherit;\n  font-size: 16px;\n  padding: 13px 14px;\n  border-radius: var(--radius-md);\n  border: 1px solid var(--hairline-strong);\n  background: var(--surface);\n  color: var(--ink);\n  outline: none;\n  transition: border-color 0.15s ease, box-shadow 0.15s ease;\n}\n.form-control:focus {\n  border-color: var(--blue);\n  box-shadow: 0 0 0 4px var(--blue-tint);\n}\ntextarea.form-control { resize: vertical; min-height: 100px; }\n.form-hint { font-size: 12.5px; color: var(--ink-faint); margin-top: 5px; padding-left: 2px; }\n.form-hint.char-count { text-align: right; }\n\nselect.form-control {\n  appearance: none;\n  -webkit-appearance: none;\n  background-image: url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='14' height='14' viewBox='0 0 24 24' fill='none' stroke='%236E6157' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'><polyline points='6 9 12 15 18 9'/></svg>\");\n  background-repeat: no-repeat;\n  background-position: right 14px center;\n  padding-right: 36px;\n}\n\n.file-drop {\n  border: 1.5px dashed var(--hairline-strong);\n  border-radius: var(--radius-md);\n  padding: 22px 14px;\n  text-align: center;\n  color: var(--ink-soft);\n  font-size: 14px;\n  background: var(--surface-alt);\n  cursor: pointer;\n}\n.file-drop svg { width: 26px; height: 26px; margin-bottom: 6px; color: var(--blue); }\n.file-drop input[type=\"file\"] { display: none; }\n\n.thumb-row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }\n.thumb {\n  position: relative; width: 64px; height: 64px;\n  border-radius: var(--radius-sm); overflow: hidden;\n  border: 0.5px solid var(--hairline-strong);\n}\n.thumb img { width: 100%; height: 100%; object-fit: cover; }\n.thumb .remove-x {\n  position: absolute; top: 2px; right: 2px;\n  width: 18px; height: 18px; border-radius: 50%;\n  background: rgba(0,0,0,0.6); color: #fff;\n  display: flex; align-items: center; justify-content: center;\n  font-size: 11px;\n}\n\n/* ---- Segmented control (iOS style) ---- */\n.segmented {\n  display: flex;\n  background: rgba(43,34,24,0.06);\n  border-radius: var(--radius-sm);\n  padding: 3px;\n  gap: 2px;\n}\n.segmented input { display: none; }\n.segmented label {\n  flex: 1;\n  text-align: center;\n  font-size: 13.5px;\n  font-weight: 600;\n  padding: 8px 6px;\n  border-radius: 9px;\n  color: var(--ink-soft);\n  cursor: pointer;\n  transition: all 0.15s ease;\n}\n.segmented input:checked + label {\n  background: var(--surface);\n  color: var(--blue-dark);\n  box-shadow: var(--shadow-card);\n}\n\n/* ---- Horizontal scrolling chip filter ---- */\n.chip-scroll {\n  display: flex;\n  gap: 8px;\n  overflow-x: auto;\n  padding: 2px 16px 12px;\n  -webkit-overflow-scrolling: touch;\n  scrollbar-width: none;\n}\n.chip-scroll::-webkit-scrollbar { display: none; }\n.chip {\n  flex: none;\n  padding: 8px 16px;\n  border-radius: var(--radius-pill);\n  background: var(--surface);\n  border: 1px solid var(--hairline-strong);\n  font-size: 13.5px;\n  font-weight: 600;\n  color: var(--ink-soft);\n  white-space: nowrap;\n}\n.chip.active { background: var(--blue); color: #fff; border-color: var(--blue); }\n\n.search-bar {\n  display: flex;\n  align-items: center;\n  gap: 8px;\n  background: rgba(43,34,24,0.06);\n  border-radius: var(--radius-pill);\n  padding: 10px 14px;\n  margin: 0 16px 12px;\n}\n.search-bar svg { width: 18px; height: 18px; color: var(--ink-faint); flex: none; }\n.search-bar input {\n  border: none; background: transparent; outline: none;\n  font-size: 15px; width: 100%; color: var(--ink); font-family: inherit;\n}\n\n/* ==========================================================================\n   List rows — iOS grouped table view\n   ========================================================================== */\n\n.list-group {\n  background: var(--surface);\n  border-radius: var(--radius-md);\n  overflow: hidden;\n  border: 0.5px solid var(--hairline);\n  box-shadow: var(--shadow-card);\n}\n.list-row {\n  display: flex;\n  align-items: center;\n  gap: 12px;\n  padding: 14px;\n  border-bottom: 0.5px solid var(--hairline);\n}\n.list-row:last-child { border-bottom: none; }\n.list-row .chevron { color: var(--ink-faint); flex: none; }\n.list-row .row-icon {\n  width: 34px; height: 34px; border-radius: 9px;\n  display: flex; align-items: center; justify-content: center; flex: none;\n}\n.list-row .row-title { font-weight: 600; font-size: 15px; }\n.list-row .row-sub { font-size: 12.5px; color: var(--ink-soft); }\n.list-row .row-main { flex: 1; min-width: 0; }\n\n/* ==========================================================================\n   Accordion (area sections on the Locate page)\n   ========================================================================== */\n\n.area-accordion { margin: 0 16px 16px; }\n.area-summary {\n  display: flex; align-items: center; justify-content: space-between;\n  padding: 14px 16px;\n  background: var(--surface);\n  border-radius: var(--radius-md);\n  border: 0.5px solid var(--hairline);\n  cursor: pointer;\n  list-style: none;\n}\n.area-summary::-webkit-details-marker { display: none; }\n.area-summary .area-name { font-weight: 700; font-size: 15.5px; }\n.area-summary .area-count {\n  font-size: 12px; font-weight: 600; color: var(--blue-dark);\n  background: var(--blue-tint); padding: 2px 9px; border-radius: var(--radius-pill);\n}\ndetails[open] .area-summary { border-bottom-left-radius: 0; border-bottom-right-radius: 0; }\n.area-body { padding: 12px; background: var(--surface-alt); border-radius: 0 0 var(--radius-md) var(--radius-md); }\n.area-body .empty-note { font-size: 13px; color: var(--ink-faint); padding: 6px 4px 10px; }\n\n/* ==========================================================================\n   Hero (Home page)\n   ========================================================================== */\n\n.hero {\n  margin: 8px 16px 4px;\n  border-radius: var(--radius-lg);\n  padding: 28px 22px 24px;\n  background:\n    radial-gradient(120% 140% at 100% 0%, rgba(227,164,49,0.35), transparent 60%),\n    radial-gradient(120% 140% at 0% 100%, rgba(217,82,122,0.28), transparent 55%),\n    linear-gradient(160deg, var(--blue) 0%, var(--blue-dark) 100%);\n  color: #fff;\n  position: relative;\n  overflow: hidden;\n}\n.hero h1 {\n  font-family: var(--font-display);\n  font-size: 30px;\n  line-height: 1.15;\n  margin: 0 0 8px;\n}\n.hero p { margin: 0 0 18px; font-size: 15px; opacity: 0.92; max-width: 42ch; }\n.hero .hero-actions { display: flex; gap: 10px; flex-wrap: wrap; }\n.hero .btn-primary { background: #fff; color: var(--blue-dark); }\n.hero .btn-outline { border-color: rgba(255,255,255,0.5); color: #fff; }\n\n.stats-row {\n  display: grid;\n  grid-template-columns: repeat(2, 1fr);\n  gap: 10px;\n  margin: 14px 16px 4px;\n}\n.stat-card {\n  background: var(--surface);\n  border-radius: var(--radius-md);\n  padding: 14px 16px;\n  border: 0.5px solid var(--hairline);\n  box-shadow: var(--shadow-card);\n}\n.stat-card .num { font-size: 24px; font-weight: 800; color: var(--blue-dark); font-family: var(--font-display); }\n.stat-card .label { font-size: 12.5px; color: var(--ink-soft); margin-top: 2px; }\n\n.horizontal-scroll {\n  display: flex; gap: 12px; overflow-x: auto;\n  padding: 2px 16px 8px;\n  scrollbar-width: none;\n}\n.horizontal-scroll::-webkit-scrollbar { display: none; }\n.horizontal-scroll .shop-card { flex: none; width: 240px; margin-bottom: 0; }\n\n/* ==========================================================================\n   Shop detail page\n   ========================================================================== */\n\n.carousel {\n  position: relative;\n  aspect-ratio: 4/3;\n  background: var(--surface-alt);\n  overflow: hidden;\n}\n.carousel-track {\n  display: flex;\n  height: 100%;\n  overflow-x: auto;\n  scroll-snap-type: x mandatory;\n  scrollbar-width: none;\n}\n.carousel-track::-webkit-scrollbar { display: none; }\n.carousel-track img {\n  flex: none; width: 100%; height: 100%;\n  object-fit: cover; scroll-snap-align: center;\n}\n.carousel-dots {\n  position: absolute; bottom: 40px; left: 0; right: 0;\n  display: flex; justify-content: center; gap: 6px;\n}\n.carousel-dots span {\n  width: 6px; height: 6px; border-radius: 50%;\n  background: rgba(255,255,255,0.55);\n}\n.carousel-dots span.active { background: #fff; }\n.carousel .no-photo {\n  width: 100%; height: 100%;\n  display: flex; align-items: center; justify-content: center;\n  color: var(--mustard-dark);\n}\n.carousel .no-photo svg { width: 56px; height: 56px; opacity: 0.5; }\n\n.detail-header { padding: 16px; }\n.detail-header .title-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }\n.detail-header h1 { font-family: var(--font-display); font-size: 24px; margin: 0 0 4px; }\n.detail-header .cat-area { color: var(--ink-soft); font-size: 14px; margin: 0 0 10px; }\n\n.action-row { display: flex; gap: 10px; padding: 0 16px 16px; }\n.action-row .btn { flex: 1; }\n\n.info-card { margin: 0 16px 16px; padding: 16px; }\n.info-card .row { display: flex; gap: 10px; align-items: flex-start; padding: 8px 0; }\n.info-card .row svg { width: 18px; height: 18px; color: var(--blue); flex: none; margin-top: 1px; }\n.info-card .row + .row { border-top: 0.5px solid var(--hairline); }\n\n.rating-widget {\n  display: flex; flex-direction: column; align-items: center;\n  gap: 8px; padding: 20px 16px; margin: 0 16px 16px;\n}\n.rating-widget .big-star-row { display: flex; gap: 6px; }\n.rating-widget .big-star-row button {\n  background: none; border: none; padding: 0; cursor: pointer;\n}\n.rating-widget .big-star-row svg { width: 32px; height: 32px; color: var(--ink-faint); }\n.rating-widget .big-star-row svg.filled { color: var(--mustard); }\n.rating-widget .avg { font-size: 14px; color: var(--ink-soft); }\n\n.feedback-item {\n  padding: 12px 0;\n  border-bottom: 0.5px solid var(--hairline);\n}\n.feedback-item:last-child { border-bottom: none; }\n.feedback-item .author { font-weight: 700; font-size: 13.5px; color: var(--blue-dark); }\n.feedback-item .msg { font-size: 14.5px; margin-top: 3px; color: var(--ink); }\n.feedback-item .date { font-size: 11.5px; color: var(--ink-faint); margin-top: 3px; }\n\n/* ==========================================================================\n   Misc utility\n   ========================================================================== */\n\n.empty-state {\n  text-align: center;\n  padding: 60px 24px;\n  color: var(--ink-soft);\n}\n.empty-state svg { width: 52px; height: 52px; color: var(--ink-faint); margin-bottom: 12px; }\n.empty-state h3 { margin: 0 0 6px; color: var(--ink); font-size: 17px; }\n.empty-state p { margin: 0; font-size: 14px; }\n\n.divider { height: 0.5px; background: var(--hairline); margin: 16px 0; border: none; }\n\n.center-page {\n  min-height: calc(100vh - var(--nav-h) - var(--tabbar-h));\n  display: flex; align-items: center; justify-content: center;\n  padding: 24px;\n}\n.auth-card { width: 100%; max-width: 380px; padding: 28px 24px; text-align: center; }\n.auth-card .icon-badge {\n  width: 56px; height: 56px; border-radius: 16px;\n  background: var(--blue-tint); color: var(--blue-dark);\n  display: flex; align-items: center; justify-content: center;\n  margin: 0 auto 14px;\n}\n.auth-card h1 { font-family: var(--font-display); font-size: 22px; margin: 6px 0 4px; }\n.auth-card .sub { color: var(--ink-soft); font-size: 13.5px; margin-bottom: 18px; }\n.auth-card form { text-align: left; }\n.auth-switch { margin-top: 16px; font-size: 13.5px; color: var(--ink-soft); }\n.auth-switch a { color: var(--blue); font-weight: 600; }\n\n.footer-note {\n  text-align: center;\n  font-size: 12px;\n  color: var(--ink-faint);\n  padding: 20px 16px 8px;\n}\n\n/* Admin */\n.admin-toolbar { display: flex; gap: 8px; padding: 0 16px 12px; overflow-x: auto; }\n.admin-shop-row { padding: 14px; }\n.admin-shop-row .top { display: flex; justify-content: space-between; gap: 10px; align-items: flex-start; }\n.admin-shop-row .actions { display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap; }\n.admin-shop-row .actions form { display: contents; }\n.reason-box { margin-top: 8px; }\n\n@media (min-width: 640px) {\n  .app-content { padding-left: 0; padding-right: 0; }\n  .stats-row { grid-template-columns: repeat(4, 1fr); }\n}\n\n</style>\n</head>\n<body>\n\n  <nav class=\"ios-navbar\">\n    <a href=\"{{ url_for('home') }}\" class=\"brand\">\n      <span class=\"pin\">{{ icons.icon('map-pin', 'brand-pin-icon') }}</span>\n      LocatePondy\n    </a>\n    <div class=\"nav-actions\">\n      {% if current_user.is_authenticated and current_user.is_admin %}\n        <a href=\"{{ url_for('admin_dashboard') }}\" class=\"nav-icon-btn\" aria-label=\"Admin dashboard\">{{ icons.icon('shield', 'icon-20') }}</a>\n      {% elif current_user.is_authenticated %}\n        <a href=\"{{ url_for('my_shops') }}\" class=\"nav-icon-btn\" aria-label=\"My shops\">{{ icons.icon('user', 'icon-20') }}</a>\n      {% else %}\n        <a href=\"{{ url_for('login') }}\" class=\"nav-icon-btn\" aria-label=\"Log in\">{{ icons.icon('log-in', 'icon-20') }}</a>\n      {% endif %}\n    </div>\n  </nav>\n\n  <div class=\"toast-stack\">\n    {% with messages = get_flashed_messages(with_categories=true) %}\n      {% if messages %}\n        {% for category, message in messages %}\n          <div class=\"toast {{ 'danger' if category == 'danger' else category }}\">\n            <span class=\"dot\"></span>\n            <span class=\"msg\">{{ message }}</span>\n            <span class=\"close\">{{ icons.icon('x', 'icon-14') }}</span>\n          </div>\n        {% endfor %}\n      {% endif %}\n    {% endwith %}\n  </div>\n\n  <main class=\"app-content\">\n    {% block content %}{% endblock %}\n  </main>\n\n  <nav class=\"ios-tabbar\">\n    <a href=\"{{ url_for('home') }}\" class=\"tab-item {{ 'active' if request.endpoint == 'home' }}\">\n      {{ icons.icon('home') }}<span>Home</span>\n    </a>\n    <a href=\"{{ url_for('locate') }}\" class=\"tab-item {{ 'active' if request.endpoint == 'locate' }}\">\n      {{ icons.icon('compass') }}<span>Locate</span>\n    </a>\n\n    {% if current_user.is_authenticated and not current_user.is_admin %}\n      <a href=\"{{ url_for('add_shop') }}\" class=\"tab-item {{ 'active' if request.endpoint == 'add_shop' }}\">\n        {{ icons.icon('plus-circle') }}<span>Add Shop</span>\n      </a>\n      <a href=\"{{ url_for('my_shops') }}\" class=\"tab-item {{ 'active' if request.endpoint == 'my_shops' }}\">\n        {{ icons.icon('grid') }}<span>My Shops</span>\n      </a>\n      <a href=\"{{ url_for('logout') }}\" class=\"tab-item\">\n        {{ icons.icon('log-out') }}<span>Logout</span>\n      </a>\n    {% elif current_user.is_authenticated and current_user.is_admin %}\n      <a href=\"{{ url_for('admin_dashboard') }}\" class=\"tab-item {{ 'active' if request.endpoint and request.endpoint.startswith('admin_') }}\">\n        {{ icons.icon('shield') }}<span>Admin</span>\n      </a>\n      <a href=\"{{ url_for('about') }}\" class=\"tab-item {{ 'active' if request.endpoint == 'about' }}\">\n        {{ icons.icon('info') }}<span>About</span>\n      </a>\n      <a href=\"{{ url_for('admin_logout') }}\" class=\"tab-item\">\n        {{ icons.icon('log-out') }}<span>Logout</span>\n      </a>\n    {% else %}\n      <a href=\"{{ url_for('about') }}\" class=\"tab-item {{ 'active' if request.endpoint == 'about' }}\">\n        {{ icons.icon('info') }}<span>About</span>\n      </a>\n      <a href=\"{{ url_for('login') }}\" class=\"tab-item {{ 'active' if request.endpoint == 'login' }}\">\n        {{ icons.icon('log-in') }}<span>Log In</span>\n      </a>\n    {% endif %}\n  </nav>\n\n  <script>\n// LOCATEPONDY — small interaction layer for the iOS-style UI\ndocument.addEventListener(\"DOMContentLoaded\", function () {\n\n  /* ---- Auto-dismiss toasts ---- */\n  document.querySelectorAll(\".toast\").forEach(function (toast) {\n    var closeBtn = toast.querySelector(\".close\");\n    var timer = setTimeout(function () { dismiss(toast); }, 4500);\n    if (closeBtn) {\n      closeBtn.addEventListener(\"click\", function () {\n        clearTimeout(timer);\n        dismiss(toast);\n      });\n    }\n  });\n  function dismiss(el) {\n    el.style.transition = \"opacity .25s ease, transform .25s ease\";\n    el.style.opacity = \"0\";\n    el.style.transform = \"translateY(-10px)\";\n    setTimeout(function () { el.remove(); }, 250);\n  }\n\n  /* ---- Character counters (e.g. shop name field) ---- */\n  document.querySelectorAll(\"[data-char-count-for]\").forEach(function (counter) {\n    var input = document.getElementById(counter.getAttribute(\"data-char-count-for\"));\n    if (!input) return;\n    var max = parseInt(counter.getAttribute(\"data-max\"), 10) || 0;\n    function update() {\n      var len = input.value.length;\n      counter.textContent = len + \" / \" + max;\n      counter.style.color = len > max ? \"var(--red)\" : \"var(--ink-faint)\";\n    }\n    input.addEventListener(\"input\", update);\n    update();\n  });\n\n  /* ---- Photo upload preview + count limit ---- */\n  document.querySelectorAll(\"[data-photo-input]\").forEach(function (input) {\n    var max = parseInt(input.getAttribute(\"data-max-photos\"), 10) || 5;\n    var previewRow = document.querySelector(input.getAttribute(\"data-preview-target\"));\n    var dropLabel = document.querySelector(input.getAttribute(\"data-drop-label\"));\n\n    input.addEventListener(\"change\", function () {\n      var files = Array.from(input.files || []);\n      if (files.length > max) {\n        alert(\"You can select up to \" + max + \" photos.\");\n        input.value = \"\";\n        if (previewRow) previewRow.innerHTML = \"\";\n        return;\n      }\n      if (previewRow) {\n        previewRow.innerHTML = \"\";\n        files.forEach(function (file) {\n          var reader = new FileReader();\n          reader.onload = function (e) {\n            var thumb = document.createElement(\"div\");\n            thumb.className = \"thumb\";\n            var img = document.createElement(\"img\");\n            img.src = e.target.result;\n            thumb.appendChild(img);\n            previewRow.appendChild(thumb);\n          };\n          reader.readAsDataURL(file);\n        });\n      }\n      if (dropLabel) {\n        dropLabel.textContent = files.length\n          ? files.length + \" photo\" + (files.length > 1 ? \"s\" : \"\") + \" selected\"\n          : \"Tap to choose photos\";\n      }\n    });\n  });\n\n  /* ---- Remove-existing-image checkboxes (admin edit) fade the thumb ---- */\n  document.querySelectorAll(\"[data-remove-toggle]\").forEach(function (checkbox) {\n    checkbox.addEventListener(\"change\", function () {\n      var thumb = checkbox.closest(\".thumb\");\n      if (thumb) thumb.style.opacity = checkbox.checked ? \"0.35\" : \"1\";\n    });\n  });\n\n  /* ---- Interactive star rating widget ---- */\n  document.querySelectorAll(\"[data-star-widget]\").forEach(function (widget) {\n    var input = widget.querySelector(\"input[name='stars']\");\n    var stars = Array.from(widget.querySelectorAll(\"button[data-star]\"));\n    function paint(value) {\n      stars.forEach(function (s) {\n        var v = parseInt(s.getAttribute(\"data-star\"), 10);\n        s.querySelector(\"svg\").classList.toggle(\"filled\", v <= value);\n      });\n    }\n    stars.forEach(function (s) {\n      s.addEventListener(\"click\", function () {\n        var v = parseInt(s.getAttribute(\"data-star\"), 10);\n        if (input) input.value = v;\n        paint(v);\n      });\n    });\n  });\n\n  /* ---- Carousel dot indicator sync ---- */\n  document.querySelectorAll(\"[data-carousel]\").forEach(function (carousel) {\n    var track = carousel.querySelector(\".carousel-track\");\n    var dots = Array.from(carousel.querySelectorAll(\".carousel-dots span\"));\n    if (!track || dots.length < 2) return;\n    track.addEventListener(\"scroll\", function () {\n      var index = Math.round(track.scrollLeft / track.clientWidth);\n      dots.forEach(function (d, i) { d.classList.toggle(\"active\", i === index); });\n    });\n  });\n\n  /* ---- Live search / filter submit on change (Locate page) ---- */\n  document.querySelectorAll(\"[data-auto-submit]\").forEach(function (el) {\n    el.addEventListener(\"change\", function () { el.form.submit(); });\n  });\n});\n\n</script>\n  {% block scripts %}{% endblock %}\n</body>\n</html>\n",
  "_icons.html": "{% macro icon(name, cls='') %}\n{%- if name == 'home' -%}\n<svg class=\"{{ cls }}\" viewBox=\"0 0 24 24\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M3 11.5 12 4l9 7.5\"/><path d=\"M5.5 9.5V19a1 1 0 0 0 1 1H9a1 1 0 0 0 1-1v-4a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v4a1 1 0 0 0 1 1h2.5a1 1 0 0 0 1-1V9.5\"/></svg>\n{%- elif name == 'map-pin' -%}\n<svg class=\"{{ cls }}\" viewBox=\"0 0 24 24\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M12 21s-7-6.1-7-11.5A7 7 0 0 1 19 9.5C19 14.9 12 21 12 21Z\"/><circle cx=\"12\" cy=\"9.5\" r=\"2.4\"/></svg>\n{%- elif name == 'plus-circle' -%}\n<svg class=\"{{ cls }}\" viewBox=\"0 0 24 24\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><circle cx=\"12\" cy=\"12\" r=\"9.25\"/><path d=\"M12 8v8M8 12h8\"/></svg>\n{%- elif name == 'user' -%}\n<svg class=\"{{ cls }}\" viewBox=\"0 0 24 24\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><circle cx=\"12\" cy=\"8\" r=\"3.5\"/><path d=\"M4.5 20c1.4-3.7 4.2-5.5 7.5-5.5s6.1 1.8 7.5 5.5\"/></svg>\n{%- elif name == 'shield' -%}\n<svg class=\"{{ cls }}\" viewBox=\"0 0 24 24\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M12 3.5 19 6v5.5c0 4.5-3 7.7-7 9.0-4-1.3-7-4.5-7-9V6l7-2.5Z\"/><path d=\"m9 12 2 2 4-4.2\"/></svg>\n{%- elif name == 'log-in' -%}\n<svg class=\"{{ cls }}\" viewBox=\"0 0 24 24\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M11 16l4-4-4-4\"/><path d=\"M15 12H3\"/><path d=\"M9 19c-3.3 0-6-2.7-6-6v-2c0-3.3 2.7-6 6-6\"/></svg>\n{%- elif name == 'log-out' -%}\n<svg class=\"{{ cls }}\" viewBox=\"0 0 24 24\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M13 16l4-4-4-4\"/><path d=\"M17 12H7\"/><path d=\"M11 19c3.3 0 6-2.7 6-6v-2c0-3.3-2.7-6-6-6\"/></svg>\n{%- elif name == 'search' -%}\n<svg class=\"{{ cls }}\" viewBox=\"0 0 24 24\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><circle cx=\"11\" cy=\"11\" r=\"7\"/><path d=\"m21 21-4.3-4.3\"/></svg>\n{%- elif name == 'camera' -%}\n<svg class=\"{{ cls }}\" viewBox=\"0 0 24 24\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M4 8.5A1.5 1.5 0 0 1 5.5 7h2l1.2-1.8A1.5 1.5 0 0 1 10 4.5h4a1.5 1.5 0 0 1 1.3.7L16.5 7h2A1.5 1.5 0 0 1 20 8.5v9A1.5 1.5 0 0 1 18.5 19h-13A1.5 1.5 0 0 1 4 17.5v-9Z\"/><circle cx=\"12\" cy=\"13\" r=\"3.3\"/></svg>\n{%- elif name == 'phone' -%}\n<svg class=\"{{ cls }}\" viewBox=\"0 0 24 24\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M6.5 4h2.7l1.3 4-2 1.4a11.6 11.6 0 0 0 5.1 5.1l1.4-2 4 1.3v2.7a1.5 1.5 0 0 1-1.6 1.5A15.5 15.5 0 0 1 5 5.6 1.5 1.5 0 0 1 6.5 4Z\"/></svg>\n{%- elif name == 'map' -%}\n<svg class=\"{{ cls }}\" viewBox=\"0 0 24 24\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M9 4 4 6.2v13.3L9 17l6 3.5 5-2.2V4.9L15 7.5 9 4Z\"/><path d=\"M9 4v13M15 7.5v13\"/></svg>\n{%- elif name == 'chevron-right' -%}\n<svg class=\"{{ cls }}\" viewBox=\"0 0 24 24\" stroke=\"currentColor\" stroke-width=\"2.2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"m9 6 6 6-6 6\"/></svg>\n{%- elif name == 'chevron-down' -%}\n<svg class=\"{{ cls }}\" viewBox=\"0 0 24 24\" stroke=\"currentColor\" stroke-width=\"2.2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"m6 9 6 6 6-6\"/></svg>\n{%- elif name == 'star' -%}\n<svg class=\"{{ cls }}\" viewBox=\"0 0 24 24\" fill=\"currentColor\"><path d=\"M12 3.8l2.4 5 5.5.7-4 3.9.9 5.5-4.8-2.6-4.8 2.6.9-5.5-4-3.9 5.5-.7Z\"/></svg>\n{%- elif name == 'star-outline' -%}\n<svg class=\"{{ cls }}\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.6\" stroke-linejoin=\"round\"><path d=\"M12 3.8l2.4 5 5.5.7-4 3.9.9 5.5-4.8-2.6-4.8 2.6.9-5.5-4-3.9 5.5-.7Z\"/></svg>\n{%- elif name == 'photo' -%}\n<svg class=\"{{ cls }}\" viewBox=\"0 0 24 24\" stroke=\"currentColor\" stroke-width=\"1.6\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><rect x=\"3.5\" y=\"4.5\" width=\"17\" height=\"15\" rx=\"2.5\"/><circle cx=\"8.5\" cy=\"9.5\" r=\"1.6\"/><path d=\"m4.5 17 4.7-4.7a2 2 0 0 1 2.8 0L15 15.3l1.2-1.2a2 2 0 0 1 2.8 0l1.5 1.5\"/></svg>\n{%- elif name == 'check' -%}\n<svg class=\"{{ cls }}\" viewBox=\"0 0 24 24\" stroke=\"currentColor\" stroke-width=\"2.2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"m5 13 4.5 4.5L19 7\"/></svg>\n{%- elif name == 'x' -%}\n<svg class=\"{{ cls }}\" viewBox=\"0 0 24 24\" stroke=\"currentColor\" stroke-width=\"2.2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"m6 6 12 12M18 6 6 18\"/></svg>\n{%- elif name == 'pencil' -%}\n<svg class=\"{{ cls }}\" viewBox=\"0 0 24 24\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M4 20l.9-3.9L16.6 4.4a1.7 1.7 0 0 1 2.4 0l.6.6a1.7 1.7 0 0 1 0 2.4L7.9 19.1 4 20Z\"/></svg>\n{%- elif name == 'trash' -%}\n<svg class=\"{{ cls }}\" viewBox=\"0 0 24 24\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M5 7h14M9.5 7V5.2c0-.7.5-1.2 1.2-1.2h2.6c.7 0 1.2.5 1.2 1.2V7M7 7l1 12.3c.05.9.8 1.7 1.7 1.7h4.6c.9 0 1.65-.8 1.7-1.7L17 7\"/></svg>\n{%- elif name == 'compass' -%}\n<svg class=\"{{ cls }}\" viewBox=\"0 0 24 24\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><circle cx=\"12\" cy=\"12\" r=\"9.25\"/><path d=\"m14.8 9.2-1.6 4.4-4.4 1.6 1.6-4.4 4.4-1.6Z\"/></svg>\n{%- elif name == 'sparkles' -%}\n<svg class=\"{{ cls }}\" viewBox=\"0 0 24 24\" stroke=\"currentColor\" stroke-width=\"1.6\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M11 3v3M11 15v3M4 9h3M15 9h3M6 6l1.6 1.6M14.4 6.6 16 5M6 12l1.6-1.6M13 13l3 3\"/><path d=\"M18.5 15.5v2M17.5 16.5h2\"/></svg>\n{%- elif name == 'info' -%}\n<svg class=\"{{ cls }}\" viewBox=\"0 0 24 24\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><circle cx=\"12\" cy=\"12\" r=\"9.25\"/><path d=\"M12 11v5.5\"/><circle cx=\"12\" cy=\"8.2\" r=\"0.9\" fill=\"currentColor\" stroke=\"none\"/></svg>\n{%- elif name == 'grid' -%}\n<svg class=\"{{ cls }}\" viewBox=\"0 0 24 24\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><rect x=\"3.5\" y=\"3.5\" width=\"7\" height=\"7\" rx=\"1.5\"/><rect x=\"13.5\" y=\"3.5\" width=\"7\" height=\"7\" rx=\"1.5\"/><rect x=\"3.5\" y=\"13.5\" width=\"7\" height=\"7\" rx=\"1.5\"/><rect x=\"13.5\" y=\"13.5\" width=\"7\" height=\"7\" rx=\"1.5\"/></svg>\n{%- endif -%}\n{% endmacro %}\n",
  "_shop_card.html": "{% import \"_icons.html\" as icons %}\n<a href=\"{{ url_for('shop_detail', shop_id=shop.id) }}\" class=\"shop-card\">\n  <div class=\"photo-wrap\">\n    {% if shop.cover_image %}\n      <img src=\"{{ url_for('static', filename='uploads/' ~ shop.cover_image) }}\" alt=\"{{ shop.name }}\">\n    {% else %}\n      <div class=\"no-photo\">{{ icons.icon('camera', 'icon-24') }}</div>\n    {% endif %}\n\n    {% if show_status is defined and show_status %}\n      <span class=\"badge {{ shop.status }} badge-float\">{{ shop.status|capitalize }}</span>\n    {% elif shop.is_verified %}\n      <span class=\"badge verified badge-float\">{{ icons.icon('check', 'icon-14') }} Verified</span>\n    {% endif %}\n\n    {% if shop.offer_text %}\n      <div class=\"offer-marquee\"><span>🎉 {{ shop.offer_text }} &nbsp;&nbsp;&nbsp; 🎉 {{ shop.offer_text }}</span></div>\n    {% endif %}\n    <div class=\"shutter-strip\"></div>\n  </div>\n  <div class=\"body\">\n    <h3 class=\"name\">{{ shop.name }}</h3>\n    <div class=\"meta\">\n      <span>{{ shop.category }}</span>\n      <span class=\"dot-sep\">{{ shop.area }}</span>\n    </div>\n    <div class=\"meta\" style=\"margin-top:6px;\">\n      {% if shop.rating_count %}\n        <span class=\"stars\">\n          {% for i in range(1,6) %}\n            {{ icons.icon('star' if i <= shop.average_rating|round(0,'floor') else 'star-outline') }}\n          {% endfor %}\n        </span>\n        <span class=\"rating-count\">{{ shop.average_rating }} ({{ shop.rating_count }})</span>\n      {% else %}\n        <span class=\"rating-count\">No ratings yet</span>\n      {% endif %}\n    </div>\n  </div>\n</a>\n",
  "home.html": "{% extends \"base.html\" %}\n{% import \"_icons.html\" as icons %}\n{% block title %}LocatePondy — Discover Pondicherry's Food Shops{% endblock %}\n\n{% block content %}\n\n<div class=\"hero\">\n  <h1>Every good meal in<br>Pondicherry, mapped.</h1>\n  <p>Discover verified food shops across every area of White Town and beyond — reviewed, rated, and organized by neighborhood.</p>\n  <div class=\"hero-actions\">\n    <a href=\"{{ url_for('locate') }}\" class=\"btn btn-primary\">{{ icons.icon('compass', 'icon-18') }} Start exploring</a>\n    {% if not current_user.is_authenticated %}\n      <a href=\"{{ url_for('register') }}\" class=\"btn btn-outline\">Create account</a>\n    {% endif %}\n  </div>\n</div>\n\n<div class=\"stats-row\">\n  <div class=\"stat-card\">\n    <div class=\"num\">{{ total_shops }}</div>\n    <div class=\"label\">Verified shops</div>\n  </div>\n  <div class=\"stat-card\">\n    <div class=\"num\">{{ total_areas_used }}</div>\n    <div class=\"label\">Areas covered</div>\n  </div>\n  <div class=\"stat-card\">\n    <div class=\"num\">{{ PONDY_AREAS|length }}</div>\n    <div class=\"label\">Total areas</div>\n  </div>\n  <div class=\"stat-card\">\n    <div class=\"num\">{{ SHOP_CATEGORIES|length }}</div>\n    <div class=\"label\">Categories</div>\n  </div>\n</div>\n\n{% if top_shops %}\n<div class=\"section\" style=\"padding-bottom:4px;\">\n  <div class=\"section-title\">Most rated</div>\n</div>\n<div class=\"horizontal-scroll\">\n  {% for shop in top_shops %}\n    {% include \"_shop_card.html\" %}\n  {% endfor %}\n</div>\n{% endif %}\n\n{% if recent_shops %}\n<div class=\"section\" style=\"padding-bottom:4px;\">\n  <div class=\"section-title\">Newest listings</div>\n</div>\n<div class=\"horizontal-scroll\">\n  {% for shop in recent_shops %}\n    {% include \"_shop_card.html\" %}\n  {% endfor %}\n</div>\n{% endif %}\n\n{% if not top_shops and not recent_shops %}\n<div class=\"empty-state\">\n  {{ icons.icon('sparkles', 'icon-28') }}\n  <h3>No shops listed yet</h3>\n  <p>Be the first to add a verified shop to LocatePondy.</p>\n</div>\n{% endif %}\n\n<p class=\"footer-note\">🇫🇷 White Town · Heritage Town · Auroville & every corner of Puducherry — © {{ current_year }} LocatePondy</p>\n\n{% endblock %}\n",
  "about.html": "{% extends \"base.html\" %}\n{% import \"_icons.html\" as icons %}\n{% block title %}About — LocatePondy{% endblock %}\n\n{% block content %}\n<div class=\"large-title\">\n  <h1>About</h1>\n  <p>Why LocatePondy exists, and how it works.</p>\n</div>\n\n<div class=\"section\">\n  <div class=\"card\" style=\"padding:18px;\">\n    <p style=\"margin:0 0 14px; font-size:15px; line-height:1.6; color:var(--ink);\">\n      LocatePondy is a community directory of food shops across Puducherry — from the\n      whitewashed lanes of White Town to the quiet backstreets of Ozhukarai. Every listing\n      is organized by area, so you can explore your own neighborhood or a new one, one\n      street at a time.\n    </p>\n  </div>\n</div>\n\n<div class=\"section\" style=\"padding-top:0;\">\n  <div class=\"section-title\">How it works</div>\n  <div class=\"list-group\">\n    <div class=\"list-row\">\n      <div class=\"row-icon\" style=\"background:var(--blue-tint); color:var(--blue-dark);\">{{ icons.icon('plus-circle', 'icon-18') }}</div>\n      <div class=\"row-main\">\n        <div class=\"row-title\">Anyone can submit a shop</div>\n        <div class=\"row-sub\">Add photos, a description, phone number and location.</div>\n      </div>\n    </div>\n    <div class=\"list-row\">\n      <div class=\"row-icon\" style=\"background:var(--mustard-tint); color:var(--mustard-dark);\">{{ icons.icon('shield', 'icon-18') }}</div>\n      <div class=\"row-main\">\n        <div class=\"row-title\">Every listing is verified</div>\n        <div class=\"row-sub\">Our admin reviews new shops before they go public.</div>\n      </div>\n    </div>\n    <div class=\"list-row\">\n      <div class=\"row-icon\" style=\"background:var(--pink-tint); color:var(--pink-dark);\">{{ icons.icon('star', 'icon-18') }}</div>\n      <div class=\"row-main\">\n        <div class=\"row-title\">Rate and review</div>\n        <div class=\"row-sub\">Leave a star rating and a note for others exploring the area.</div>\n      </div>\n    </div>\n    <div class=\"list-row\">\n      <div class=\"row-icon\" style=\"background:var(--green-tint); color:var(--green);\">{{ icons.icon('map', 'icon-18') }}</div>\n      <div class=\"row-main\">\n        <div class=\"row-title\">Organized area by area</div>\n        <div class=\"row-sub\">Every corner of Puducherry, from White Town to Auroville.</div>\n      </div>\n    </div>\n  </div>\n</div>\n\n<div class=\"section\" style=\"padding-top:0;\">\n  <div class=\"section-title\">Areas covered</div>\n  <div class=\"chip-scroll\" style=\"padding-left:0; padding-right:0;\">\n    {% for area in PONDY_AREAS %}\n      <span class=\"chip\">{{ area }}</span>\n    {% endfor %}\n  </div>\n</div>\n\n{% endblock %}\n",
  "login.html": "{% extends \"base.html\" %}\n{% import \"_icons.html\" as icons %}\n{% block title %}Log In — LocatePondy{% endblock %}\n\n{% block content %}\n<div class=\"center-page\">\n  <div class=\"card auth-card\">\n    <div class=\"icon-badge\">{{ icons.icon('log-in', 'icon-28') }}</div>\n    <h1>Welcome back</h1>\n    <p class=\"sub\">Log in to add shops, rate places, and leave feedback.</p>\n\n    <div class=\"segmented\" id=\"login-tabs\" style=\"margin-bottom:20px;\">\n      <input type=\"radio\" name=\"login_tab\" id=\"tab-phone\" checked>\n      <label for=\"tab-phone\" onclick=\"showTab('phone')\">Phone</label>\n      <input type=\"radio\" name=\"login_tab\" id=\"tab-email\">\n      <label for=\"tab-email\" onclick=\"showTab('email')\">Email</label>\n      <input type=\"radio\" name=\"login_tab\" id=\"tab-google\">\n      <label for=\"tab-google\" onclick=\"showTab('google')\">Google</label>\n    </div>\n\n    <!-- Phone / OTP panel -->\n    <div class=\"tab-panel\" data-panel=\"phone\">\n      {% if not otp_stage %}\n      <form method=\"POST\" action=\"{{ url_for('login') }}\">\n        <input type=\"hidden\" name=\"csrf_token\" value=\"{{ csrf_token() }}\">\n        <input type=\"hidden\" name=\"method\" value=\"phone\">\n        <div class=\"form-group\">\n          <label class=\"form-label\">Phone number</label>\n          <input class=\"form-control\" type=\"tel\" name=\"phone\" placeholder=\"e.g. 9876543210\" required>\n        </div>\n        <button type=\"submit\" name=\"send_otp\" value=\"1\" class=\"btn btn-primary block\">Send OTP</button>\n      </form>\n      {% else %}\n      <form method=\"POST\" action=\"{{ url_for('login') }}\">\n        <input type=\"hidden\" name=\"csrf_token\" value=\"{{ csrf_token() }}\">\n        <input type=\"hidden\" name=\"method\" value=\"phone\">\n        <input type=\"hidden\" name=\"phone\" value=\"{{ phone }}\">\n        <div class=\"form-group\">\n          <label class=\"form-label\">Phone number</label>\n          <input class=\"form-control\" type=\"tel\" value=\"{{ phone }}\" disabled>\n        </div>\n        <div class=\"form-group\">\n          <label class=\"form-label\">Enter the OTP sent to your phone</label>\n          <input class=\"form-control\" type=\"text\" name=\"otp\" inputmode=\"numeric\" maxlength=\"6\" placeholder=\"6-digit code\" required autofocus>\n        </div>\n        <button type=\"submit\" name=\"verify_otp\" value=\"1\" class=\"btn btn-primary block\">Verify & Log In</button>\n      </form>\n      {% endif %}\n    </div>\n\n    <!-- Email / password panel -->\n    <div class=\"tab-panel\" data-panel=\"email\" style=\"display:none;\">\n      <form method=\"POST\" action=\"{{ url_for('login') }}\">\n        <input type=\"hidden\" name=\"csrf_token\" value=\"{{ csrf_token() }}\">\n        <input type=\"hidden\" name=\"method\" value=\"email\">\n        <div class=\"form-group\">\n          <label class=\"form-label\">Email</label>\n          <input class=\"form-control\" type=\"email\" name=\"email\" placeholder=\"you@example.com\" required>\n        </div>\n        <div class=\"form-group\">\n          <label class=\"form-label\">Password</label>\n          <input class=\"form-control\" type=\"password\" name=\"password\" placeholder=\"••••••••\" required>\n        </div>\n        <button type=\"submit\" class=\"btn btn-primary block\">Log In</button>\n      </form>\n    </div>\n\n    <!-- Google panel -->\n    <div class=\"tab-panel\" data-panel=\"google\" style=\"display:none; text-align:center;\">\n      <p style=\"font-size:13.5px; color:var(--ink-soft); margin-bottom:16px;\">\n        Demo mode — signs you in as a sample Google account. Configure real OAuth in <code>config.py</code>.\n      </p>\n      <a href=\"{{ url_for('google_login') }}\" class=\"btn btn-outline block\">Continue with Google</a>\n    </div>\n\n    <p class=\"auth-switch\">New here? <a href=\"{{ url_for('register') }}\">Create an account</a></p>\n    <p class=\"auth-switch\" style=\"margin-top:4px;\">Are you the admin? <a href=\"{{ url_for('admin_login') }}\">Log in here</a></p>\n  </div>\n</div>\n\n<script>\n  function showTab(name) {\n    document.querySelectorAll('.tab-panel').forEach(function (p) {\n      p.style.display = (p.getAttribute('data-panel') === name) ? 'block' : 'none';\n    });\n  }\n  {% if otp_stage %}showTab('phone');{% endif %}\n</script>\n{% endblock %}\n",
  "register.html": "{% extends \"base.html\" %}\n{% import \"_icons.html\" as icons %}\n{% block title %}Create Account — LocatePondy{% endblock %}\n\n{% block content %}\n<div class=\"center-page\">\n  <div class=\"card auth-card\">\n    <div class=\"icon-badge\">{{ icons.icon('user', 'icon-28') }}</div>\n    <h1>Create your account</h1>\n    <p class=\"sub\">Join LocatePondy to add and manage your own shop listings.</p>\n\n    <form method=\"POST\" action=\"{{ url_for('register') }}\">\n      <input type=\"hidden\" name=\"csrf_token\" value=\"{{ csrf_token() }}\">\n      <div class=\"form-group\">\n        <label class=\"form-label\">Full name</label>\n        <input class=\"form-control\" type=\"text\" name=\"name\" placeholder=\"Your name\" required>\n      </div>\n      <div class=\"form-group\">\n        <label class=\"form-label\">Email</label>\n        <input class=\"form-control\" type=\"email\" name=\"email\" placeholder=\"you@example.com\" required>\n      </div>\n      <div class=\"form-group\">\n        <label class=\"form-label\">Password</label>\n        <input class=\"form-control\" type=\"password\" name=\"password\" placeholder=\"8+ characters, with a letter and a number\" required>\n        <p class=\"form-hint\">Must be at least 8 characters and include a letter and a number.</p>\n      </div>\n      <button type=\"submit\" class=\"btn btn-primary block\">Create Account</button>\n    </form>\n\n    <p class=\"auth-switch\">Already have an account? <a href=\"{{ url_for('login') }}\">Log in</a></p>\n  </div>\n</div>\n{% endblock %}\n",
  "locate.html": "{% extends \"base.html\" %}\n{% import \"_icons.html\" as icons %}\n{% block title %}Locate — LocatePondy{% endblock %}\n\n{% block content %}\n<div class=\"large-title\">\n  <h1>Locate</h1>\n  <p>Browse verified shops, area by area.</p>\n</div>\n\n<form method=\"GET\" action=\"{{ url_for('locate') }}\" id=\"locate-filter-form\">\n  <div class=\"search-bar\">\n    {{ icons.icon('search', 'icon-18') }}\n    <input type=\"text\" name=\"q\" placeholder=\"Search shop names…\" value=\"{{ search_q }}\">\n  </div>\n\n  <div class=\"container\" style=\"display:flex; gap:8px; padding-bottom:12px;\">\n    <select class=\"form-control\" name=\"area\" data-auto-submit style=\"flex:1; font-size:14px; padding:10px 30px 10px 12px;\">\n      <option value=\"\">All areas</option>\n      {% for area in PONDY_AREAS %}\n        <option value=\"{{ area }}\" {{ 'selected' if area_filter == area }}>{{ area }}</option>\n      {% endfor %}\n    </select>\n    <select class=\"form-control\" name=\"category\" data-auto-submit style=\"flex:1; font-size:14px; padding:10px 30px 10px 12px;\">\n      <option value=\"\">All categories</option>\n      {% for cat in SHOP_CATEGORIES %}\n        <option value=\"{{ cat }}\" {{ 'selected' if category_filter == cat }}>{{ cat }}</option>\n      {% endfor %}\n    </select>\n  </div>\n</form>\n\n{% set has_filters = area_filter or category_filter or search_q %}\n{% set any_results = shops_by_area.values() | map('length') | sum > 0 %}\n\n{% if not any_results %}\n<div class=\"empty-state\">\n  {{ icons.icon('map-pin', 'icon-28') }}\n  <h3>No shops found</h3>\n  <p>{% if has_filters %}Try a different search or filter.{% else %}No verified shops yet — check back soon.{% endif %}</p>\n</div>\n{% endif %}\n\n{% for area, shops in shops_by_area.items() %}\n  {% if shops or not has_filters %}\n  <details class=\"area-accordion\" {{ 'open' if shops and (has_filters or loop.first) }}>\n    <summary class=\"area-summary\">\n      <span class=\"area-name\">{{ area }}</span>\n      <span style=\"display:flex; align-items:center; gap:8px;\">\n        <span class=\"area-count\">{{ shops|length }}</span>\n        {{ icons.icon('chevron-down', 'icon-16') }}\n      </span>\n    </summary>\n    <div class=\"area-body\">\n      {% if shops %}\n        {% for shop in shops %}\n          {% include \"_shop_card.html\" %}\n        {% endfor %}\n      {% else %}\n        <p class=\"empty-note\">No shops listed in {{ area }} yet.</p>\n      {% endif %}\n    </div>\n  </details>\n  {% endif %}\n{% endfor %}\n\n{% if current_user.is_authenticated and not current_user.is_admin %}\n<div class=\"section\">\n  <a href=\"{{ url_for('add_shop') }}\" class=\"btn btn-primary block\">{{ icons.icon('plus-circle', 'icon-18') }} Add your shop</a>\n</div>\n{% endif %}\n\n{% endblock %}\n",
  "add_shop.html": "{% extends \"base.html\" %}\n{% import \"_icons.html\" as icons %}\n{% block title %}Add a Shop — LocatePondy{% endblock %}\n\n{% block content %}\n<div class=\"large-title\">\n  <h1>Add a shop</h1>\n  <p>Submitted listings are reviewed before going live.</p>\n</div>\n\n<div class=\"section\" style=\"padding-top:0;\">\n  <form method=\"POST\" action=\"{{ url_for('add_shop') }}\" enctype=\"multipart/form-data\" class=\"card\" style=\"padding:18px;\">\n    <input type=\"hidden\" name=\"csrf_token\" value=\"{{ csrf_token() }}\">\n\n    <div class=\"form-group\">\n      <label class=\"form-label\">Shop name</label>\n      <input class=\"form-control\" type=\"text\" name=\"name\" id=\"shop-name\" maxlength=\"{{ name_max }}\" required>\n      <p class=\"form-hint char-count\" data-char-count-for=\"shop-name\" data-max=\"{{ name_max }}\">0 / {{ name_max }}</p>\n    </div>\n\n    <div class=\"form-group\">\n      <label class=\"form-label\">Category</label>\n      <select class=\"form-control\" name=\"category\" required>\n        <option value=\"\" disabled selected>Choose a category</option>\n        {% for cat in SHOP_CATEGORIES %}<option value=\"{{ cat }}\">{{ cat }}</option>{% endfor %}\n      </select>\n    </div>\n\n    <div class=\"form-group\">\n      <label class=\"form-label\">Area</label>\n      <select class=\"form-control\" name=\"area\" required>\n        <option value=\"\" disabled selected>Choose an area</option>\n        {% for area in PONDY_AREAS %}<option value=\"{{ area }}\">{{ area }}</option>{% endfor %}\n      </select>\n    </div>\n\n    <div class=\"form-group\">\n      <label class=\"form-label\">Phone number</label>\n      <input class=\"form-control\" type=\"tel\" name=\"phone_number\" placeholder=\"10-digit phone number\" required>\n    </div>\n\n    <div class=\"form-group\">\n      <label class=\"form-label\">Description</label>\n      <textarea class=\"form-control\" name=\"description\" placeholder=\"What makes this place worth visiting?\"></textarea>\n    </div>\n\n    <div class=\"form-group\">\n      <label class=\"form-label\">Address</label>\n      <input class=\"form-control\" type=\"text\" name=\"address\" placeholder=\"Street, landmark\">\n    </div>\n\n    <div class=\"form-group\">\n      <label class=\"form-label\">Google Maps link <span style=\"font-weight:400; color:var(--ink-faint);\">(optional)</span></label>\n      <input class=\"form-control\" type=\"url\" name=\"map_link\" placeholder=\"https://maps.google.com/…\">\n    </div>\n\n    <div class=\"form-group\">\n      <label class=\"form-label\">Scrolling offer text <span style=\"font-weight:400; color:var(--ink-faint);\">(optional)</span></label>\n      <input class=\"form-control\" type=\"text\" name=\"offer_text\" maxlength=\"200\" placeholder=\"e.g. 20% off this weekend!\">\n    </div>\n\n    <div class=\"form-group\">\n      <label class=\"form-label\">Photos <span style=\"font-weight:400; color:var(--ink-faint);\">(up to {{ max_photos }})</span></label>\n      <label class=\"file-drop\" for=\"shop-images\">\n        {{ icons.icon('camera', 'icon-24') }}\n        <div id=\"drop-label\">Tap to choose photos</div>\n        <input type=\"file\" id=\"shop-images\" name=\"images\" accept=\"image/png,image/jpeg,image/gif,image/webp\"\n               multiple data-photo-input data-max-photos=\"{{ max_photos }}\"\n               data-preview-target=\"#photo-previews\" data-drop-label=\"#drop-label\">\n      </label>\n      <div class=\"thumb-row\" id=\"photo-previews\"></div>\n    </div>\n\n    <button type=\"submit\" class=\"btn btn-primary block\" style=\"margin-top:6px;\">Submit for review</button>\n  </form>\n</div>\n{% endblock %}\n",
  "shop_detail.html": "{% extends \"base.html\" %}\n{% import \"_icons.html\" as icons %}\n{% block title %}{{ shop.name }} — LocatePondy{% endblock %}\n\n{% block content %}\n\n<div class=\"carousel\" data-carousel>\n  {% if shop.images %}\n    <div class=\"carousel-track\">\n      {% for img in shop.images %}\n        <img src=\"{{ url_for('static', filename='uploads/' ~ img.filename) }}\" alt=\"{{ shop.name }}\">\n      {% endfor %}\n    </div>\n    {% if shop.images|length > 1 %}\n    <div class=\"carousel-dots\">\n      {% for img in shop.images %}<span class=\"{{ 'active' if loop.first }}\"></span>{% endfor %}\n    </div>\n    {% endif %}\n  {% else %}\n    <div class=\"no-photo\">{{ icons.icon('camera', 'icon-28') }}</div>\n  {% endif %}\n\n  {% if shop.offer_text %}\n    <div class=\"offer-marquee\" style=\"bottom:0;\"><span>🎉 {{ shop.offer_text }} &nbsp;&nbsp;&nbsp; 🎉 {{ shop.offer_text }}</span></div>\n  {% endif %}\n</div>\n\n<div class=\"detail-header\">\n  <div class=\"title-row\">\n    <div>\n      <h1>{{ shop.name }}</h1>\n      <p class=\"cat-area\">{{ shop.category }} · {{ shop.area }}</p>\n    </div>\n    {% if shop.is_verified %}\n      <span class=\"badge verified\">{{ icons.icon('check', 'icon-14') }} Verified</span>\n    {% elif current_user.is_authenticated and (current_user.is_admin or shop.owner_id == current_user.id) %}\n      <span class=\"badge {{ shop.status }}\">{{ shop.status|capitalize }}</span>\n    {% endif %}\n  </div>\n\n  {% if shop.rating_count %}\n    <span class=\"stars\">\n      {% for i in range(1,6) %}{{ icons.icon('star' if i <= shop.average_rating|round(0,'floor') else 'star-outline') }}{% endfor %}\n    </span>\n    <span class=\"rating-count\">{{ shop.average_rating }} · {{ shop.rating_count }} rating{{ 's' if shop.rating_count != 1 }}</span>\n  {% else %}\n    <span class=\"rating-count\">No ratings yet</span>\n  {% endif %}\n</div>\n\n<div class=\"action-row\">\n  <a href=\"tel:{{ shop.phone_number }}\" class=\"btn btn-primary\">{{ icons.icon('phone', 'icon-18') }} Call</a>\n  {% if shop.map_link %}\n    <a href=\"{{ shop.map_link }}\" target=\"_blank\" rel=\"noopener\" class=\"btn btn-secondary\">{{ icons.icon('map', 'icon-18') }} Map</a>\n  {% endif %}\n</div>\n\n{% if shop.description or shop.address %}\n<div class=\"card info-card\">\n  {% if shop.description %}\n  <div class=\"row\">\n    {{ icons.icon('sparkles') }}\n    <span>{{ shop.description }}</span>\n  </div>\n  {% endif %}\n  {% if shop.address %}\n  <div class=\"row\">\n    {{ icons.icon('map-pin') }}\n    <span>{{ shop.address }}</span>\n  </div>\n  {% endif %}\n  <div class=\"row\">\n    {{ icons.icon('phone') }}\n    <span>{{ shop.phone_number }}</span>\n  </div>\n</div>\n{% endif %}\n\n{% if shop.status == 'rejected' and (current_user.is_authenticated and (current_user.is_admin or shop.owner_id == current_user.id)) %}\n<div class=\"section\" style=\"padding-top:0;\">\n  <div class=\"toast danger\" style=\"position:static; animation:none;\">\n    <span class=\"dot\"></span>\n    <span class=\"msg\">Rejected: {{ shop.rejection_reason }}</span>\n  </div>\n</div>\n{% endif %}\n\n{% if shop.is_verified %}\n\n  {% if current_user.is_authenticated and not current_user.is_admin %}\n  <div class=\"card rating-widget\" data-star-widget>\n    <div class=\"section-title\" style=\"margin-bottom:0;\">{{ 'Update your rating' if user_rating else 'Rate this shop' }}</div>\n    <form method=\"POST\" action=\"{{ url_for('rate_shop', shop_id=shop.id) }}\" id=\"rate-form\">\n      <input type=\"hidden\" name=\"csrf_token\" value=\"{{ csrf_token() }}\">\n      <input type=\"hidden\" name=\"stars\" value=\"{{ user_rating or 0 }}\">\n      <div class=\"big-star-row\">\n        {% for i in range(1,6) %}\n          <button type=\"submit\" data-star=\"{{ i }}\" onclick=\"document.getElementById('rate-form').querySelector('[name=stars]').value={{ i }}\">\n            {{ icons.icon('star' if user_rating and i <= user_rating else 'star-outline') }}\n          </button>\n        {% endfor %}\n      </div>\n    </form>\n  </div>\n  {% endif %}\n\n  <div class=\"section\">\n    <div class=\"section-title\">Feedback ({{ feedbacks|length }})</div>\n    <div class=\"card\" style=\"padding:6px 16px;\">\n      {% if current_user.is_authenticated and not current_user.is_admin %}\n      <form method=\"POST\" action=\"{{ url_for('add_feedback', shop_id=shop.id) }}\" style=\"padding:12px 0; border-bottom:0.5px solid var(--hairline);\">\n        <input type=\"hidden\" name=\"csrf_token\" value=\"{{ csrf_token() }}\">\n        <textarea class=\"form-control\" name=\"message\" placeholder=\"Share your experience…\" required style=\"min-height:70px;\"></textarea>\n        <button type=\"submit\" class=\"btn btn-primary small\" style=\"margin-top:8px;\">Post feedback</button>\n      </form>\n      {% endif %}\n\n      {% for fb in feedbacks %}\n        <div class=\"feedback-item\">\n          <div class=\"author\">{{ fb.user.name }}</div>\n          <div class=\"msg\">{{ fb.message }}</div>\n          <div class=\"date\">{{ fb.created_at.strftime('%d %b %Y') }}</div>\n        </div>\n      {% else %}\n        <p class=\"empty-note\" style=\"padding:14px 0;\">No feedback yet — be the first to share your experience.</p>\n      {% endfor %}\n    </div>\n  </div>\n\n{% endif %}\n\n{% endblock %}\n",
  "my_shops.html": "{% extends \"base.html\" %}\n{% import \"_icons.html\" as icons %}\n{% block title %}My Shops — LocatePondy{% endblock %}\n\n{% block content %}\n<div class=\"large-title\">\n  <h1>My Shops</h1>\n  <p>Track the review status of everything you've submitted.</p>\n</div>\n\n<div class=\"section\" style=\"padding-top:0;\">\n  <a href=\"{{ url_for('add_shop') }}\" class=\"btn btn-primary block\" style=\"margin-bottom:16px;\">\n    {{ icons.icon('plus-circle', 'icon-18') }} Add another shop\n  </a>\n\n  {% if shops %}\n    {% for shop in shops %}\n      {% set show_status = true %}\n      {% include \"_shop_card.html\" %}\n      {% if shop.status == 'rejected' and shop.rejection_reason %}\n        <p style=\"font-size:12.5px; color:var(--red); margin:-10px 0 14px 4px;\">Reason: {{ shop.rejection_reason }}</p>\n      {% endif %}\n    {% endfor %}\n  {% else %}\n    <div class=\"empty-state\">\n      {{ icons.icon('grid', 'icon-28') }}\n      <h3>No shops yet</h3>\n      <p>Shops you submit will appear here with their review status.</p>\n    </div>\n  {% endif %}\n</div>\n{% endblock %}\n",
  "404.html": "{% extends \"base.html\" %}\n{% import \"_icons.html\" as icons %}\n{% block title %}Not Found — LocatePondy{% endblock %}\n{% block content %}\n<div class=\"center-page\">\n  <div class=\"empty-state\">\n    {{ icons.icon('compass', 'icon-28') }}\n    <h3>Page not found</h3>\n    <p>This street doesn't exist on the map. Let's get you back.</p>\n    <a href=\"{{ url_for('home') }}\" class=\"btn btn-primary\" style=\"margin-top:16px;\">Back to home</a>\n  </div>\n</div>\n{% endblock %}\n",
  "403.html": "{% extends \"base.html\" %}\n{% import \"_icons.html\" as icons %}\n{% block title %}Access Denied — LocatePondy{% endblock %}\n{% block content %}\n<div class=\"center-page\">\n  <div class=\"empty-state\">\n    {{ icons.icon('shield', 'icon-28') }}\n    <h3>Access denied</h3>\n    <p>You don't have permission to view this page, or you've hit a rate limit. Please try again shortly.</p>\n    <a href=\"{{ url_for('home') }}\" class=\"btn btn-primary\" style=\"margin-top:16px;\">Back to home</a>\n  </div>\n</div>\n{% endblock %}\n",
  "admin/login.html": "{% extends \"base.html\" %}\n{% import \"_icons.html\" as icons %}\n{% block title %}Admin Login — LocatePondy{% endblock %}\n\n{% block content %}\n<div class=\"center-page\">\n  <div class=\"card auth-card\">\n    <div class=\"icon-badge\" style=\"background:var(--mustard-tint); color:var(--mustard-dark);\">{{ icons.icon('shield', 'icon-28') }}</div>\n    <h1>Admin login</h1>\n    <p class=\"sub\">Restricted access — for verifying and managing listings.</p>\n\n    <form method=\"POST\" action=\"{{ url_for('admin_login') }}\">\n      <input type=\"hidden\" name=\"csrf_token\" value=\"{{ csrf_token() }}\">\n      <div class=\"form-group\">\n        <label class=\"form-label\">Username</label>\n        <input class=\"form-control\" type=\"text\" name=\"username\" required autofocus>\n      </div>\n      <div class=\"form-group\">\n        <label class=\"form-label\">Password</label>\n        <input class=\"form-control\" type=\"password\" name=\"password\" required>\n      </div>\n      <button type=\"submit\" class=\"btn btn-mustard block\">Log In</button>\n    </form>\n    <p class=\"auth-switch\">Not an admin? <a href=\"{{ url_for('login') }}\">Go to user login</a></p>\n  </div>\n</div>\n{% endblock %}\n",
  "admin/dashboard.html": "{% extends \"base.html\" %}\n{% import \"_icons.html\" as icons %}\n{% block title %}Admin Dashboard — LocatePondy{% endblock %}\n\n{% block content %}\n<div class=\"large-title\">\n  <h1>Admin</h1>\n  <p>Review, verify, and manage every listing.</p>\n</div>\n\n<div class=\"admin-toolbar\">\n  <a href=\"{{ url_for('admin_dashboard', status='pending') }}\" class=\"chip {{ 'active' if status_filter == 'pending' }}\">Pending ({{ counts.pending }})</a>\n  <a href=\"{{ url_for('admin_dashboard', status='approved') }}\" class=\"chip {{ 'active' if status_filter == 'approved' }}\">Approved ({{ counts.approved }})</a>\n  <a href=\"{{ url_for('admin_dashboard', status='rejected') }}\" class=\"chip {{ 'active' if status_filter == 'rejected' }}\">Rejected ({{ counts.rejected }})</a>\n</div>\n\n<div class=\"section\" style=\"padding-top:0;\">\n  {% if shops %}\n    {% for shop in shops %}\n      <div class=\"card admin-shop-row\" style=\"margin-bottom:12px;\">\n        <div class=\"top\">\n          <div>\n            <div style=\"font-weight:700; font-size:15.5px;\">{{ shop.name }}</div>\n            <div style=\"font-size:13px; color:var(--ink-soft);\">{{ shop.category }} · {{ shop.area }}</div>\n            <div style=\"font-size:12.5px; color:var(--ink-faint); margin-top:2px;\">by {{ shop.owner.name }} · {{ shop.created_at.strftime('%d %b %Y') }}</div>\n          </div>\n          <span class=\"badge {{ shop.status }}\">{{ shop.status|capitalize }}</span>\n        </div>\n\n        {% if shop.status == 'rejected' and shop.rejection_reason %}\n          <p style=\"font-size:12.5px; color:var(--red); margin:8px 0 0;\">Reason: {{ shop.rejection_reason }}</p>\n        {% endif %}\n\n        <div class=\"actions\">\n          <a href=\"{{ url_for('shop_detail', shop_id=shop.id) }}\" class=\"btn btn-outline small\">View</a>\n          <a href=\"{{ url_for('admin_edit_shop', shop_id=shop.id) }}\" class=\"btn btn-secondary small\">{{ icons.icon('pencil', 'icon-16') }} Edit</a>\n\n          {% if shop.status != 'approved' %}\n          <form method=\"POST\" action=\"{{ url_for('admin_approve_shop', shop_id=shop.id) }}\">\n            <input type=\"hidden\" name=\"csrf_token\" value=\"{{ csrf_token() }}\">\n            <button type=\"submit\" class=\"btn btn-success small\">{{ icons.icon('check', 'icon-16') }} Approve</button>\n          </form>\n          {% endif %}\n\n          {% if shop.status != 'rejected' %}\n          <button type=\"button\" class=\"btn btn-outline small\" onclick=\"toggleReason({{ shop.id }})\">{{ icons.icon('x', 'icon-16') }} Reject</button>\n          {% endif %}\n\n          <form method=\"POST\" action=\"{{ url_for('admin_delete_shop', shop_id=shop.id) }}\" onsubmit=\"return confirm('Delete {{ shop.name }} permanently?');\">\n            <input type=\"hidden\" name=\"csrf_token\" value=\"{{ csrf_token() }}\">\n            <button type=\"submit\" class=\"btn btn-danger small\">{{ icons.icon('trash', 'icon-16') }} Delete</button>\n          </form>\n        </div>\n\n        <div class=\"reason-box\" id=\"reason-{{ shop.id }}\" style=\"display:none;\">\n          <form method=\"POST\" action=\"{{ url_for('admin_reject_shop', shop_id=shop.id) }}\" style=\"display:flex; gap:8px; margin-top:8px;\">\n            <input type=\"hidden\" name=\"csrf_token\" value=\"{{ csrf_token() }}\">\n            <input class=\"form-control\" type=\"text\" name=\"reason\" placeholder=\"Reason for rejection\" style=\"flex:1;\">\n            <button type=\"submit\" class=\"btn btn-danger small\">Confirm</button>\n          </form>\n        </div>\n      </div>\n    {% endfor %}\n  {% else %}\n    <div class=\"empty-state\">\n      {{ icons.icon('shield', 'icon-28') }}\n      <h3>Nothing here</h3>\n      <p>No {{ status_filter }} listings right now.</p>\n    </div>\n  {% endif %}\n</div>\n\n<script>\n  function toggleReason(id) {\n    var box = document.getElementById('reason-' + id);\n    box.style.display = box.style.display === 'none' ? 'block' : 'none';\n  }\n</script>\n{% endblock %}\n",
  "admin/edit_shop.html": "{% extends \"base.html\" %}\n{% import \"_icons.html\" as icons %}\n{% block title %}Edit {{ shop.name }} — LocatePondy{% endblock %}\n\n{% block content %}\n<div class=\"large-title\">\n  <h1>Edit shop</h1>\n  <p>Full access — changes go live immediately.</p>\n</div>\n\n<div class=\"section\" style=\"padding-top:0;\">\n  <form method=\"POST\" action=\"{{ url_for('admin_edit_shop', shop_id=shop.id) }}\" enctype=\"multipart/form-data\" class=\"card\" style=\"padding:18px;\">\n    <input type=\"hidden\" name=\"csrf_token\" value=\"{{ csrf_token() }}\">\n\n    <div class=\"form-group\">\n      <label class=\"form-label\">Shop name</label>\n      <input class=\"form-control\" type=\"text\" name=\"name\" id=\"shop-name\" maxlength=\"{{ name_max }}\" value=\"{{ shop.name }}\" required>\n      <p class=\"form-hint char-count\" data-char-count-for=\"shop-name\" data-max=\"{{ name_max }}\">{{ shop.name|length }} / {{ name_max }}</p>\n    </div>\n\n    <div class=\"form-group\">\n      <label class=\"form-label\">Category</label>\n      <select class=\"form-control\" name=\"category\" required>\n        {% for cat in SHOP_CATEGORIES %}<option value=\"{{ cat }}\" {{ 'selected' if cat == shop.category }}>{{ cat }}</option>{% endfor %}\n      </select>\n    </div>\n\n    <div class=\"form-group\">\n      <label class=\"form-label\">Area</label>\n      <select class=\"form-control\" name=\"area\" required>\n        {% for area in PONDY_AREAS %}<option value=\"{{ area }}\" {{ 'selected' if area == shop.area }}>{{ area }}</option>{% endfor %}\n      </select>\n    </div>\n\n    <div class=\"form-group\">\n      <label class=\"form-label\">Phone number</label>\n      <input class=\"form-control\" type=\"tel\" name=\"phone_number\" value=\"{{ shop.phone_number }}\" required>\n    </div>\n\n    <div class=\"form-group\">\n      <label class=\"form-label\">Description</label>\n      <textarea class=\"form-control\" name=\"description\">{{ shop.description or '' }}</textarea>\n    </div>\n\n    <div class=\"form-group\">\n      <label class=\"form-label\">Address</label>\n      <input class=\"form-control\" type=\"text\" name=\"address\" value=\"{{ shop.address or '' }}\">\n    </div>\n\n    <div class=\"form-group\">\n      <label class=\"form-label\">Google Maps link</label>\n      <input class=\"form-control\" type=\"url\" name=\"map_link\" value=\"{{ shop.map_link or '' }}\">\n    </div>\n\n    <div class=\"form-group\">\n      <label class=\"form-label\">Scrolling offer text</label>\n      <input class=\"form-control\" type=\"text\" name=\"offer_text\" maxlength=\"200\" value=\"{{ shop.offer_text or '' }}\">\n    </div>\n\n    {% if shop.images %}\n    <div class=\"form-group\">\n      <label class=\"form-label\">Existing photos <span style=\"font-weight:400; color:var(--ink-faint);\">(check to remove)</span></label>\n      <div class=\"thumb-row\">\n        {% for img in shop.images %}\n          <label class=\"thumb\" style=\"cursor:pointer;\">\n            <img src=\"{{ url_for('static', filename='uploads/' ~ img.filename) }}\">\n            <input type=\"checkbox\" name=\"remove_image_ids\" value=\"{{ img.id }}\" data-remove-toggle style=\"position:absolute; top:2px; left:2px; width:16px; height:16px;\">\n          </label>\n        {% endfor %}\n      </div>\n    </div>\n    {% endif %}\n\n    <div class=\"form-group\">\n      <label class=\"form-label\">Add more photos <span style=\"font-weight:400; color:var(--ink-faint);\">(max {{ max_photos }} total)</span></label>\n      <label class=\"file-drop\" for=\"shop-images\">\n        {{ icons.icon('camera', 'icon-24') }}\n        <div id=\"drop-label\">Tap to choose photos</div>\n        <input type=\"file\" id=\"shop-images\" name=\"images\" accept=\"image/png,image/jpeg,image/gif,image/webp\"\n               multiple data-photo-input data-max-photos=\"{{ max_photos }}\"\n               data-preview-target=\"#photo-previews\" data-drop-label=\"#drop-label\">\n      </label>\n      <div class=\"thumb-row\" id=\"photo-previews\"></div>\n    </div>\n\n    <button type=\"submit\" class=\"btn btn-primary block\" style=\"margin-top:6px;\">Save changes</button>\n  </form>\n</div>\n{% endblock %}\n"
}

# ----------------------------------------------------------------------
# App / Extensions setup
# ----------------------------------------------------------------------
app = Flask(__name__)
app.config.from_object(Config)

if app.config["SECRET_KEY"] == "locatepondy-dev-secret-change-in-production":
    print(
        "\n*** WARNING: SECRET_KEY is still the default dev value. "
        "Set a strong SECRET_KEY environment variable before deploying. ***\n"
    )

db = SQLAlchemy(app)
csrf = CSRFProtect(app)
limiter = Limiter(get_remote_address, app=app, default_limits=[])

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to add or manage shops."
login_manager.login_message_category = "info"

from jinja2 import DictLoader
app.jinja_loader = DictLoader(TEMPLATES)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

PONDY_AREAS = [
    "White Town",
    "Heritage Town (Tamil Quarter)",
    "Muthialpet",
    "Lawspet",
    "Reddiarpalayam",
    "Kalapet",
    "Thattanchavady",
    "Ariyankuppam",
    "Ozhukarai",
    "Villianur",
    "Mudaliarpet",
    "Uppalam",
    "Nellithope",
    "Auroville & Suburbs",
    "Karuvadikuppam",
]

SHOP_CATEGORIES = [
    "South Indian",
    "North Indian",
    "French / Continental",
    "Cafe & Bakery",
    "Street Food",
    "Sea Food",
    "Fast Food",
    "Ice Cream & Desserts",
    "Juice & Beverages",
    "Bar & Restaurant",
    "Vegan / Healthy",
    "Sweets & Snacks",
    "Other",
]


# ----------------------------------------------------------------------
# Models
# ----------------------------------------------------------------------
class Admin(UserMixin, db.Model):
    """Separate admin account, kept in its own table so it can never be
    created or upgraded to from the public registration form."""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    failed_login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)

    is_admin = True  # class-level flag used in templates / decorators

    def get_id(self):
        return f"admin-{self.id}"

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=True)
    email = db.Column(db.String(150), unique=True, nullable=True)
    password_hash = db.Column(db.String(255), nullable=True)
    auth_provider = db.Column(db.String(20), default="phone")  # phone | email | google
    google_id = db.Column(db.String(150), unique=True, nullable=True)
    avatar_url = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    failed_login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)

    is_admin = False  # class-level flag used in templates / decorators

    shops = db.relationship("Shop", backref="owner", lazy=True,
                             cascade="all, delete-orphan")
    ratings = db.relationship("Rating", backref="user", lazy=True,
                               cascade="all, delete-orphan")
    feedbacks = db.relationship("Feedback", backref="user", lazy=True,
                                 cascade="all, delete-orphan")

    def get_id(self):
        return f"user-{self.id}"

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, raw)


class Shop(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    area = db.Column(db.String(80), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)
    description = db.Column(db.Text, nullable=True)
    map_link = db.Column(db.String(500), nullable=True)
    address = db.Column(db.String(300), nullable=True)

    # Scrolling promotional text shown over the shop's photo(s)
    offer_text = db.Column(db.String(200), nullable=True)

    # Verification / moderation workflow — every listing must be approved
    # by the admin before it is publicly visible. Only the admin can
    # edit, approve, reject, or delete a listing after it is submitted.
    status = db.Column(db.String(20), default="pending")  # pending | approved | rejected
    rejection_reason = db.Column(db.String(300), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    images = db.relationship("ShopImage", backref="shop", lazy=True,
                              cascade="all, delete-orphan",
                              order_by="ShopImage.position")
    ratings = db.relationship("Rating", backref="shop", lazy=True,
                               cascade="all, delete-orphan")
    feedbacks = db.relationship("Feedback", backref="shop", lazy=True,
                                 cascade="all, delete-orphan")

    @property
    def average_rating(self):
        if not self.ratings:
            return 0
        return round(sum(r.stars for r in self.ratings) / len(self.ratings), 1)

    @property
    def rating_count(self):
        return len(self.ratings)

    @property
    def is_verified(self):
        return self.status == "approved"

    @property
    def cover_image(self):
        return self.images[0].filename if self.images else None


class ShopImage(db.Model):
    """Up to MAX_PHOTOS_PER_SHOP rows per shop."""
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey("shop.id"), nullable=False)
    filename = db.Column(db.String(300), nullable=False)
    position = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Rating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey("shop.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    stars = db.Column(db.Integer, nullable=False)  # 1-5
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("shop_id", "user_id",
                                           name="one_rating_per_user_per_shop"),)


class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey("shop.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


@login_manager.user_loader
def load_user(composite_id):
    """composite_id looks like 'admin-3' or 'user-17'."""
    try:
        kind, raw_id = composite_id.split("-", 1)
        raw_id = int(raw_id)
    except (ValueError, AttributeError):
        return None
    if kind == "admin":
        return Admin.query.get(raw_id)
    if kind == "user":
        return User.query.get(raw_id)
    return None


# ----------------------------------------------------------------------
# Security helpers
# ----------------------------------------------------------------------
def admin_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not getattr(current_user, "is_admin", False):
            abort(403)
        return view_func(*args, **kwargs)
    return wrapped


def is_locked(account):
    return bool(account.locked_until and account.locked_until > datetime.utcnow())


def register_failed_attempt(account):
    account.failed_login_attempts = (account.failed_login_attempts or 0) + 1
    if account.failed_login_attempts >= app.config["MAX_FAILED_LOGIN_ATTEMPTS"]:
        account.locked_until = datetime.utcnow() + timedelta(
            minutes=app.config["ACCOUNT_LOCKOUT_MINUTES"]
        )
    db.session.commit()


def reset_failed_attempts(account):
    account.failed_login_attempts = 0
    account.locked_until = None
    db.session.commit()


def password_is_strong(raw):
    """Minimum bar: 8+ characters with at least one letter and one digit."""
    if len(raw) < 8:
        return False
    has_letter = any(c.isalpha() for c in raw)
    has_digit = any(c.isdigit() for c in raw)
    return has_letter and has_digit


def generate_otp():
    return "".join(random.choices(string.digits, k=6))


# ----------------------------------------------------------------------
# Upload helpers
# ----------------------------------------------------------------------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_shop_image(file_storage):
    if not file_storage or file_storage.filename == "":
        return None
    if not allowed_file(file_storage.filename):
        flash(f"'{file_storage.filename}': unsupported format. Use png, jpg, jpeg, gif or webp.", "danger")
        return None
    ext = file_storage.filename.rsplit(".", 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file_storage.save(path)
    return filename


def delete_shop_images(shop):
    for img in shop.images:
        path = os.path.join(app.config["UPLOAD_FOLDER"], img.filename)
        if os.path.exists(path):
            os.remove(path)


@app.context_processor
def inject_globals():
    return {
        "PONDY_AREAS": PONDY_AREAS,
        "SHOP_CATEGORIES": SHOP_CATEGORIES,
        "current_year": datetime.utcnow().year,
        "SHOP_NAME_MAX_LENGTH": app.config["SHOP_NAME_MAX_LENGTH"],
        "MAX_PHOTOS_PER_SHOP": app.config["MAX_PHOTOS_PER_SHOP"],
    }


# ----------------------------------------------------------------------
# Public pages
# ----------------------------------------------------------------------
@app.route("/")
def home():
    approved = Shop.query.filter_by(status="approved")
    total_shops = approved.count()
    total_areas_used = db.session.query(Shop.area).filter(Shop.status == "approved").distinct().count()
    top_shops = (
        approved.outerjoin(Rating)
        .group_by(Shop.id)
        .order_by(func.count(Rating.id).desc())
        .limit(6)
        .all()
    )
    recent_shops = approved.order_by(Shop.created_at.desc()).limit(6).all()
    return render_template(
        "home.html",
        total_shops=total_shops,
        total_areas_used=total_areas_used,
        top_shops=top_shops,
        recent_shops=recent_shops,
    )


@app.route("/about")
def about():
    return render_template("about.html")


# ----------------------------------------------------------------------
# Auth: phone (OTP) + email/password + Google OAuth stub
# ----------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
@limiter.limit("15 per hour")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("locate"))

    if request.method == "POST":
        method = request.form.get("method", "phone")

        if method == "phone":
            phone = request.form.get("phone", "").strip()
            otp = request.form.get("otp", "").strip()

            if not phone:
                flash("Enter a valid phone number.", "danger")
                return redirect(url_for("login"))

            if "send_otp" in request.form:
                generated_otp = generate_otp()
                session["pending_phone"] = phone
                session["pending_otp"] = generated_otp
                session["pending_otp_expires"] = (
                    datetime.utcnow() + timedelta(seconds=app.config["OTP_EXPIRY_SECONDS"])
                ).isoformat()
                session["otp_attempts"] = 0
                # DEMO ONLY: flashing the OTP stands in for a real SMS gateway
                # (Twilio Verify / MSG91) — see README for how to wire one in.
                flash(f"Demo OTP sent: {generated_otp} (valid 5 minutes). Replace with a real SMS gateway in production.", "info")
                return render_template("login.html", otp_stage=True, phone=phone)

            if "verify_otp" in request.form:
                expires_raw = session.get("pending_otp_expires")
                expired = not expires_raw or datetime.fromisoformat(expires_raw) < datetime.utcnow()
                session["otp_attempts"] = session.get("otp_attempts", 0) + 1

                if session["otp_attempts"] > app.config["OTP_MAX_ATTEMPTS"]:
                    flash("Too many incorrect attempts. Request a new OTP.", "danger")
                    session.pop("pending_otp", None)
                    return render_template("login.html", otp_stage=False)

                if expired:
                    flash("OTP expired. Please request a new one.", "danger")
                    return render_template("login.html", otp_stage=False)

                if phone == session.get("pending_phone") and otp == session.get("pending_otp"):
                    user = User.query.filter_by(phone=phone).first()
                    if not user:
                        user = User(name=f"User {phone[-4:]}", phone=phone, auth_provider="phone")
                        db.session.add(user)
                        db.session.commit()
                    login_user(user)
                    session.pop("pending_otp", None)
                    session.pop("pending_phone", None)
                    session.pop("otp_attempts", None)
                    flash(f"Welcome, {user.name}!", "success")
                    return redirect(url_for("locate"))
                else:
                    flash("Incorrect OTP. Try again.", "danger")
                    return render_template("login.html", otp_stage=True, phone=phone)

        elif method == "email":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            user = User.query.filter_by(email=email).first()

            if user and is_locked(user):
                flash("Account temporarily locked due to repeated failed logins. Try again later.", "danger")
                return render_template("login.html", otp_stage=False)

            if user and user.check_password(password):
                reset_failed_attempts(user)
                login_user(user)
                flash(f"Welcome back, {user.name}!", "success")
                return redirect(url_for("locate"))

            if user:
                register_failed_attempt(user)
            flash("Invalid email or password.", "danger")

    return render_template("login.html", otp_stage=False)


@app.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per hour")
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password:
            flash("All fields are required.", "danger")
            return redirect(url_for("register"))

        if not password_is_strong(password):
            flash("Password must be at least 8 characters and include a letter and a number.", "danger")
            return redirect(url_for("register"))

        if User.query.filter_by(email=email).first():
            flash("An account with this email already exists.", "danger")
            return redirect(url_for("register"))

        user = User(name=name, email=email, auth_provider="email")
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash("Account created successfully!", "success")
        return redirect(url_for("locate"))

    return render_template("register.html")


@app.route("/login/google")
def google_login():
    """
    Placeholder route for Google OAuth.
    To enable real Google Sign-In:
      1. pip install authlib
      2. Create OAuth credentials at https://console.cloud.google.com
      3. Set GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET in config.py or env vars
      4. Register the Authlib OAuth client and redirect here to the
         provider's consent screen, then handle the callback at
         /login/google/callback to create/log in the User by google_id.
    This demo simulates a successful Google login for local testing.
    """
    demo_email = "demo.googleuser@gmail.com"
    user = User.query.filter_by(email=demo_email).first()
    if not user:
        user = User(
            name="Google Demo User",
            email=demo_email,
            google_id="demo-google-id",
            auth_provider="google",
            avatar_url="https://ui-avatars.com/api/?name=G+User&background=E8B92E&color=fff",
        )
        db.session.add(user)
        db.session.commit()
    login_user(user)
    flash("Logged in with Google (demo mode). Configure real OAuth in config.py.", "info")
    return redirect(url_for("locate"))


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("home"))


# ----------------------------------------------------------------------
# Locate page: browse by area, add shops, shop detail, ratings, feedback
# ----------------------------------------------------------------------
@app.route("/locate")
def locate():
    area_filter = request.args.get("area", "")
    category_filter = request.args.get("category", "")
    search_q = request.args.get("q", "")

    query = Shop.query.filter_by(status="approved")
    if area_filter:
        query = query.filter_by(area=area_filter)
    if category_filter:
        query = query.filter_by(category=category_filter)
    if search_q:
        like = f"%{search_q}%"
        query = query.filter(Shop.name.ilike(like))

    shops = query.order_by(Shop.area, Shop.name).all()

    shops_by_area = {}
    for area in PONDY_AREAS:
        shops_by_area[area] = [s for s in shops if s.area == area]

    return render_template(
        "locate.html",
        shops_by_area=shops_by_area,
        area_filter=area_filter,
        category_filter=category_filter,
        search_q=search_q,
    )


@app.route("/locate/add", methods=["GET", "POST"])
@login_required
def add_shop():
    if getattr(current_user, "is_admin", False):
        abort(403)  # admin manages listings from the admin dashboard, not this form

    max_photos = app.config["MAX_PHOTOS_PER_SHOP"]
    name_max = app.config["SHOP_NAME_MAX_LENGTH"]

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "")
        area = request.form.get("area", "")
        phone_number = request.form.get("phone_number", "").strip()
        description = request.form.get("description", "").strip()
        address = request.form.get("address", "").strip()
        map_link = request.form.get("map_link", "").strip()
        offer_text = request.form.get("offer_text", "").strip()
        image_files = [f for f in request.files.getlist("images") if f and f.filename]

        if not name or not category or not area or not phone_number:
            flash("Please fill all required fields.", "danger")
            return redirect(url_for("add_shop"))

        if len(name) > name_max:
            flash(f"Shop name must be {name_max} characters or fewer.", "danger")
            return redirect(url_for("add_shop"))

        if len(image_files) > max_photos:
            flash(f"You can upload a maximum of {max_photos} photos.", "danger")
            return redirect(url_for("add_shop"))

        shop = Shop(
            owner_id=current_user.id,
            name=name,
            category=category,
            area=area,
            phone_number=phone_number,
            description=description,
            address=address,
            map_link=map_link,
            offer_text=offer_text or None,
            status="pending",
        )
        db.session.add(shop)
        db.session.flush()  # get shop.id before committing images

        for position, file_storage in enumerate(image_files[:max_photos]):
            filename = save_shop_image(file_storage)
            if filename:
                db.session.add(ShopImage(shop_id=shop.id, filename=filename, position=position))

        db.session.commit()
        flash(
            f"'{shop.name}' has been submitted for review. It will appear on LocatePondy "
            f"once our admin verifies it.",
            "success",
        )
        return redirect(url_for("my_shops"))

    return render_template("add_shop.html", max_photos=max_photos, name_max=name_max)


@app.route("/shop/<int:shop_id>", methods=["GET"])
def shop_detail(shop_id):
    shop = Shop.query.get_or_404(shop_id)

    is_owner = current_user.is_authenticated and not getattr(current_user, "is_admin", False) \
        and shop.owner_id == current_user.id
    is_admin_viewer = current_user.is_authenticated and getattr(current_user, "is_admin", False)

    if shop.status != "approved" and not (is_owner or is_admin_viewer):
        abort(404)

    feedbacks = (
        Feedback.query.filter_by(shop_id=shop.id)
        .order_by(Feedback.created_at.desc())
        .all()
    )
    user_rating = None
    if current_user.is_authenticated and not getattr(current_user, "is_admin", False):
        r = Rating.query.filter_by(shop_id=shop.id, user_id=current_user.id).first()
        user_rating = r.stars if r else None

    return render_template(
        "shop_detail.html", shop=shop, feedbacks=feedbacks, user_rating=user_rating
    )


@app.route("/shop/<int:shop_id>/rate", methods=["POST"])
@login_required
def rate_shop(shop_id):
    if getattr(current_user, "is_admin", False):
        abort(403)
    shop = Shop.query.get_or_404(shop_id)
    if shop.status != "approved":
        abort(404)
    stars = int(request.form.get("stars", 0))
    if stars < 1 or stars > 5:
        flash("Invalid rating.", "danger")
        return redirect(url_for("shop_detail", shop_id=shop.id))

    existing = Rating.query.filter_by(shop_id=shop.id, user_id=current_user.id).first()
    if existing:
        existing.stars = stars
    else:
        db.session.add(Rating(shop_id=shop.id, user_id=current_user.id, stars=stars))
    db.session.commit()
    flash("Thanks for rating this shop!", "success")
    return redirect(url_for("shop_detail", shop_id=shop.id))


@app.route("/shop/<int:shop_id>/feedback", methods=["POST"])
@login_required
def add_feedback(shop_id):
    if getattr(current_user, "is_admin", False):
        abort(403)
    shop = Shop.query.get_or_404(shop_id)
    if shop.status != "approved":
        abort(404)
    message = request.form.get("message", "").strip()
    if message:
        db.session.add(Feedback(shop_id=shop.id, user_id=current_user.id, message=message))
        db.session.commit()
        flash("Feedback submitted!", "success")
    return redirect(url_for("shop_detail", shop_id=shop.id))


@app.route("/my-shops")
@login_required
def my_shops():
    if getattr(current_user, "is_admin", False):
        return redirect(url_for("admin_dashboard"))
    shops = Shop.query.filter_by(owner_id=current_user.id).order_by(Shop.created_at.desc()).all()
    return render_template("my_shops.html", shops=shops)


# ----------------------------------------------------------------------
# Admin: separate login + full edit/verify/delete access over all listings
# ----------------------------------------------------------------------
@app.route("/admin/login", methods=["GET", "POST"])
@limiter.limit("10 per hour")
def admin_login():
    if current_user.is_authenticated and getattr(current_user, "is_admin", False):
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        admin = Admin.query.filter_by(username=username).first()

        if admin and is_locked(admin):
            flash("Admin account temporarily locked due to repeated failed logins.", "danger")
            return render_template("admin/login.html")

        if admin and admin.check_password(password):
            reset_failed_attempts(admin)
            login_user(admin)
            flash("Welcome back, admin.", "success")
            return redirect(url_for("admin_dashboard"))

        if admin:
            register_failed_attempt(admin)
        flash("Invalid admin credentials.", "danger")

    return render_template("admin/login.html")


@app.route("/admin/logout")
@login_required
@admin_required
def admin_logout():
    logout_user()
    flash("Admin logged out.", "info")
    return redirect(url_for("home"))


@app.route("/admin")
@login_required
@admin_required
def admin_dashboard():
    status_filter = request.args.get("status", "pending")
    query = Shop.query
    if status_filter in ("pending", "approved", "rejected"):
        query = query.filter_by(status=status_filter)
    shops = query.order_by(Shop.created_at.desc()).all()
    counts = {
        "pending": Shop.query.filter_by(status="pending").count(),
        "approved": Shop.query.filter_by(status="approved").count(),
        "rejected": Shop.query.filter_by(status="rejected").count(),
    }
    return render_template("admin/dashboard.html", shops=shops, status_filter=status_filter, counts=counts)


@app.route("/admin/shop/<int:shop_id>/approve", methods=["POST"])
@login_required
@admin_required
def admin_approve_shop(shop_id):
    shop = Shop.query.get_or_404(shop_id)
    shop.status = "approved"
    shop.rejection_reason = None
    shop.reviewed_at = datetime.utcnow()
    db.session.commit()
    flash(f"'{shop.name}' verified and published.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/shop/<int:shop_id>/reject", methods=["POST"])
@login_required
@admin_required
def admin_reject_shop(shop_id):
    shop = Shop.query.get_or_404(shop_id)
    shop.status = "rejected"
    shop.rejection_reason = request.form.get("reason", "").strip() or "Did not meet listing guidelines."
    shop.reviewed_at = datetime.utcnow()
    db.session.commit()
    flash(f"'{shop.name}' rejected.", "info")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/shop/<int:shop_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def admin_edit_shop(shop_id):
    shop = Shop.query.get_or_404(shop_id)
    max_photos = app.config["MAX_PHOTOS_PER_SHOP"]
    name_max = app.config["SHOP_NAME_MAX_LENGTH"]

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "")
        area = request.form.get("area", "")
        phone_number = request.form.get("phone_number", "").strip()
        description = request.form.get("description", "").strip()
        address = request.form.get("address", "").strip()
        map_link = request.form.get("map_link", "").strip()
        offer_text = request.form.get("offer_text", "").strip()
        new_files = [f for f in request.files.getlist("images") if f and f.filename]
        remove_ids = set(request.form.getlist("remove_image_ids"))

        if not name or not category or not area or not phone_number:
            flash("Please fill all required fields.", "danger")
            return redirect(url_for("admin_edit_shop", shop_id=shop.id))

        if len(name) > name_max:
            flash(f"Shop name must be {name_max} characters or fewer.", "danger")
            return redirect(url_for("admin_edit_shop", shop_id=shop.id))

        remaining = [img for img in shop.images if str(img.id) not in remove_ids]
        removed = [img for img in shop.images if str(img.id) in remove_ids]

        if len(remaining) + len(new_files) > max_photos:
            flash(f"A shop can have at most {max_photos} photos.", "danger")
            return redirect(url_for("admin_edit_shop", shop_id=shop.id))

        for img in removed:
            path = os.path.join(app.config["UPLOAD_FOLDER"], img.filename)
            if os.path.exists(path):
                os.remove(path)
            db.session.delete(img)

        next_position = len(remaining)
        for file_storage in new_files[: max_photos - len(remaining)]:
            filename = save_shop_image(file_storage)
            if filename:
                db.session.add(ShopImage(shop_id=shop.id, filename=filename, position=next_position))
                next_position += 1

        shop.name = name
        shop.category = category
        shop.area = area
        shop.phone_number = phone_number
        shop.description = description
        shop.address = address
        shop.map_link = map_link
        shop.offer_text = offer_text or None

        db.session.commit()
        flash(f"'{shop.name}' has been updated.", "success")
        return redirect(url_for("shop_detail", shop_id=shop.id))

    return render_template("admin/edit_shop.html", shop=shop, max_photos=max_photos, name_max=name_max)


@app.route("/admin/shop/<int:shop_id>/delete", methods=["POST"])
@login_required
@admin_required
def admin_delete_shop(shop_id):
    shop = Shop.query.get_or_404(shop_id)
    delete_shop_images(shop)
    db.session.delete(shop)
    db.session.commit()
    flash("Shop listing removed.", "info")
    return redirect(url_for("admin_dashboard"))


# ----------------------------------------------------------------------
# Error handlers
# ----------------------------------------------------------------------
@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


@app.errorhandler(403)
def forbidden(e):
    return render_template("403.html"), 403


@app.errorhandler(429)
def rate_limited(e):
    flash("Too many attempts. Please wait a bit before trying again.", "danger")
    return render_template("403.html"), 429


# ----------------------------------------------------------------------
# CLI init / admin seeding
# ----------------------------------------------------------------------
def init_db():
    with app.app_context():
        db.create_all()
        seed_admin()
        print("Database initialized at:", app.config["SQLALCHEMY_DATABASE_URI"])


def seed_admin():
    """Create the default admin account on first run if none exists yet."""
    if Admin.query.count() > 0:
        return
    admin = Admin(username=app.config["ADMIN_USERNAME"])
    admin.set_password(app.config["ADMIN_PASSWORD"])
    db.session.add(admin)
    db.session.commit()
    print(
        f"\n*** Seeded admin account: username='{admin.username}'. "
        f"Log in at /admin/login and change the password if you used the default. ***\n"
    )


if __name__ == "__main__":
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    init_db()
    app.run(debug=True)
