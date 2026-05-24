CREATE TABLE IF NOT EXISTS scrape_run (
    id              SERIAL PRIMARY KEY,
    manufacturer    VARCHAR(100) NOT NULL,
    started_at      TIMESTAMP    NOT NULL,
    completed_at    TIMESTAMP,
    cars_processed  INTEGER      NOT NULL DEFAULT 0,
    new_parts       INTEGER      NOT NULL DEFAULT 0,
    updated_parts   INTEGER      NOT NULL DEFAULT 0,
    success         BOOLEAN      NOT NULL DEFAULT FALSE,
    error_message   VARCHAR(1000)
);
