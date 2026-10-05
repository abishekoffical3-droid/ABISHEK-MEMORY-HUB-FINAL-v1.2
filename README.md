# ABISHEK MEMORY HUB — V2

A polished Flask + SQLite personal memory hub with a premium light visual system.

## Included
- Animated welcome/home experience
- Photos, videos, voice/audio, stories and documents
- Albums
- Private memories
- Likes and comments
- Contact inbox
- Admin login + dashboard
- Notebook
- Site settings
- Responsive mobile layout
- ABISHEK / AB DEV STUDIO branding
- Secure password hashes via environment variables

## Run
1. Create a virtual environment:
   `python -m venv .venv`
2. Activate it.
3. Install:
   `pip install -r requirements.txt`
4. Set environment variables:
   - `SESSION_SECRET`
   - `ADMIN_USERNAME`
   - `ADMIN_PASSWORD_HASH`
   - `PRIVATE_PASSWORD_HASH`

Generate a password hash:
`python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash(input('Password: ')))"`

5. Start:
   `python app.py`
6. Open:
   `http://127.0.0.1:5000`

## Important
Do not place a real password directly in source code. Use a generated hash in `ADMIN_PASSWORD_HASH` and `PRIVATE_PASSWORD_HASH`.
