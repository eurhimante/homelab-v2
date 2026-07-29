import pytest
import itertools
import secrets
import main

def get_library_combinations():
    """
    Génère dynamiquement toutes les combinaisons non vides à partir de JELLYFIN_LIBRARIES.
    Pour 5 bibliothèques, cela génère 2^5 - 1 = 31 combinaisons uniques.
    """
    libs = list(main.JELLYFIN_LIBRARIES.items())
    combinations = []
    for r in range(1, len(libs) + 1):
        for combo in itertools.combinations(libs, r):
            combinations.append(combo)
    return combinations

# Matrice de test combinant (liste de bibliothèques, droit de téléchargement)
# 31 combinaisons * 2 états de téléchargement = 62 cas de tests d'intégration d'invariants
TEST_MATRIX = []
for combo in get_library_combinations():
    for allow_download in [True, False]:
        TEST_MATRIX.append((combo, allow_download))

@pytest.mark.parametrize("library_combo, allow_download", TEST_MATRIX)
def test_jellyfin_policy_matrix(library_combo, allow_download):
    """
    Valide les invariants de la Policy retournée par Jellyfin après création de l'utilisateur.
    """
    # 1. Génération d'identifiants de test uniques et identifiables
    random_suffix = secrets.token_hex(4)
    test_username = f"ci_test_{random_suffix}"
    test_password = secrets.token_urlsafe(12)

    lib_names = [name for name, _ in library_combo]
    lib_ids = [lib_id for _, lib_id in library_combo]

    user_id = None
    try:
        # Étape A : Création de l'utilisateur dans Jellyfin
        user_id = main.create_jellyfin_user(test_username, test_password)
        assert user_id is not None, "Échec de création de l'utilisateur de test dans Jellyfin"

        # Étape B : Application de la Policy via l'application
        main.apply_jellyfin_policy(user_id, lib_ids, allow_download)

        # Étape C : Récupération de la Policy depuis l'API réelle de Jellyfin
        policy = main.get_jellyfin_user_policy(user_id)

        # --- VALIDATION DES INVARIANTS SÉCURITÉ ---
        
        # Invariant 1 : L'utilisateur n'est PAS un administrateur
        assert policy.get("IsAdministrator") is False, "Faille de sécurité : l'utilisateur créé est Administrateur"

        # Invariant 2 : EnableAllFolders doit être False (pour que le filtrage s'applique)
        assert policy.get("EnableAllFolders") is False, "Faille de filtrage : EnableAllFolders est à True alors qu'une sélection est explicite"

        # Invariant 3 : EnabledFolders correspond exactement aux bibliothèques demandées
        staged_folders = set(policy.get("EnabledFolders", []))
        expected_folders = set(lib_ids)
        assert staged_folders == expected_folders, (
            f"Décalage bibliothèques ! Attendues : {expected_folders}, Obtenues : {staged_folders}"
        )

        # Invariant 4 : EnableContentDownloading correspond exactement à la valeur demandée
        assert policy.get("EnableContentDownloading") is allow_download, (
            f"Décalage téléchargement ! Attendu : {allow_download}, Obtenu : {policy.get('EnableContentDownloading')}"
        )

    finally:
        # Étape D : Nettoyage systématique garanti par le bloc finally
        if user_id:
            try:
                main.delete_jellyfin_user(user_id)
            except Exception as e:
                print(f"Erreur lors du nettoyage de l'utilisateur de test {user_id}: {e}")
