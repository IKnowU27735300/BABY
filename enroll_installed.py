"""Write ANISH admin to the INSTALLED app's database."""
import sys, os, sqlite3
sys.path.insert(0, r"S:\CODE\BABY")
from cryptography.fernet import Fernet

db_path = r"C:\Users\anish\AppData\Local\BABY\data\biometrics.db"

# Get the encryption key from keyring (same as BiometricDB)
import keyring
service, username = "BABY-AI", "biometric_key"
stored = keyring.get_password(service, username)
if stored:
    key = stored.encode()
else:
    key = Fernet.generate_key()
    keyring.set_password(service, username, key.decode())

fernet = Fernet(key)

def enc(data):
    if data is None:
        return None
    import pickle
    return fernet.encrypt(pickle.dumps(data))

def enc_str(s):
    if s is None:
        return None
    return fernet.encrypt(s.encode())

# Read the face image and get embedding
import cv2
import numpy as np

img_path = r"C:\Users\anish\.cache\opencode\tool-images\tmpt8w0w78w.jpg"
frame = cv2.imread(img_path)

face_emb = None
if frame is not None:
    print(f"Image loaded: {frame.shape}")
    from insightface.app import FaceAnalysis
    app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=0, det_size=(640, 640))
    faces = app.get(frame)
    if faces:
        largest = max(faces, key=lambda f: (f.bbox[2]-f.bbox[0]) * (f.bbox[3]-f.bbox[1]))
        face_emb = largest.embedding
        print(f"Face embedding extracted: {face_emb.shape}")
    else:
        print("No face detected in image")
else:
    print("Could not read image file")

# Insert into the installed app's database
conn = sqlite3.connect(db_path)
face_blob = enc(face_emb) if face_emb is not None else None

conn.execute(
    "INSERT INTO profiles (name, relationship, face_emb, voice_emb, is_admin) VALUES (?, ?, ?, ?, ?)",
    ("ANISH", "admin", face_blob, None, 1)
)
conn.commit()

# Verify
rows = conn.execute("SELECT id, name, is_admin, face_emb IS NOT NULL, voice_emb IS NOT NULL FROM profiles").fetchall()
print("\nProfiles in installed DB:")
for r in rows:
    print(f"  id={r[0]} name={r[1]} admin={r[2]} face={r[3]} voice={r[4]}")

conn.close()
print("\nDone! Admin ANISH saved to installed app database.")



















