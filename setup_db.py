import os
import sqlite3

DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'smriti.db')


def init_db(db_path=DEFAULT_DB):
    """Create / migrate every table. Safe to run repeatedly; app.py calls it at startup."""
    conn = sqlite3.connect(db_path)
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


    try:
        cursor.execute("ALTER TABLE GameSessions ADD COLUMN max_score INTEGER")
    except sqlite3.OperationalError:
        pass



    def add_column(table, ddl):
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
        except sqlite3.OperationalError:
            pass  # already exists

    # -- Security / consent / audit (v3) --
    add_column("Users", "username TEXT")
    add_column("Users", "secret_hash TEXT")                 # password (caregiver) or PIN (patient), hashed
    add_column("Users", "location_consent INTEGER DEFAULT 0")
    add_column("Users", "link_code TEXT")                   # one-time code a patient gives a caregiver
    add_column("Users", "link_expires TEXT")
    add_column("Alerts", "acknowledged_at TIMESTAMP")
    add_column("Alerts", "acknowledged_by INTEGER")
    add_column("Alerts", "resolution TEXT")                 # 'resolved' | 'false_alarm'
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_loc_user ON Locations(user_id, id)")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON Users(username) WHERE username IS NOT NULL")

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS Sessions (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        role TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TEXT NOT NULL
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS AccessLog (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL,
        caregiver_id INTEGER,
        action TEXT NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS ClinicalScores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL,
        moca_score INTEGER NOT NULL,
        assessed_on TEXT NOT NULL,
        entered_by INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')


    conn.commit()
    conn.close()


if __name__ == '__main__':
    init_db()
    print("Database and tables created successfully.")
