import sys
import os
import shutil
from pathlib import Path

# Résolution des chemins
tests_dir = Path(__file__).parent
service_dir = tests_dir.parent
sys.path.insert(0, str(service_dir / "app"))
sys.path.insert(0, str(service_dir))

# Chargement intelligent du fichier .env de la racine (sans dépendance externe)
project_root = service_dir.parent.parent
env_path = project_root / ".env"

if env_path.exists():
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                # On ne surcharge pas les variables système déjà existantes
                os.environ.setdefault(key.strip(), val.strip())

# Valeurs de secours sûres (permet l'importation de l'app même sans vraie config)
os.environ.setdefault("JELLYFIN_URL", "http://localhost:8096")
os.environ.setdefault("JELLYFIN_API_KEY", "dummy_api_key_for_testing")
os.environ.setdefault("INVITE_ENCRYPTION_KEY", "b3E1VFFSRUdTWUhXWkdVSkpLVk5XU1pYQ0RFRkdISUo=")  # Clé Fernet 32 octets base64
os.environ.setdefault("INVITE_ADMIN_USERNAME", "admin")
os.environ.setdefault("INVITE_ADMIN_PASSWORD", "testpass")
os.environ.setdefault("SESSION_SECRET", "dummy_session_secret_for_testing_32_bytes_len_minimum")

# Isolation stricte de la BDD pour les tests
test_data_dir = tests_dir / "test_data"
test_data_dir.mkdir(parents=True, exist_ok=True)
os.environ["APP_DATA_DIR"] = str(test_data_dir)

import pytest
import main

# Redéfinition du chemin de la BDD vers la BDD de test
main.DATABASE_PATH = test_data_dir / "test_database.db"

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """
    Initialise une base de données SQLite de test isolée et nettoie les fichiers à la fin.
    """
    main.init_database()
    yield
    # Nettoyage complet du dossier temporaire de données de test
    if test_data_dir.exists():
        shutil.rmtree(test_data_dir)
