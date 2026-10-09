import hashlib
import os
import re
import sqlite3
from contextlib import asynccontextmanager
from typing import Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from .auth import admin_user, create_session, current_user, hash_password, seed_users, verify_password
from .db import connect, migrate
from .metadata import detail as metadata_detail, key_for, known_link, search as metadata_search, valid_http_url

load_dotenv()

Kind = Literal['movie', 'series', 'game']
Status = Literal['want', 'active', 'done', 'paused']


class Login(BaseModel):
    username: str
    password: str


class ItemInput(BaseModel):
    kind: Kind
    title: str = Field(min_length=1, max_length=200)
    year: int | None = Field(default=None, ge=1880, le=2100)
    status: Status = 'want'
    description: str = Field(default='', max_length=10000)
    genres: str = Field(default='', max_length=500)
    image_url: str | None = None
    source_url: str | None = None
    source: Literal['tmdb', 'rawg'] | None = None
    external_id: str | None = None

    @field_validator('title')
    @classmethod
    def title_nonblank(cls, value):
        if not value.strip():
            raise ValueError('Title is required')
        return value.strip()

    @field_validator('image_url', 'source_url')
    @classmethod
    def safe_url(cls, value):
        if not valid_http_url(value):
            raise ValueError('Use an HTTP or HTTPS URL')
        return value


class ItemPatch(BaseModel):
    kind: Kind | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    year: int | None = Field(default=None, ge=1880, le=2100)
    status: Status | None = None
    description: str | None = Field(default=None, max_length=10000)
    genres: str | None = Field(default=None, max_length=500)
    image_url: str | None = None
    source_url: str | None = None

    @field_validator('image_url', 'source_url')
    @classmethod
    def safe_url(cls, value):
        if not valid_http_url(value):
            raise ValueError('Use an HTTP or HTTPS URL')
        return value


class NoteInput(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class LanguageInput(BaseModel):
    language: Literal['ru', 'en']


class UserInput(BaseModel):
    username: str = Field(pattern=r'^[a-zA-Z0-9_-]{3,32}$')
    password: str = Field(min_length=12)
    role: Literal['admin', 'friend'] = 'friend'


class UserPatch(BaseModel):
    password: str | None = Field(default=None, min_length=12)
    role: Literal['admin', 'friend'] | None = None


def rowdict(row):
    return dict(row) if row else None


def normalize_title(value: str):
    return re.sub(r'\s+', ' ', value.casefold().strip())


def item_or_404(db, item_id):
    row = db.execute('SELECT * FROM items WHERE id=?', (item_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Item not found')
    return dict(row)


def create_app():
    @asynccontextmanager
    async def lifespan(app):
        migrate()
        seed_users()
        yield

    app = FastAPI(title='Play & Watch API', lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=[os.getenv('FRONTEND_ORIGIN', 'http://127.0.0.1:5173')],
                       allow_credentials=True, allow_methods=['GET', 'POST', 'PATCH', 'DELETE'],
                       allow_headers=['Content-Type', 'X-Requested-With'])

    @app.middleware('http')
    async def require_custom_header(request: Request, call_next):
        if request.method in ('POST', 'PATCH', 'DELETE') and request.headers.get('X-Requested-With') != 'PlayWatch':
            return Response('Missing request header', status_code=403)
        return await call_next(request)

    @app.post('/api/login')
    def login(body: Login, response: Response):
        with connect() as db:
            row = db.execute('SELECT * FROM users WHERE username=?', (body.username,)).fetchone()
        if not row or not verify_password(body.password, row['password_hash']):
            raise HTTPException(401, 'Invalid credentials')
        token = create_session(row['id'])
        response.set_cookie('pw_session', token, httponly=True, secure=False, samesite='lax', max_age=14*86400)
        return {'id': row['id'], 'username': row['username'], 'role': row['role'], 'language': row['language']}

    @app.post('/api/logout')
    def logout(request: Request, response: Response):
        token = request.cookies.get('pw_session')
        if token:
            with connect() as db:
                db.execute('DELETE FROM sessions WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),))
        response.delete_cookie('pw_session')
        return {'ok': True}

    @app.get('/api/me')
    def me(user=Depends(current_user)):
        return user

    @app.patch('/api/me')
    def change_language(body: LanguageInput, user=Depends(current_user)):
        with connect() as db:
            db.execute('UPDATE users SET language=? WHERE id=?', (body.language, user['id']))
        return {**user, 'language': body.language}

    @app.get('/api/items')
    def list_items(kind: Kind | None = None, status: Status | None = None, q: str = '', user=Depends(current_user)):
        sql = 'SELECT * FROM items WHERE 1=1'
        args = []
        if kind:
            sql += ' AND kind=?'; args.append(kind)
        if status:
            sql += ' AND status=?'; args.append(status)
        if q.strip():
            sql += ' AND (title LIKE ? OR genres LIKE ?)'; args.extend([f'%{q.strip()}%'] * 2)
        sql += ' ORDER BY updated_at DESC, id DESC'
        with connect() as db:
            return [dict(row) for row in db.execute(sql, args).fetchall()]

    @app.get('/api/items/random')
    def random_item(kind: Kind | None = None, user=Depends(current_user)):
        sql = 'SELECT * FROM items WHERE status=?'
        args = ['want']
        if kind == 'movie':
            sql += ' AND kind IN (?, ?)'
            args.extend(['movie', 'series'])
        elif kind:
            sql += ' AND kind=?'
            args.append(kind)
        sql += ' ORDER BY RANDOM() LIMIT 1'
        with connect() as db:
            row = db.execute(sql, args).fetchone()
        if not row:
            raise HTTPException(404, 'No wanted items')
        return dict(row)

    @app.get('/api/items/{item_id}')
    def get_item(item_id: int, user=Depends(current_user)):
        with connect() as db:
            item = item_or_404(db, item_id)
            notes = [dict(row) for row in db.execute('''SELECT notes.id,notes.text,notes.created_at,COALESCE(users.username,'Deleted user') AS username
                FROM notes LEFT JOIN users ON users.id=notes.user_id WHERE item_id=? ORDER BY notes.id DESC''', (item_id,))]
            history = [dict(row) for row in db.execute('''SELECT status_events.status,status_events.created_at,COALESCE(users.username,'Deleted user') AS username
                FROM status_events LEFT JOIN users ON users.id=status_events.user_id WHERE item_id=? ORDER BY status_events.id''', (item_id,))]
        if item['source'] and item['external_id']:
            localized = metadata_detail(item['kind'], item['source'], item['external_id'], user['language'])
            if localized and localized.get('description'):
                item['description'] = localized['description']
        return {**item, 'notes': notes, 'history': history}

    @app.post('/api/items', status_code=201)
    def add_item(body: ItemInput, user=Depends(current_user)):
        data = body.model_dump()
        if data['source'] == 'tmdb' and data['kind'] == 'game' or data['source'] == 'rawg' and data['kind'] != 'game':
            raise HTTPException(422, 'Source does not match kind')
        try:
            with connect() as db:
                possible_duplicate = db.execute('''SELECT id FROM items WHERE kind=? AND normalized_title=?
                    AND (year=? OR year IS NULL OR ? IS NULL) LIMIT 1''',
                    (data['kind'], normalize_title(data['title']), data['year'], data['year'])).fetchone()
                if possible_duplicate:
                    raise HTTPException(409, 'This title is already in the collection')
                cursor = db.execute('''INSERT INTO items(kind,title,normalized_title,year,status,description,genres,image_url,
                    source_url,source,external_id,created_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (data['kind'], data['title'], normalize_title(data['title']), data['year'], data['status'],
                     data['description'], data['genres'], data['image_url'], data['source_url'], data['source'],
                     data['external_id'], user['id']))
                item_id = cursor.lastrowid
                db.execute('INSERT INTO status_events(item_id,user_id,status) VALUES (?,?,?)', (item_id, user['id'], data['status']))
                return item_or_404(db, item_id)
        except sqlite3.IntegrityError:
            raise HTTPException(409, 'This title is already in the collection')

    @app.patch('/api/items/{item_id}')
    def edit_item(item_id: int, body: ItemPatch, user=Depends(current_user)):
        data = body.model_dump(exclude_unset=True)
        with connect() as db:
            old = item_or_404(db, item_id)
            if user['role'] != 'admin' and set(data) != {'status'}:
                raise HTTPException(403, 'Administrator only')
            if not data:
                return old
            if 'title' in data:
                if not data['title'].strip():
                    raise HTTPException(422, 'Title is required')
                data['title'] = data['title'].strip()
                data['normalized_title'] = normalize_title(data['title'])
            effective_kind = data.get('kind', old['kind'])
            effective_title = data.get('normalized_title', old['normalized_title'])
            effective_year = data.get('year', old['year'])
            possible_duplicate = db.execute('''SELECT id FROM items WHERE id<>? AND kind=? AND normalized_title=?
                AND (year=? OR year IS NULL OR ? IS NULL) LIMIT 1''',
                (item_id, effective_kind, effective_title, effective_year, effective_year)).fetchone()
            if possible_duplicate:
                raise HTTPException(409, 'This title is already in the collection')
            assignments = ','.join(f'{key}=?' for key in data)
            try:
                db.execute(f'UPDATE items SET {assignments},updated_at=CURRENT_TIMESTAMP WHERE id=?', (*data.values(), item_id))
            except sqlite3.IntegrityError:
                raise HTTPException(409, 'This title is already in the collection')
            if 'status' in data and data['status'] != old['status']:
                db.execute('INSERT INTO status_events(item_id,user_id,status) VALUES (?,?,?)', (item_id, user['id'], data['status']))
            return item_or_404(db, item_id)

    @app.delete('/api/items/{item_id}', status_code=204)
    def delete_item(item_id: int, user=Depends(admin_user)):
        with connect() as db:
            item_or_404(db, item_id)
            db.execute('DELETE FROM items WHERE id=?', (item_id,))

    @app.post('/api/items/{item_id}/notes', status_code=201)
    def add_note(item_id: int, body: NoteInput, user=Depends(current_user)):
        if not body.text.strip():
            raise HTTPException(422, 'Note is required')
        with connect() as db:
            item_or_404(db, item_id)
            cursor = db.execute('INSERT INTO notes(item_id,user_id,text) VALUES (?,?,?)', (item_id, user['id'], body.text.strip()))
            return {'id': cursor.lastrowid, 'text': body.text.strip(), 'username': user['username']}

    @app.get('/api/metadata/search')
    def search_metadata(kind: Kind, query: str = Query(min_length=2, max_length=100), user=Depends(current_user)):
        return metadata_search(kind, query, user['language'])

    @app.get('/api/metadata/link')
    def resolve_link(url: str, user=Depends(current_user)):
        if not valid_http_url(url) or not url:
            raise HTTPException(422, 'Invalid URL')
        match = known_link(url)
        if not match:
            return {'available': False, 'item': None, 'reason': 'unknown_link', 'message': 'Unknown link; use manual entry'}
        kind, source, external_id = match
        item = metadata_detail(kind, source, external_id, user['language'])
        return {'available': bool(item), 'item': item, 'reason': None if item else ('missing_key' if not key_for(kind) else 'upstream_error'), 'message': '' if item else 'Metadata unavailable; use manual entry'}

    @app.get('/api/users')
    def list_users(user=Depends(admin_user)):
        with connect() as db:
            return [dict(row) for row in db.execute('SELECT id,username,role,language FROM users ORDER BY id')]

    @app.post('/api/users', status_code=201)
    def add_user(body: UserInput, user=Depends(admin_user)):
        try:
            with connect() as db:
                cursor = db.execute('INSERT INTO users(username,password_hash,role) VALUES (?,?,?)',
                                    (body.username, hash_password(body.password), body.role))
                return {'id': cursor.lastrowid, 'username': body.username, 'role': body.role, 'language': 'ru'}
        except sqlite3.IntegrityError:
            raise HTTPException(409, 'Username already exists')

    @app.patch('/api/users/{user_id}')
    def edit_user(user_id: int, body: UserPatch, user=Depends(admin_user)):
        with connect() as db:
            target = db.execute('SELECT id,username,role,language FROM users WHERE id=?', (user_id,)).fetchone()
            if not target:
                raise HTTPException(404, 'User not found')
            if body.role and body.role != target['role']:
                if user_id == user['id']:
                    raise HTTPException(422, 'Cannot change your own role')
                db.execute('UPDATE users SET role=? WHERE id=?', (body.role, user_id))
            if body.password:
                db.execute('UPDATE users SET password_hash=? WHERE id=?', (hash_password(body.password), user_id))
                db.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
            return rowdict(db.execute('SELECT id,username,role,language FROM users WHERE id=?', (user_id,)).fetchone())

    @app.delete('/api/users/{user_id}', status_code=204)
    def delete_user(user_id: int, user=Depends(admin_user)):
        if user_id == user['id']:
            raise HTTPException(422, 'Cannot delete yourself')
        with connect() as db:
            target = db.execute('SELECT id FROM users WHERE id=?', (user_id,)).fetchone()
            if not target:
                raise HTTPException(404, 'User not found')
            db.execute('UPDATE items SET created_by=NULL WHERE created_by=?', (user_id,))
            db.execute('DELETE FROM users WHERE id=?', (user_id,))

    return app


app = create_app()
