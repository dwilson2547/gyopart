ALTER TABLE image
    ADD COLUMN IF NOT EXISTS imgcache_hash   VARCHAR(64),
    ADD COLUMN IF NOT EXISTS imgcache_bucket VARCHAR(100);

CREATE INDEX IF NOT EXISTS idx_image_imgcache_hash ON image(imgcache_hash);
