import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request

from .db import connect


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f'scrypt${salt.hex()}${digest.hex()}'


def verify_password(password: str, encoded: str) -> bool:
    try:
        _, salt, digest = encoded.split('$')
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1)
        return hmac.compare_digest(actual, bytes.fromhex(digest))
    except (ValueError, TypeError):
        return False


def seed_users():
    with connect() as db:
        for role, prefix, default_name in [('admin', 'ADMIN', 'admin'), ('friend', 'FRIEND', 'friend')]:
            username = os.getenv(f'{prefix}_USERNAME', default_name).strip()
            password = os.getenv(f'{prefix}_PASSWORD', '')
            if not username or len(password) < 12 or password.startswith('replace-with-'):
                raise RuntimeError(f'Set {prefix}_USERNAME and {prefix}_PASSWORD (at least 12 characters) in backend/.env')
            if not db.execute('SELECT 1 FROM users WHERE role=?', (role,)).fetchone():
                db.execute('INSERT INTO users(username,password_hash,role) VALUES (?,?,?)', (username, hash_password(password), role))


def current_user(request: Request):
    token = request.cookies.get('pw_session')
    if not token:
        raise HTTPException(401, 'Authentication required')
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with connect() as db:
        row = db.execute('''SELECT users.id, username, role, language FROM sessions
            JOIN users ON users.id=sessions.user_id WHERE token_hash=? AND expires_at>?''',
            (token_hash, datetime.now(timezone.utc).isoformat())).fetchone()
    if not row:
        raise HTTPException(401, 'Session expired')
    return dict(row)


def admin_user(request: Request):
    user = current_user(request)
    if user['role'] != 'admin':
        raise HTTPException(403, 'Administrator only')
    return user


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expiry = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()
    with connect() as db:
        db.execute('INSERT INTO sessions(token_hash,user_id,expires_at) VALUES (?,?,?)',
                   (hashlib.sha256(token.encode()).hexdigest(), user_id, expiry))
    return token
