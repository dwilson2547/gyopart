-- PostgreSQL schema for parts interchange
-- Safe to run multiple times (IF NOT EXISTS / IF EXISTS guards)

CREATE TABLE IF NOT EXISTS manufacturer (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(300) NOT NULL,
    base_url    VARCHAR(300),
    CONSTRAINT uq_manufacturer_name UNIQUE (name)
);

CREATE TABLE IF NOT EXISTS year (
    id   SERIAL PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    CONSTRAINT uq_year_name UNIQUE (name)
);

CREATE TABLE IF NOT EXISTS make (
    id           SERIAL PRIMARY KEY,
    name         VARCHAR(120) NOT NULL,
    select_value VARCHAR(120),
    start_year   INTEGER,
    end_year     INTEGER,
    CONSTRAINT uq_make_name UNIQUE (name)
);

CREATE TABLE IF NOT EXISTS model (
    id           SERIAL PRIMARY KEY,
    name         VARCHAR(120) NOT NULL,
    select_value VARCHAR(120),
    make_id      INTEGER REFERENCES make(id)
);

CREATE TABLE IF NOT EXISTS trim (
    id           SERIAL PRIMARY KEY,
    name         VARCHAR(120) NOT NULL,
    select_value VARCHAR(120),
    CONSTRAINT uq_trim_name UNIQUE (name)
);

CREATE TABLE IF NOT EXISTS engine (
    id           SERIAL PRIMARY KEY,
    name         VARCHAR(120) NOT NULL,
    select_value VARCHAR(120),
    CONSTRAINT uq_engine_name UNIQUE (name)
);

CREATE TABLE IF NOT EXISTS category (
    id   SERIAL PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    CONSTRAINT uq_category_name UNIQUE (name)
);

CREATE TABLE IF NOT EXISTS subcategory (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(120) NOT NULL,
    category_id INTEGER REFERENCES category(id)
);

CREATE TABLE IF NOT EXISTS image (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100),
    bucket_path     VARCHAR(120),
    url             VARCHAR(500),
    alt_text        VARCHAR(500),
    saved           BOOLEAN DEFAULT FALSE,
    uploaded        BOOLEAN DEFAULT FALSE,
    manufacturer_id INTEGER REFERENCES manufacturer(id)
);

CREATE TABLE IF NOT EXISTS part (
    id              SERIAL PRIMARY KEY,
    url             VARCHAR(500),
    part_number     VARCHAR(200),
    manufacturer_id INTEGER REFERENCES manufacturer(id),
    title           VARCHAR(200),
    category_id     INTEGER REFERENCES category(id),
    other_names     TEXT,
    description     TEXT,
    replaces        TEXT,
    positions       TEXT,
    notes           TEXT,
    msrp            FLOAT,
    applications    TEXT,
    hazmat          BOOLEAN
);

CREATE TABLE IF NOT EXISTS car (
    id              SERIAL PRIMARY KEY,
    year_id         INTEGER REFERENCES year(id),
    make_id         INTEGER REFERENCES make(id),
    model_id        INTEGER REFERENCES model(id),
    trim_id         INTEGER REFERENCES trim(id),
    engine_id       INTEGER REFERENCES engine(id),
    manufacturer_id INTEGER REFERENCES manufacturer(id),
    car_id          VARCHAR(200),
    vehicle_id      VARCHAR(200),
    base_url        VARCHAR(1000)
);

CREATE TABLE IF NOT EXISTS diagram (
    id              SERIAL PRIMARY KEY,
    image_id        INTEGER REFERENCES image(id),
    category_id     INTEGER REFERENCES category(id),
    sub_category_id INTEGER REFERENCES subcategory(id),
    base_car_url    VARCHAR(1000),
    category_url    VARCHAR(1000)
);

CREATE TABLE IF NOT EXISTS part_images (
    part_id         INTEGER NOT NULL REFERENCES part(id),
    image_id        INTEGER NOT NULL REFERENCES image(id),
    part_image_text VARCHAR(500),
    PRIMARY KEY (part_id, image_id)
);

CREATE TABLE IF NOT EXISTS diagram_parts (
    diagram_id  INTEGER NOT NULL REFERENCES diagram(id),
    part_id     INTEGER NOT NULL REFERENCES part(id),
    part_index  VARCHAR(25),
    PRIMARY KEY (diagram_id, part_id)
);

CREATE TABLE IF NOT EXISTS car_parts (
    car_id  INTEGER NOT NULL REFERENCES car(id),
    part_id INTEGER NOT NULL REFERENCES part(id),
    PRIMARY KEY (car_id, part_id)
);

CREATE TABLE IF NOT EXISTS car_diagrams (
    car_id     INTEGER NOT NULL REFERENCES car(id),
    diagram_id INTEGER NOT NULL REFERENCES diagram(id),
    PRIMARY KEY (car_id, diagram_id)
);

CREATE TABLE IF NOT EXISTS car_categories (
    car_id      INTEGER NOT NULL REFERENCES car(id),
    category_id INTEGER NOT NULL REFERENCES category(id),
    PRIMARY KEY (car_id, category_id)
);

CREATE TABLE IF NOT EXISTS feedback (
    id       SERIAL PRIMARY KEY,
    name     VARCHAR(250),
    email    VARCHAR(250),
    comments VARCHAR(2000)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_image_name         ON image(name);
CREATE INDEX IF NOT EXISTS idx_image_manufacturer ON image(manufacturer_id);
CREATE INDEX IF NOT EXISTS idx_part_number        ON part(part_number);
CREATE INDEX IF NOT EXISTS idx_part_manufacturer  ON part(manufacturer_id);
CREATE INDEX IF NOT EXISTS idx_car_manufacturer   ON car(manufacturer_id);
CREATE INDEX IF NOT EXISTS idx_car_year           ON car(year_id);
CREATE INDEX IF NOT EXISTS idx_car_make           ON car(make_id);
CREATE INDEX IF NOT EXISTS idx_car_model          ON car(model_id);
CREATE INDEX IF NOT EXISTS idx_model_make         ON model(make_id);
CREATE INDEX IF NOT EXISTS idx_subcat_category    ON subcategory(category_id);
CREATE INDEX IF NOT EXISTS idx_diagram_category   ON diagram(category_id);
CREATE INDEX IF NOT EXISTS idx_diagram_subcat     ON diagram(sub_category_id);
