BEGIN;
ALTER TABLE items ADD COLUMN season_number INTEGER CHECK(season_number IS NULL OR season_number BETWEEN 1 AND 1000);
ALTER TABLE items ADD COLUMN episode_number INTEGER CHECK(episode_number IS NULL OR episode_number BETWEEN 1 AND 10000);
COMMIT;
