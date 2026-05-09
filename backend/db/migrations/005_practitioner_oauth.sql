ALTER TABLE practitioners
    ADD COLUMN IF NOT EXISTS gcal_oauth_refresh_token TEXT,
    ADD COLUMN IF NOT EXISTS gcal_oauth_email VARCHAR(255),
    ADD COLUMN IF NOT EXISTS gcal_oauth_calendar_id VARCHAR(255);
