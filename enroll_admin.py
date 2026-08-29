"""Enroll ANISH as admin - direct database approach."""
import sys
sys.path.insert(0, r"S:\CODE\BABY")

import cv2
import numpy as np
from pathlib import Path

# Try to find the user's image in common locations
possible_paths = [
    r"C:\Users\anish\Desktop",
    r"C:\Users\anish\Downloads",
    r"C:\Users\anish\Pictures",
    r"C:\Users\anish\.cache\opencode",
]

# First, let's just create the admin profile
from biometrics.biometric_db import BiometricDB
db = BiometricDB()

# Check if admin already exists
if db.has_admin():
    print("Admin already exists!")
    profiles = db.get_all()
    for p in profiles:
        print(f"  {p['name']} (admin={p['is_admin']})")
else:
    # Create admin profile without face for now
    db.save_profile(
        name="ANISH",
        relationship="admin",
        is_admin=True
    )
    print("Admin profile 'ANISH' created!")
    print("Face enrollment will happen through the camera in the app.")

# Verify
profiles = db.get_all()
for p in profiles:
    name = p["name"]
    is_admin = p["is_admin"]
    has_face = p["face_emb"] is not None
    print(f"Profile: {name}, admin={is_admin}, has_face={has_face}")



















