ALTER TABLE bookings
    ADD COLUMN IF NOT EXISTS gcal_event_id VARCHAR(255);

CREATE INDEX IF NOT EXISTS idx_bookings_gcal_event_id ON bookings(gcal_event_id);
