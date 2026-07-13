# 📍 LocatePondy

A full-stack Python (Flask) web app to discover, list, and rate food shops across Puducherry (Pondicherry) — organized area by area, in a single-file build.

**Everything — backend routes, database models, and the entire frontend (HTML + CSS + JS) — lives in one file: `app.py`.** No `templates/` or `static/` folders required to run it.

## Features

- **Home page** — hero banner, live stats, newest & most-rated verified shops
- **About page** — mission and feature overview
- **Login** — Phone number + OTP (demo), Email/password, Google login (demo stub, ready for real OAuth)
- **Register** — email/password account creation
- **Locate page** — the core directory:
  - Every Pondicherry area (White Town, Heritage Town, Lawspet, Kalapet, Ariyankuppam, Villianur, Ozhukarai, Auroville & more)
  - Shops grouped area-wise, filterable by area/category, searchable by name
  - Logged-in users can add a shop with up to 5 photos, category, area, phone, description, address, an optional scrolling offer banner, and a Google Maps link — submitted for admin verification
  - Shop detail page: photo carousel, offer marquee, 5-star ratings, feedback/reviews, embedded map link
- **My Shops** — track the verification status of shops you've submitted
- **Admin dashboard** (`/admin`) — approve, reject (with reason), edit, or delete any listing, separate admin login at `/admin/login`

### Security

- CSRF protection on every form (Flask-WTF)
- Rate limiting on login, registration, and admin login (Flask-Limiter)
- Account lockout after 5 failed logins (15-minute cooldown)
- Expiring, attempt-capped OTPs
- Minimum password strength rule on registration
- Secure session cookie flags, with a startup warning if `SECRET_KEY` is still the default

## Tech Stack

- **Backend:** Python, Flask, Flask-SQLAlchemy, Flask-Login, Flask-WTF, Flask-Limiter
- **Database:** SQLite (file-based, zero setup) — swap `DATABASE_URL` for Postgres/MySQL in production
- **Frontend:** Jinja2 templates + vanilla CSS + vanilla JS, all inlined inside `app.py` via a Jinja `DictLoader` — no build step
- **Auth:** Werkzeug password hashing, session-based OTP flow, Google OAuth stub, separate Admin login

## Getting Started

```bash
git clone https://github.com/YOUR_USERNAME/locatepondy.git
cd locatepondy
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5000**. The SQLite database (`locatepondy.db`) and tables are created automatically on first run, and a default admin account is seeded.

### Default admin login

```
ADMIN_USERNAME=admin
ADMIN_PASSWORD=ChangeMe@123
```

**Set your own values before running anywhere but local dev:**

```bash
export ADMIN_USERNAME=your_admin_name
export ADMIN_PASSWORD='something-long-and-random'
export SECRET_KEY='another-long-random-string'
python app.py
```

Log in at `/admin/login`. From the dashboard you can approve/reject pending listings and edit or delete any shop.

## Project Structure

```
locatepondy/
├── app.py              # Routes, models, config, and the entire frontend
│                        # (templates + CSS + JS), all in one file
├── requirements.txt
└── README.md
```

At runtime, `app.py` creates two things next to itself automatically:
- `locatepondy.db` — the SQLite database
- `static/uploads/` — folder for shop images uploaded through the app

Neither should be committed to git (see `.gitignore` below).

## Recommended `.gitignore`

```
__pycache__/
*.pyc
locatepondy.db
static/uploads/*
!static/uploads/.gitkeep
.env
```

## Connecting Real Services (Production Checklist)

The app ships with demo-mode stand-ins for two things that normally require paid third-party accounts:

**1. Phone OTP** — currently a random 6-digit code shown via flash message. In `app.py`'s `login()` view, replace it with a real SMS gateway call, e.g. Twilio Verify or MSG91.

**2. Google Sign-In** — currently a demo auto-login. To enable real OAuth:
1. `pip install authlib`
2. Create OAuth 2.0 credentials at the [Google Cloud Console](https://console.cloud.google.com/)
3. Set `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` as environment variables
4. Register an Authlib OAuth client and replace `/login/google` with the real authorize-redirect + callback flow

**Before deploying anywhere real:**
- Set a strong `SECRET_KEY` and `ADMIN_PASSWORD` via environment variables (never hardcode them)
- Set `FORCE_HTTPS=1` once served over HTTPS
- Switch `SQLALCHEMY_DATABASE_URI` to Postgres/MySQL for concurrent users
- Configure a persistent Flask-Limiter storage backend (e.g. Redis)
- Serve behind Gunicorn/uWSGI + Nginx, not `app.run()`
- Store uploaded images in S3/Cloud Storage instead of the local filesystem

## Areas Covered

White Town, Heritage Town (Tamil Quarter), Muthialpet, Lawspet, Reddiarpalayam, Kalapet, Thattanchavady, Ariyankuppam, Ozhukarai, Villianur, Mudaliarpet, Uppalam, Nellithope, Auroville & Suburbs, Karuvadikuppam.

(Edit the `PONDY_AREAS` list near the top of `app.py` to customize.)

## Categories

South Indian, North Indian, French/Continental, Cafe & Bakery, Street Food, Sea Food, Fast Food, Ice Cream & Desserts, Juice & Beverages, Bar & Restaurant, Vegan/Healthy, Sweets & Snacks, Other.

(Edit the `SHOP_CATEGORIES` list in `app.py` to customize.)
