import pytest
import sqlite3
import main
from cryptography.fernet import Fernet
from argon2 import PasswordHasher

def test_sqlite_connection_and_schema():
    """
    Vérifie que la BDD s'initialise correctement et contient toutes les tables requises.
    """
    with main.get_db() as db:
        res = db.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()
        tables = [r["name"] for r in res]
        assert "admin_users" in tables
        assert "invitations" in tables
        assert "access_requests" in tables

def test_fernet_encryption_decryption():
    """
    Valide le chiffrement et déchiffrement réversible des mots de passe.
    """
    fernet = Fernet(main.INVITE_ENCRYPTION_KEY.encode())
    original = "MotDePasseTrêsComplexe123_@!"
    encrypted = fernet.encrypt(original.encode()).decode()
    decrypted = fernet.decrypt(encrypted.encode()).decode()
    assert original == decrypted

def test_password_hashing():
    """
    Valide la conformité du hachage de mot de passe administrateur avec Argon2.
    """
    ph = PasswordHasher()
    password = "admin_secure_password"
    pwd_hash = ph.hash(password)
    assert ph.verify(pwd_hash, password)
    
    with pytest.raises(Exception):
        ph.verify(pwd_hash, "wrong_password")
