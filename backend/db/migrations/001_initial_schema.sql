-- Practitioners (e.g. Silvia)
CREATE TABLE practitioners (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    phone VARCHAR(20) NOT NULL,
    profession VARCHAR(100),
    working_hours JSONB NOT NULL,
    break_minutes INT DEFAULT 5,
    services JSONB NOT NULL,
    timezone VARCHAR(50) DEFAULT 'Europe/Rome',
    whatsapp_number VARCHAR(20),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Clients
CREATE TABLE clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    practitioner_id UUID REFERENCES practitioners(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    phone VARCHAR(20) NOT NULL UNIQUE,
    notes TEXT,
    first_seen TIMESTAMPTZ DEFAULT NOW(),
    last_seen TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_clients_phone ON clients(phone);
CREATE INDEX idx_clients_practitioner ON clients(practitioner_id);

-- Bookings
CREATE TABLE bookings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    practitioner_id UUID REFERENCES practitioners(id) ON DELETE CASCADE,
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    service VARCHAR(100),
    starts_at TIMESTAMPTZ NOT NULL,
    duration_minutes INT NOT NULL,
    status VARCHAR(20) DEFAULT 'confirmed',
    reminder_sent BOOLEAN DEFAULT FALSE,
    created_via VARCHAR(20) DEFAULT 'whatsapp',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    cancelled_at TIMESTAMPTZ
);

CREATE INDEX idx_bookings_starts_at ON bookings(starts_at);
CREATE INDEX idx_bookings_practitioner ON bookings(practitioner_id, starts_at);
CREATE INDEX idx_bookings_client ON bookings(client_id);
CREATE INDEX idx_bookings_status ON bookings(status);

-- Packages (prepaid lesson bundles)
CREATE TABLE packages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    practitioner_id UUID REFERENCES practitioners(id) ON DELETE CASCADE,
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    total_sessions INT NOT NULL,
    used_sessions INT DEFAULT 0,
    purchase_date DATE DEFAULT CURRENT_DATE,
    expiry_date DATE,
    payment_status VARCHAR(20) DEFAULT 'paid',
    notes TEXT
);

CREATE INDEX idx_packages_client ON packages(client_id);

-- Conversation log
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    direction VARCHAR(10) NOT NULL,
    body TEXT NOT NULL,
    intent VARCHAR(30),
    entities JSONB,
    confidence FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_messages_client ON messages(client_id, created_at);
