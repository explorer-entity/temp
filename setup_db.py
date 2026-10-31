import sqlite3

conn = sqlite3.connect('smriti.db')
cursor = conn.cursor()


# -----------------------------
# Users
# -----------------------------
cursor.execute('''
CREATE TABLE IF NOT EXISTS Users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    stage TEXT DEFAULT 'Early'
)
''')


# -----------------------------
# Game Sessions
# -----------------------------
cursor.execute('''
CREATE TABLE IF NOT EXISTS GameSessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    game_type TEXT,
    score INTEGER,
    difficulty TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')


# -----------------------------
# Patient Locations
# -----------------------------
cursor.execute('''
CREATE TABLE IF NOT EXISTS Locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    latitude REAL,
    longitude REAL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')


# -----------------------------
# Caregiver ↔ Patient Links
# -----------------------------
cursor.execute('''
CREATE TABLE IF NOT EXISTS CaregiverLinks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    caregiver_id INTEGER NOT NULL,
    patient_id INTEGER NOT NULL,
    FOREIGN KEY (caregiver_id) REFERENCES Users(id),
    FOREIGN KEY (patient_id) REFERENCES Users(id)
)
''')


# -----------------------------
# Alerts
# -----------------------------
cursor.execute('''
CREATE TABLE IF NOT EXISTS Alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    status TEXT DEFAULT 'Active',
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES Users(id)
)
''')


# -----------------------------
# Safe Zones / Geofences (v2: multiple NAMED zones per patient)
# -----------------------------
cursor.execute('''
CREATE TABLE IF NOT EXISTS SafeZones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    name TEXT NOT NULL DEFAULT 'Home',
    center_lat REAL NOT NULL,
    center_lng REAL NOT NULL,
    radius_meters REAL NOT NULL DEFAULT 200,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(patient_id, name),
    FOREIGN KEY (patient_id) REFERENCES Users(id)
)
''')

# Migrate a legacy v1 SafeZones table (patient_id as PRIMARY KEY, no name column)
try:
    cursor.execute("ALTER TABLE SafeZones ADD COLUMN name TEXT NOT NULL DEFAULT 'Home'")
except sqlite3.OperationalError:
    pass  # column already exists (fresh v2 DB or already migrated)


# -----------------------------
# Patient Reminders
# -----------------------------
cursor.execute('''
CREATE TABLE IF NOT EXISTS Reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    reminder_time TEXT NOT NULL,
    repeat_daily INTEGER DEFAULT 1,
    active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES Users(id)
)
''')


# -----------------------------
# Add newer Users columns
# -----------------------------

try:
    cursor.execute(
        "ALTER TABLE Users ADD COLUMN role TEXT DEFAULT 'patient'"
    )
except sqlite3.OperationalError:
    pass

try:
    cursor.execute(
        "ALTER TABLE Users ADD COLUMN age INTEGER"
    )
except sqlite3.OperationalError:
    pass

try:
    cursor.execute(
        "ALTER TABLE Users ADD COLUMN gender TEXT"
    )
except sqlite3.OperationalError:
    pass

try:
    cursor.execute(
        "ALTER TABLE Users ADD COLUMN language TEXT DEFAULT 'English'"
    )
except sqlite3.OperationalError:
    pass


# Save everything
conn.commit()

# Close database connection
conn.close()

print("Database and tables created successfully.")