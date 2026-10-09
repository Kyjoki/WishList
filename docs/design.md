# Play & Watch: design

Two people share one collection of movies, series and games. Both authenticated users can add entries and notes through the management area. The administrator can additionally edit/delete entries and manage users. The public-facing collection is private to those two accounts.

Visual direction follows the supplied `play-and-watch-design.html`: graphite background, violet navigation and filters, cyan random button, poster-first cards, a compact mobile layout, and a management dashboard with counts and an entry list.

FastAPI owns authentication, SQLite, migrations, validation and metadata integrations. React/TypeScript owns the responsive dark interface, search, filtering, detail pages and management forms. The server fetches TMDB and RAWG with secrets from environment variables. Manual entry remains available for every content type. Stored external IDs and normalized title/year checks prevent duplicates.

SQLite schema has users, sessions, items, notes and status_events. Migrations run on server startup. Initial admin and friend passwords come from environment variables. Passwords use salted scrypt. Opaque session tokens are kept hashed in the database and delivered by HttpOnly cookies. Local CORS accepts only configured frontend origin. JSON mutation requests require a custom header.

Metadata searches return multiple candidate records. Candidate selection fills an editable confirmation form. Source URLs are accepted only over HTTP(S); known TMDB/RAWG links are resolved by provider IDs when configured, unknown links open a manual form. Detail fetches request localized TMDB descriptions when available. Provider attribution appears on data cards and the credits footer.

Tests cover authentication/authorization, deduplication, status history, language preference, URL validation and metadata fallback. Frontend is checked with TypeScript build and a local smoke test.
