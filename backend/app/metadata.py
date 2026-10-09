import os
import re
from urllib.parse import urlparse

import httpx


def valid_http_url(value: str | None) -> bool:
    if not value:
        return True
    parsed = urlparse(value)
    return parsed.scheme in ('http', 'https') and bool(parsed.netloc) and not parsed.username and not parsed.password


def known_link(value: str):
    parsed = urlparse(value)
    host = (parsed.hostname or '').lower()
    path = parsed.path.rstrip('/')
    if host in ('themoviedb.org', 'www.themoviedb.org'):
        match = re.fullmatch(r'/(movie|tv)/(\d+)(?:-[^/]*)?', path)
        if match:
            return ('series' if match.group(1) == 'tv' else 'movie', 'tmdb', match.group(2))
    if host in ('rawg.io', 'www.rawg.io'):
        match = re.fullmatch(r'/games/([a-zA-Z0-9-]+)', path)
        if match:
            return ('game', 'rawg', match.group(1))
    return None


def key_for(kind: str) -> str:
    return os.getenv('RAWG_API_KEY' if kind == 'game' else 'TMDB_API_KEY', '')


def normalize_tmdb(row: dict, kind: str) -> dict:
    item_id = str(row['id'])
    date = row.get('release_date' if kind == 'movie' else 'first_air_date') or ''
    return {
        'kind': kind, 'title': row.get('title' if kind == 'movie' else 'name') or '',
        'year': int(date[:4]) if len(date) >= 4 and date[:4].isdigit() else None,
        'description': row.get('overview') or '',
        'genres': ', '.join(g['name'] for g in row.get('genres', [])),
        'image_url': 'https://image.tmdb.org/t/p/w500' + row['poster_path'] if row.get('poster_path') else None,
        'source_url': f"https://www.themoviedb.org/{'tv' if kind == 'series' else 'movie'}/{item_id}",
        'source': 'tmdb', 'external_id': item_id,
    }


def normalize_rawg(row: dict) -> dict:
    date = row.get('released') or ''
    item_id = str(row['id'])
    return {
        'kind': 'game', 'title': row.get('name') or '',
        'year': int(date[:4]) if len(date) >= 4 and date[:4].isdigit() else None,
        'description': re.sub('<[^>]+>', '', row.get('description_raw') or ''),
        'genres': ', '.join(g['name'] for g in row.get('genres', [])),
        'image_url': row.get('background_image'),
        'source_url': f"https://rawg.io/games/{row.get('slug') or item_id}",
        'source': 'rawg', 'external_id': item_id,
    }


def search(kind: str, query: str, language: str):
    key = key_for(kind)
    if not key:
        return {'available': False, 'results': [], 'reason': 'missing_key', 'message': 'API key is not configured'}
    try:
        with httpx.Client(timeout=7) as client:
            if kind == 'game':
                result = client.get('https://api.rawg.io/api/games', params={'key': key, 'search': query, 'page_size': 8})
                result.raise_for_status()
                rows = [normalize_rawg(row) for row in result.json().get('results', [])]
            else:
                path = 'movie' if kind == 'movie' else 'tv'
                result = client.get(f'https://api.themoviedb.org/3/search/{path}', params={
                    'api_key': key, 'query': query, 'language': 'ru-RU' if language == 'ru' else 'en-US',
                    'include_adult': 'false'})
                result.raise_for_status()
                rows = [normalize_tmdb(row, kind) for row in result.json().get('results', [])[:8]]
        return {'available': True, 'results': rows, 'reason': None, 'message': ''}
    except (httpx.HTTPError, ValueError, KeyError):
        return {'available': False, 'results': [], 'reason': 'upstream_error', 'message': 'Metadata service unavailable'}


def detail(kind: str, source: str, external_id: str, language: str):
    key = key_for(kind)
    if not key:
        return None
    try:
        with httpx.Client(timeout=7) as client:
            if source == 'rawg' and kind == 'game':
                response = client.get(f'https://api.rawg.io/api/games/{external_id}', params={'key': key})
                response.raise_for_status()
                return normalize_rawg(response.json())
            if source == 'tmdb' and kind in ('movie', 'series') and external_id.isdigit():
                path = 'movie' if kind == 'movie' else 'tv'
                response = client.get(f'https://api.themoviedb.org/3/{path}/{external_id}', params={
                    'api_key': key, 'language': 'ru-RU' if language == 'ru' else 'en-US'})
                response.raise_for_status()
                return normalize_tmdb(response.json(), kind)
    except (httpx.HTTPError, ValueError, KeyError):
        return None
    return None
