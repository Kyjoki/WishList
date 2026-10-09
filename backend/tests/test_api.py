import os
import pytest
from fastapi.testclient import TestClient


def client(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_PATH', str(tmp_path / 'test.db'))
    monkeypatch.setenv('TMDB_API_KEY', '')
    monkeypatch.setenv('RAWG_API_KEY', '')
    monkeypatch.setenv('ADMIN_USERNAME', 'admin')
    monkeypatch.setenv('ADMIN_PASSWORD', 'admin-password-long')
    monkeypatch.setenv('FRIEND_USERNAME', 'friend')
    monkeypatch.setenv('FRIEND_PASSWORD', 'friend-password-long')
    from app.main import create_app
    return TestClient(create_app())


def login(c, username='admin', password='admin-password-long'):
    response = c.post('/api/login', json={'username': username, 'password': password}, headers={'X-Requested-With': 'PlayWatch'})
    assert response.status_code == 200


def test_seed_login_and_private_collection(tmp_path, monkeypatch):
    with client(tmp_path, monkeypatch) as c:
        assert c.get('/api/items').status_code == 401
        login(c)
        assert c.get('/api/me').json()['role'] == 'admin'
        assert c.get('/api/items').json() == []


def test_create_duplicate_and_status_history(tmp_path, monkeypatch):
    with client(tmp_path, monkeypatch) as c:
        login(c)
        payload = {'kind': 'movie', 'title': 'Arrival', 'year': 2016, 'status': 'want', 'source': 'tmdb', 'external_id': '329865'}
        first = c.post('/api/items', json=payload, headers={'X-Requested-With': 'PlayWatch'})
        assert first.status_code == 201
        duplicate = c.post('/api/items', json=payload, headers={'X-Requested-With': 'PlayWatch'})
        assert duplicate.status_code == 409
        item_id = first.json()['id']
        change = c.patch(f'/api/items/{item_id}', json={'status': 'done'}, headers={'X-Requested-With': 'PlayWatch'})
        assert change.status_code == 200
        detail = c.get(f'/api/items/{item_id}').json()
        assert [e['status'] for e in detail['history']] == ['want', 'done']


def test_friend_notes_but_cannot_edit_or_manage_users(tmp_path, monkeypatch):
    with client(tmp_path, monkeypatch) as c:
        login(c)
        item_id = c.post('/api/items', json={'kind': 'game', 'title': 'Portal 2', 'status': 'want'}, headers={'X-Requested-With': 'PlayWatch'}).json()['id']
        c.post('/api/logout', headers={'X-Requested-With': 'PlayWatch'})
        login(c, 'friend', 'friend-password-long')
        assert c.post(f'/api/items/{item_id}/notes', json={'text': 'Play co-op'}, headers={'X-Requested-With': 'PlayWatch'}).status_code == 201
        assert c.patch(f'/api/items/{item_id}', json={'title': 'Other'}, headers={'X-Requested-With': 'PlayWatch'}).status_code == 403
        assert c.get('/api/users').status_code == 403


def test_invalid_link_and_manual_fallback(tmp_path, monkeypatch):
    with client(tmp_path, monkeypatch) as c:
        login(c)
        bad = c.post('/api/items', json={'kind': 'movie', 'title': 'A', 'status': 'want', 'source_url': 'javascript:alert(1)'}, headers={'X-Requested-With': 'PlayWatch'})
        assert bad.status_code == 422
        response = c.get('/api/metadata/search', params={'kind': 'movie', 'query': 'Arrival'})
        assert response.status_code == 200
        assert response.json()['available'] is False
        assert response.json()['reason'] == 'missing_key'


def test_language_and_random(tmp_path, monkeypatch):
    with client(tmp_path, monkeypatch) as c:
        login(c)
        c.patch('/api/me', json={'language': 'en'}, headers={'X-Requested-With': 'PlayWatch'})
        assert c.get('/api/me').json()['language'] == 'en'
        c.post('/api/items', json={'kind': 'game', 'title': 'Hades', 'status': 'want'}, headers={'X-Requested-With': 'PlayWatch'})
        assert c.get('/api/items/random', params={'kind': 'game'}).json()['title'] == 'Hades'


def test_random_watch_includes_series(tmp_path, monkeypatch):
    with client(tmp_path, monkeypatch) as c:
        login(c)
        headers = {'X-Requested-With': 'PlayWatch'}
        c.post('/api/items', json={'kind': 'series', 'title': 'Friends', 'status': 'want'}, headers=headers)
        c.post('/api/items', json={'kind': 'game', 'title': 'Hades', 'status': 'want'}, headers=headers)

        response = c.get('/api/items/random', params={'kind': 'movie'})
        assert response.status_code == 200
        assert response.json()['title'] == 'Friends'


def test_random_respects_search_genre_and_exclusions(tmp_path, monkeypatch):
    with client(tmp_path, monkeypatch) as c:
        login(c)
        headers = {'X-Requested-With': 'PlayWatch'}
        for item in [
            {'kind': 'movie', 'title': 'Funny Moon', 'genres': 'Comedy', 'status': 'want'},
            {'kind': 'series', 'title': 'Funny Friends', 'genres': 'Comedy', 'status': 'want'},
            {'kind': 'movie', 'title': 'Serious Moon', 'genres': 'Drama', 'status': 'want'},
            {'kind': 'game', 'title': 'Funny Quest', 'genres': 'Comedy', 'status': 'want'},
            {'kind': 'movie', 'title': 'Funny Done', 'genres': 'Comedy', 'status': 'done'},
        ]:
            assert c.post('/api/items', json=item, headers=headers).status_code == 201

        first = c.get('/api/items/random', params={'kind': 'movie', 'genre': 'Comedy', 'q': 'Funny'})
        assert first.status_code == 200
        second = c.get('/api/items/random', params={'kind': 'movie', 'genre': 'Comedy', 'q': 'Funny', 'exclude': first.json()['id']})
        assert second.status_code == 200
        assert {first.json()['title'], second.json()['title']} == {'Funny Moon', 'Funny Friends'}
        exhausted = c.get('/api/items/random', params=[('kind', 'movie'), ('genre', 'Comedy'), ('q', 'Funny'),
                                                         ('exclude', first.json()['id']), ('exclude', second.json()['id'])])
        assert exhausted.status_code == 404
        assert c.get('/api/items/random', params={'kind': 'game', 'genre': 'Comedy'}).json()['title'] == 'Funny Quest'
        c.post('/api/items', json={'kind': 'series', 'title': 'Луна', 'genres': 'Комедия', 'status': 'want'}, headers=headers)
        localized = c.get('/api/items/random', params={'kind': 'movie', 'genre': 'комедия', 'q': 'ЛУНА'})
        assert localized.status_code == 200
        assert localized.json()['title'] == 'Луна'


def test_friends_share_series_progress(tmp_path, monkeypatch):
    with client(tmp_path, monkeypatch) as c:
        login(c)
        headers = {'X-Requested-With': 'PlayWatch'}
        series_id = c.post('/api/items', json={'kind': 'series', 'title': 'Friends'}, headers=headers).json()['id']
        movie_id = c.post('/api/items', json={'kind': 'movie', 'title': 'Moon'}, headers=headers).json()['id']
        c.post('/api/logout', headers=headers)
        login(c, 'friend', 'friend-password-long')

        updated = c.patch(f'/api/items/{series_id}/progress', json={'season_number': 2, 'episode_number': 5}, headers=headers)
        assert updated.status_code == 200
        assert (updated.json()['season_number'], updated.json()['episode_number']) == (2, 5)
        assert c.get(f'/api/items/{series_id}').json()['episode_number'] == 5
        listed_series = next(item for item in c.get('/api/items').json() if item['id'] == series_id)
        assert listed_series['season_number'] == 2
        assert c.patch(f'/api/items/{series_id}/progress', json={'season_number': 0, 'episode_number': 5}, headers=headers).status_code == 422
        assert c.patch(f'/api/items/{movie_id}/progress', json={'season_number': 1, 'episode_number': 1}, headers=headers).status_code == 422
        cleared = c.patch(f'/api/items/{series_id}/progress', json={'season_number': None, 'episode_number': None}, headers=headers)
        assert cleared.status_code == 200
        assert cleared.json()['season_number'] is None
        assert cleared.json()['episode_number'] is None


def test_admin_can_manage_user_without_losing_activity(tmp_path, monkeypatch):
    with client(tmp_path, monkeypatch) as c:
        login(c)
        item_id = c.post('/api/items', json={'kind': 'movie', 'title': 'Moon', 'status': 'want'}, headers={'X-Requested-With': 'PlayWatch'}).json()['id']
        created = c.post('/api/users', json={'username': 'guest', 'password': 'guest-password-long', 'role': 'friend'}, headers={'X-Requested-With': 'PlayWatch'})
        assert created.status_code == 201
        guest_id = created.json()['id']
        c.post('/api/logout', headers={'X-Requested-With': 'PlayWatch'})
        login(c, 'guest', 'guest-password-long')
        assert c.post(f'/api/items/{item_id}/notes', json={'text': 'Worth a watch'}, headers={'X-Requested-With': 'PlayWatch'}).status_code == 201
        c.post('/api/logout', headers={'X-Requested-With': 'PlayWatch'})
        login(c)
        assert c.delete(f'/api/users/{guest_id}', headers={'X-Requested-With': 'PlayWatch'}).status_code == 204
        assert c.get(f'/api/items/{item_id}').json()['notes'][0]['text'] == 'Worth a watch'


def test_mutations_require_custom_header_and_manual_duplicates(tmp_path, monkeypatch):
    with client(tmp_path, monkeypatch) as c:
        assert c.post('/api/login', json={'username': 'admin', 'password': 'admin-password-long'}).status_code == 403
        login(c)
        first = c.post('/api/items', json={'kind': 'game', 'title': '  Portal   2 ', 'year': 2011}, headers={'X-Requested-With': 'PlayWatch'})
        assert first.status_code == 201
        again = c.post('/api/items', json={'kind': 'game', 'title': 'portal 2', 'year': 2011}, headers={'X-Requested-With': 'PlayWatch'})
        assert again.status_code == 409


def test_unknown_year_does_not_allow_same_title_again(tmp_path, monkeypatch):
    with client(tmp_path, monkeypatch) as c:
        login(c)
        first = c.post('/api/items', json={'kind': 'movie', 'title': 'Solaris'}, headers={'X-Requested-With': 'PlayWatch'})
        assert first.status_code == 201
        again = c.post('/api/items', json={'kind': 'movie', 'title': '  SOLARIS  ', 'year': 1972}, headers={'X-Requested-With': 'PlayWatch'})
        assert again.status_code == 409


def test_example_password_must_be_changed_before_start(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_PATH', str(tmp_path / 'unconfigured.db'))
    monkeypatch.setenv('ADMIN_USERNAME', 'admin')
    monkeypatch.setenv('ADMIN_PASSWORD', 'replace-with-a-long-unique-password')
    monkeypatch.setenv('FRIEND_USERNAME', 'friend')
    monkeypatch.setenv('FRIEND_PASSWORD', 'friend-password-long')
    from app.auth import seed_users
    from app.db import migrate
    migrate()
    with pytest.raises(RuntimeError, match='ADMIN_PASSWORD'):
        seed_users()
