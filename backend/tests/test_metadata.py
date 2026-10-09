from app.metadata import known_link, normalize_rawg, normalize_tmdb, valid_http_url


def test_known_links_are_parsed_without_fetching_untrusted_hosts():
    assert known_link('https://www.themoviedb.org/tv/95396-severance') == ('series', 'tmdb', '95396')
    assert known_link('https://rawg.io/games/hades-2') == ('game', 'rawg', 'hades-2')
    assert known_link('https://notrawg.io/games/hades-2') is None
    assert not valid_http_url('file:///etc/passwd')
    assert not valid_http_url('https://user:password@example.com')


def test_provider_results_include_attribution_links_and_safe_missing_images():
    movie = normalize_tmdb({'id': 1, 'title': 'Dune', 'release_date': '2021-09-15', 'overview': 'A desert world.'}, 'movie')
    game = normalize_rawg({'id': 2, 'slug': 'hades', 'name': 'Hades', 'released': '2020-09-17', 'description_raw': 'Escape <b>the underworld</b>.'})
    assert movie['year'] == 2021 and movie['image_url'] is None
    assert movie['source_url'] == 'https://www.themoviedb.org/movie/1'
    assert game['description'] == 'Escape the underworld.'
    assert game['source_url'] == 'https://rawg.io/games/hades'
