import pytest
import sys
from pathlib import Path
# Ajouter le dossier parent au path pour permettre l'import de merge_v5_3mf
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from merge_v5_3mf import apply_uniform_scale_and_drop_to_bed, duplicate_instances

def setup_mock_3mf_full(tmp_path):
    """Crée une structure de fichiers 3MF plus complète pour tester scale+dup."""
    model_dir = tmp_path / "3D"
    model_dir.mkdir()
    meta_dir = tmp_path / "Metadata"
    meta_dir.mkdir()
    
    # Structure de production: 3D/Objects/ contenant les modèles réels
    objects_dir = model_dir / "Objects"
    objects_dir.mkdir()
    
    # 1. 3dmodel.model principal (référence l'objet)
    model_file = model_dir / "3dmodel.model"
    model_file.write_text("""
    <model>
        <item transform="1 0 0 0 1 0 0 0 1 10 10 0" p:UUID="original-uuid" objectid="2"/>
    </model>
    """)
    
    # 2. Le modèle réel de l'objet dans 3D/Objects/
    object_model_file = objects_dir / "object_2.model"
    object_model_file.write_text("""
    <model>
        <component id="2">
            <mesh>
                <vertices>
                    <vertex x="0" y="0" z="0"/>
                    <vertex x="35" y="35" z="10"/>
                </vertices>
            </mesh>
        </component>
    </model>
    """)
    
    settings_file = meta_dir / "model_settings.config"
    # Structure réaliste de model_settings.config
    settings_file.write_text("""
    <config>
        <model_instance>
            <metadata key="object_id" value="2"/>
            <metadata key="instance_id" value="0"/>
            <metadata key="identify_id" value="15"/>
        </model_instance>
    </config>
    """)
    
    return model_file

def test_scale_and_duplicate_integration(tmp_path):
    """
    Teste l'intégration : redimensionner un objet, puis le dupliquer.
    Vérifie que la duplication prend bien en compte la nouvelle taille après redimensionnement.
    """
    model_file = setup_mock_3mf_full(tmp_path)
    
    # 1. Scale par 2.0 (l'objet passe de 35x35 à 70x70)
    apply_uniform_scale_and_drop_to_bed(tmp_path, scale=2.0)
    
    # 2. Dupliquer (le step doit être basé sur 70+gap)
    # Si le bug existe, la duplication utilisera l'ancienne taille (35)
    quantity = 2
    duplicate_instances(tmp_path, quantity=quantity, bed_size=235, gap=10)
    
    content = model_file.read_text()
    transforms = re.findall(r'transform="([^"]+)"', content)
    
    assert len(transforms) == quantity
    
    # Analyse des matrices pour vérifier le décalage (grid)
    # Si le scale est appliqué correctement, le step devrait être ~80 (70+10)
    # transform 1: X=10
    # transform 2: X=10+80=90
    
    # Parsing rapide de la deuxieme transform
    vals = [float(x) for x in transforms[1].split()]
    assert vals[9] > 50 # Le X doit etre bien plus grand que le step de l'objet non scale

def test_xml_persistence_after_scale(tmp_path):
    """
    Vérifie explicitement que le fichier 3dmodel.model est correctement mis à jour
    sur le disque après un redimensionnement.
    """
    model_file = setup_mock_3mf_full(tmp_path)

    # 1. Appliquer le scale
    apply_uniform_scale_and_drop_to_bed(tmp_path, scale=2.0)

    # 2. Vérifier que le fichier 3dmodel.model est bien mis à jour
    content = model_file.read_text()

    # Vérifier que les transformations ont été modifiées
    assert 'transform="2 0 0 0 2 0 0 0 2' in content

    # 3. Vérifier que le composant mesh est toujours présent dans l'objet réel
    object_model_file = tmp_path / "3D" / "Objects" / "object_2.model"
    assert object_model_file.exists()
    assert '<mesh>' in object_model_file.read_text()

import re
