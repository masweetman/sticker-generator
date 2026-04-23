# Sticker Generator

A web application for creating printable sticker sheets with AI-generated images. Users create named sheets with a configurable grid of sticker slots, type a prompt into each slot, and the app generates an image using an AI image provider. Completed sheets can be printed as a full 8.5×11 page.

## Features

- **AI image generation** — supports [OpenRouter](https://openrouter.ai) (server-side, requires API key) and [Pollinations.ai](https://pollinations.ai) (free, no key required)
- **Per-user provider preference** — each user can choose their preferred image provider independently of the site default
- **Configurable sticker sheets** — adjustable grid size (up to 10×10), named sheets, printable layout
- **Copy tools** — copy any generated sticker to a single cell or to every cell on the sheet at once
- **Admin panel** — manage users, configure the default provider, API keys, models, and the image bounding prompt

## Requirements

- Python 3.8+
- [pipenv](https://pipenv.pypa.io/)

## Local Installation

Clone the repository and install dependencies:

```bash
git clone <repo-url>
cd sticker-generator
pipenv install
```

Run the development server:

```bash
pipenv run flask --app run.py run
```

Open `http://localhost:5000` in your browser.

The database is created automatically on first run. A default admin account is seeded:

| Username | Password  |
|----------|-----------|
| `admin`  | `password1` |

**Change the admin password immediately after first login.**

## Configuration

All settings live in `app/configuration.py`. The important values to override for production are:

- `SECRET_KEY` — set to a long random string (or via the `SECRET_KEY` environment variable)
- `SQLALCHEMY_DATABASE_URI` — defaults to `sqlite:///app.db` inside the `instance/` directory

Image provider settings (API keys, default model, default provider, and the bounding prompt) are managed at runtime through the admin panel at `/admin/`.

## Database Migrations

The app uses Flask-Migrate. After pulling changes that include model updates:

```bash
flask --app run.py db upgrade
```

To create a new migration after changing `models.py`:

```bash
flask --app run.py db migrate -m "description"
flask --app run.py db upgrade
```

## Production Deployment (Linux / systemd)

The `deploy/` directory contains a systemd service unit for running the app with Gunicorn over a Unix socket.

### 1. Copy files to the server

```bash
rsync -av --exclude='.git' --exclude='instance/' . user@server:/srv/sticker-generator/
```

### 2. Create a virtual environment and install dependencies

```bash
cd /srv/sticker-generator
python3 -m venv venv
venv/bin/pip install pipenv
venv/bin/pipenv install --deploy --ignore-pipfile
# or simply:
venv/bin/pip install flask flask-admin flask-migrate flask-bootstrap \
    flask-cache flask-login flask-sqlalchemy flask-wtf requests werkzeug gunicorn
```

### 3. Set the secret key

Add a `SECRET_KEY` to the environment or create an `.env` file:

```bash
echo "SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')" \
    >> /srv/sticker-generator/.env
```

Then load it in `app/configuration.py` or export it in the systemd unit's `EnvironmentFile=`.

### 4. Apply database migrations

```bash
cd /srv/sticker-generator
FLASK_APP=run.py venv/bin/flask db upgrade
```

### 5. Install and start the systemd service

```bash
sudo cp deploy/sticker-generator.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sticker-generator
```

The app binds to `/run/sticker-generator/sticker-generator.sock`. The `RuntimeDirectory=sticker-generator` directive in the unit file creates this directory automatically with correct permissions.

### 6. Configure a reverse proxy (nginx example)

```nginx
server {
    listen 80;
    server_name example.com;

    location /static/ {
        alias /srv/sticker-generator/app/static/;
    }

    location / {
        proxy_pass http://unix:/run/sticker-generator/sticker-generator.sock;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Set up TLS with Certbot: `sudo certbot --nginx -d example.com`

### Useful service commands

```bash
sudo systemctl status sticker-generator   # check status
sudo systemctl restart sticker-generator  # restart after code changes
sudo journalctl -u sticker-generator -f   # follow logs
```
