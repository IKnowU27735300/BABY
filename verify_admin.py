"""Clean up old profiles and verify admin."""
import sys
sys.path.insert(0, r"S:\CODE\BABY")
from biometrics.biometric_db import BiometricDB

db = BiometricDB()

# Remove stray profiles
profiles = db.get_all()
for p in profiles:
    if p["name"] == "Not" and not p["is_admin"]:
        db.delete_profile(p["id"])
        print(f"Removed: {p['name']}")

# Verify
profiles = db.get_all()
for p in profiles:
    n = p["name"]
    a = p["is_admin"]
    f = p["face_emb"] is not None
    v = p["voice_emb"] is not None
    print(f"  {n} | admin={a} | face={f} | voice={v}")



















