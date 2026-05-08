ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS first_name VARCHAR(60),
    ADD COLUMN IF NOT EXISTS last_name VARCHAR(60);

-- Backfill: any existing 'name' that looks like a real name goes into first_name.
-- Phone-number placeholders get left as NULL so we re-prompt on next message.
UPDATE clients
SET first_name = name
WHERE first_name IS NULL
  AND name IS NOT NULL
  AND name NOT LIKE '+%';

CREATE INDEX IF NOT EXISTS idx_clients_first_name ON clients(first_name);
