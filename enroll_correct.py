"""Write ANISH admin to installed app DB with correct file-based encryption."""
import sys, os, sqlite3, pickle
sys.path.insert(0, r"S:\CODE\BABY")
from cryptography.fernet import Fernet

db_path = r"C:\Users\anish\AppData\Local\BABY\data\biometrics.db"
key_path = r"C:\Users\anish\AppData\Local\BABY\data\.biometric.key"

# Read the SAME key the app uses
with open(key_path, "rb") as _f:
    key = _f.read()
fernet = Fernet(key)
print(f"Using key: {key[:8]}...")

def enc(data):
    if data is None:
        return None
    return fernet.encrypt(pickle.dumps(data))

# Delete old profile
conn = sqlite3.connect(db_path)
conn.execute("DELETE FROM profiles")
conn.commit()
print("Cleared old profiles")

# Insert ANISH as admin (no face yet - will capture via camera)
conn.execute(
    "INSERT INTO profiles (name, relationship, face_emb, voice_emb, is_admin) VALUES (?, ?, ?, ?, ?)",
    ("ANISH", "admin", None, None, 1)
)
conn.commit()
print("Created admin profile: ANISH")

# Verify
rows = conn.execute("SELECT id, name, is_admin FROM profiles").fetchall()
for r in rows:
    print(f"  id={r[0]} name={r[1]} admin={r[2]}")

conn.close()
print("Done!")



















