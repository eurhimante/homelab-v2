import argparse
import json
import math
import re
import shutil
import tempfile
import zipfile
import uuid
from pathlib import Path


# =========================================================
# ZIP UTILS
# =========================================================

def extract_zip(zip_path, out_dir):
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(out_dir)


def copy_tree(src, dst):
    src = Path(src)
    dst = Path(dst)

    for item in src.rglob("*"):
        rel = item.relative_to(src)
        target = dst / rel

        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def repack_3mf(folder, output_file):
    with zipfile.ZipFile(output_file, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for file in Path(folder).rglob("*"):
            if file.is_file():
                arcname = file.relative_to(folder).as_posix()
                z.write(file, arcname)


# =========================================================
# JSON PATCH
# =========================================================

def patch_json_value(text, key, value):
    pattern = rf'"{re.escape(key)}"\s*:\s*"[^"]*"'
    replacement = f'"{key}": "{value}"'

    text, count = re.subn(pattern, replacement, text)

    if count == 0:
        insert = f'    "{key}": "{value}",\n'
        text = text.replace("{\n", "{\n" + insert, 1)

    return text


def patch_project_settings(
    project_config,
    support_type="off",
    support_threshold=45,
    support_bed_only=False,
    infill=15,
    infill_pattern="gyroid",
    brim=5,
    layer=0.2,
    wall_loops=2,
    quantity=1
):
    if not project_config.exists():
        return

    text = project_config.read_text(encoding="utf-8", errors="ignore")

    # Supports
    if support_type == "off":
        text = patch_json_value(text, "enable_support", "0")
    else:
        text = patch_json_value(text, "enable_support", "1")
        text = patch_json_value(text, "support_type", support_type)
        text = patch_json_value(text, "support_threshold_angle", str(support_threshold))
        text = patch_json_value(
            text,
            "support_on_build_plate_only",
            "1" if support_bed_only else "0"
        )

    # Infill
    text = patch_json_value(text, "sparse_infill_density", f"{infill}%")
    text = patch_json_value(text, "sparse_infill_pattern", infill_pattern)

    # Brim
    text = patch_json_value(text, "brim_width", str(brim))
    text = patch_json_value(text, "brim_type", "auto_brim" if brim > 0 else "no_brim")

    # Layer
    text = patch_json_value(text, "layer_height", str(layer))
    text = patch_json_value(text, "initial_layer_print_height", str(layer))

    # Walls
    text = patch_json_value(text, "wall_loops", str(wall_loops))

    project_config.write_text(text, encoding="utf-8")


# =========================================================
# PLATEAU IMPRIMABLE (NOUVEAU)
# =========================================================

# Valeur de repli SEULEMENT si le fichier project_settings.config est
# introuvable ou illisible. Ne doit normalement jamais être utilisée :
# on préfère échouer bruyamment plutôt que de deviner un plateau 235mm
# qui n'existe peut-être pas sur l'imprimante cible.
FALLBACK_BED_SIZE = 200.0


def get_printable_area(root_dir):
    """Lit le plateau imprimable RÉEL depuis project_settings.config,
    au lieu de supposer une taille fixe (c'était la cause du bug -52 :
    des projets étaient dupliqués sur une grille pensée pour un plateau
    de 235mm alors que le plateau réel de l'imprimante faisait 200mm).

    Retourne (largeur, profondeur) en mm.
    """
    cfg_path = root_dir / "Metadata" / "project_settings.config"

    if not cfg_path.exists():
        return FALLBACK_BED_SIZE, FALLBACK_BED_SIZE

    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8", errors="ignore"))
        points = cfg.get("printable_area", [])

        xs, ys = [], []
        for p in points:
            x_str, y_str = p.split("x")
            xs.append(float(x_str))
            ys.append(float(y_str))

        if not xs or not ys:
            return FALLBACK_BED_SIZE, FALLBACK_BED_SIZE

        width = max(xs) - min(xs)
        depth = max(ys) - min(ys)

        if width <= 0 or depth <= 0:
            return FALLBACK_BED_SIZE, FALLBACK_BED_SIZE

        return width, depth

    except Exception:
        return FALLBACK_BED_SIZE, FALLBACK_BED_SIZE


# =========================================================
# GEOMETRY / TRANSFORM
# =========================================================

def parse_transform(transform):
    vals = [float(x) for x in transform.split()]
    if len(vals) != 12:
        raise ValueError("Transform invalide")
    return vals


def format_transform(vals):
    return " ".join(f"{v:.12g}" for v in vals)


def apply_transform_z(vals, x, y, z):
    return vals[2] * x + vals[5] * y + vals[8] * z + vals[11]


def get_vertices_from_object_model(object_model_file):
    text = object_model_file.read_text(encoding="utf-8", errors="ignore")

    vertices = []

    pattern = re.compile(
        r'<vertex\s+[^>]*x="([^"]+)"[^>]*y="([^"]+)"[^>]*z="([^"]+)"',
        re.I
    )

    for m in pattern.finditer(text):
        try:
            vertices.append((
                float(m.group(1)),
                float(m.group(2)),
                float(m.group(3))
            ))
        except ValueError:
            pass

    return vertices


def find_first_object_model(root_dir):
    objects_dir = root_dir / "3D" / "Objects"

    if not objects_dir.exists():
        return None

    models = list(objects_dir.glob("*.model"))

    if not models:
        return None

    return models[0]


def reset_component_transform(model_text):
    return re.sub(
        r'(<component\b[^>]*\btransform=")([^"]+)(")',
        lambda m: m.group(1) + "1 0 0 0 1 0 0 0 1 0 0 0" + m.group(3),
        model_text,
        count=1
    )


def scale_transform_values(transform, scale):
    vals = parse_transform(transform)

    vals[0] *= scale
    vals[1] *= scale
    vals[2] *= scale

    vals[3] *= scale
    vals[4] *= scale
    vals[5] *= scale

    vals[6] *= scale
    vals[7] *= scale
    vals[8] *= scale

    vals[9] = 100.0
    vals[10] = 100.0
    vals[11] *= scale

    return vals


def apply_uniform_scale_and_drop_to_bed(root_dir, scale):
    model_file = root_dir / "3D" / "3dmodel.model"
    model_settings_file = root_dir / "Metadata" / "model_settings.config"
    object_model_file = find_first_object_model(root_dir)

    if not model_file.exists():
        return

    model_text = model_file.read_text(encoding="utf-8", errors="ignore")
    model_text = reset_component_transform(model_text)

    item_match = re.search(
        r'(<item\b[^>]*\btransform=")([^"]+)(")',
        model_text
    )

    if not item_match:
        model_file.write_text(model_text, encoding="utf-8")
        return

    old_transform = item_match.group(2)
    vals = scale_transform_values(old_transform, scale)

    # Extrait les vertices depuis le fichier objet réel
    vertices = []
    if object_model_file and object_model_file.exists():
        vertices = get_vertices_from_object_model(object_model_file)
    # SINON: si le fichier objet est introuvable, impossible de faire un
    # drop-to-bed correct basé sur le mesh.

    if vertices:
        min_z = min(
            apply_transform_z(vals, x, y, z)
            for x, y, z in vertices
        )
        vals[11] -= min_z

    new_transform = format_transform(vals)

    model_text = (
        model_text[:item_match.start(2)]
        + new_transform
        + model_text[item_match.end(2):]
    )

    model_file.write_text(model_text, encoding="utf-8")

    # Sync assemble_item
    if model_settings_file.exists():
        cfg = model_settings_file.read_text(encoding="utf-8", errors="ignore")

        # Toujours en dur sur object_id="2" pour matcher la logique actuelle.
        assemble_block = (
            '  <assemble>\n'
            f'   <assemble_item object_id="2" instance_id="0" '
            f'transform="{new_transform}" offset="0 0 0" />\n'
            '  </assemble>'
        )

        if re.search(r'  <assemble>\s*</assemble>', cfg, flags=re.S):
            cfg = re.sub(
                r'  <assemble>\s*</assemble>',
                assemble_block,
                cfg,
                flags=re.S
            )
        else:
            if "<assemble>" not in cfg:
                cfg = re.sub(
                    r'</config>',
                    assemble_block + "\n</config>",
                    cfg
                )

        model_settings_file.write_text(cfg, encoding="utf-8")


def apply_transform_xy(vals, x, y, z):
    return vals[0] * x + vals[3] * y + vals[6] * z + vals[9], vals[1] * x + vals[4] * y + vals[7] * z + vals[10]


def get_transformed_size_xy(root_dir):
    model_file = root_dir / "3D" / "3dmodel.model"
    object_model_file = find_first_object_model(root_dir)

    if not model_file.exists() or not object_model_file or not object_model_file.exists():
        return 35.0, 35.0

    model_text = model_file.read_text(encoding="utf-8", errors="ignore")
    item_match = re.search(r'<item\b[^>]*\btransform="([^"]+)"', model_text)
    if not item_match:
        return 35.0, 35.0

    try:
        vals = parse_transform(item_match.group(1))
    except Exception:
        return 35.0, 35.0

    vertices = get_vertices_from_object_model(object_model_file)
    if not vertices:
        return 35.0, 35.0

    xs, ys = [], []
    for x, y, z in vertices:
        tx, ty = apply_transform_xy(vals, x, y, z)
        xs.append(tx)
        ys.append(ty)

    width = max(xs) - min(xs) if xs else 35.0
    depth = max(ys) - min(ys) if ys else 35.0
    return max(width, 10.0), max(depth, 10.0)


def duplicate_instances(root_dir, quantity=1, margin=10, gap=8, strict=True):
    """Duplique l'objet principal dans le 3MF en copiant les <item> du build.

    CORRECTIF: la grille est désormais dimensionnée et centrée par rapport
    au VRAI plateau imprimable (lu dans project_settings.config), et non
    plus par rapport à une taille de plateau supposée à 235mm étendue
    depuis la position d'origine de l'objet. C'était la cause du bug
    "Some objects are located over the boundary of the heated bed" /
    return -52 : sur les imprimantes dont le plateau réel est plus petit
    (ex: 200x200), la grille dépassait le bord sans jamais être détecté
    avant l'appel à OrcaSlicer CLI.
    """
    try:
        quantity = max(1, int(quantity))
    except Exception:
        quantity = 1

    if quantity <= 1:
        return

    model_file = root_dir / "3D" / "3dmodel.model"
    model_settings_file = root_dir / "Metadata" / "model_settings.config"

    if not model_file.exists():
        return

    model_text = model_file.read_text(encoding="utf-8", errors="ignore")
    item_match = re.search(r'(<item\b[^>]*\btransform=")([^"]+)("[^>]*/>)', model_text)
    if not item_match:
        return

    try:
        base_vals = parse_transform(item_match.group(2))
    except Exception:
        return

    width, depth = get_transformed_size_xy(root_dir)
    bed_w, bed_h = get_printable_area(root_dir)

    step_x = width + gap
    step_y = depth + gap

    usable_w = max(bed_w - 2 * margin, step_x)
    usable_h = max(bed_h - 2 * margin, step_y)

    cols = max(1, min(quantity, int(usable_w // step_x)))
    rows = math.ceil(quantity / cols)

    # Garde-fou : si même une seule colonne/ligne ne tient pas sur le
    # plateau réel, on échoue proprement ICI plutôt que de laisser
    # OrcaSlicer CLI renvoyer un -52 opaque après coup.
    if rows * step_y - gap > usable_h or step_x > usable_w:
        if strict:
            raise ValueError(
                f"quantity={quantity} ne tient pas sur le plateau réel "
                f"({bed_w:.0f}x{bed_h:.0f}mm) avec cet objet "
                f"({width:.1f}x{depth:.1f}mm, pas de grille {step_x:.1f}x{step_y:.1f}mm). "
                f"Réduire la quantité, réduire le scale, ou augmenter le plateau."
            )
        # Mode non strict : on tronque silencieusement à ce qui tient.
        rows = max(1, int(usable_h // step_y))
        quantity = min(quantity, cols * rows)

    # Grille centrée sur le plateau réel (au lieu d'être étendue depuis
    # base_x/base_y, qui est déjà proche du centre et fait sortir la
    # grille du plateau bien avant que "cols" ne soit épuisé).
    grid_w = (cols - 1) * step_x
    grid_h = (rows - 1) * step_y

    start_x = bed_w / 2.0 - grid_w / 2.0
    start_y = bed_h / 2.0 - grid_h / 2.0

    new_items = []
    for idx in range(quantity):
        row = idx // cols
        col = idx % cols
        vals = base_vals[:]
        vals[9] = start_x + col * step_x
        vals[10] = start_y + row * step_y
        transform = format_transform(vals)

        item = item_match.group(0)
        item = re.sub(r'transform="[^"]+"', f'transform="{transform}"', item)
        item = re.sub(r'p:UUID="[^"]+"', f'p:UUID="{uuid.uuid4()}"', item)
        new_items.append(item)

    model_text = model_text[:item_match.start()] + "\n  ".join(new_items) + model_text[item_match.end():]
    model_file.write_text(model_text, encoding="utf-8")

    if model_settings_file.exists():
        cfg = model_settings_file.read_text(encoding="utf-8", errors="ignore")
        mi_match = re.search(
            r'(\s*<model_instance>\s*<metadata key="object_id" value="2"/>\s*'
            r'<metadata key="instance_id" value=")0("/>\s*'
            r'<metadata key="identify_id" value=")([^"/]+)("/>\s*</model_instance>)',
            cfg, flags=re.S
        )
        if mi_match:
            blocks = []
            for idx in range(quantity):
                identify = 15 + idx
                blocks.append(f'{mi_match.group(1)}{idx}{mi_match.group(2)}{identify}{mi_match.group(4)}')
            cfg = cfg[:mi_match.start()] + "\n".join(blocks) + cfg[mi_match.end():]

        model_settings_file.write_text(cfg, encoding="utf-8")


# =========================================================
# MERGE
# =========================================================

def merge_3mf(
    cli_3mf,
    gui_3mf,
    output_3mf,
    scale=1.0,
    support_type="off",
    support_threshold=45,
    support_bed_only=False,
    infill=15,
    infill_pattern="gyroid",
    brim=5,
    layer=0.2,
    wall_loops=2,
    quantity=1,
    strict_bed_check=True
):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        cli_dir = tmp / "cli"
        gui_dir = tmp / "gui"
        out_dir = tmp / "merged"

        extract_zip(cli_3mf, cli_dir)
        extract_zip(gui_3mf, gui_dir)

        # Base GUI complète
        copy_tree(gui_dir, out_dir)

        # Fichiers critiques CLI
        files_to_copy = [
            "3D/3dmodel.model",
            "3D/_rels/3dmodel.model.rels",
            "Metadata/model_settings.config",
        ]

        for file_path in files_to_copy:
            src = cli_dir / file_path
            dst = out_dir / file_path

            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

        # Objets 3D CLI
        cli_objects = cli_dir / "3D" / "Objects"
        out_objects = out_dir / "3D" / "Objects"

        if cli_objects.exists():
            copy_tree(cli_objects, out_objects)

        # Paramètres impression : appliqués AVANT la duplication, pour que
        # get_printable_area() lise déjà le bon project_settings.config
        # (le plateau ne dépend pas de ces réglages, mais on garde l'ordre
        # explicite pour éviter toute surprise si ça change un jour).
        patch_project_settings(
            out_dir / "Metadata" / "project_settings.config",
            support_type=support_type,
            support_threshold=support_threshold,
            support_bed_only=support_bed_only,
            infill=infill,
            infill_pattern=infill_pattern,
            brim=brim,
            layer=layer,
            wall_loops=wall_loops
        )

        # Scale + drop to bed
        if scale != 1.0:
            apply_uniform_scale_and_drop_to_bed(out_dir, scale)

        duplicate_instances(out_dir, quantity=quantity, strict=strict_bed_check)

        repack_3mf(out_dir, output_3mf)

    print(f"Fusion terminée : {output_3mf}")


# =========================================================
# CLI
# =========================================================

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--cli", required=True, help="3MF généré par Orca CLI")
    parser.add_argument("--gui", required=True, help="3MF template GUI")
    parser.add_argument("--output", required=True, help="3MF final fusionné")
    parser.add_argument("--quantity", type=int, default=1, help="Nombre de copies dans le 3MF")

    parser.add_argument("--scale", type=float, default=1.0, help="Scale uniforme, exemple 0.25")

    parser.add_argument(
        "--support-type",
        choices=["off", "normal(auto)", "tree(auto)"],
        default="off",
        help="Type de supports"
    )

    parser.add_argument(
        "--support-threshold",
        type=int,
        default=45,
        help="Angle de déclenchement supports"
    )

    parser.add_argument(
        "--support-bed-only",
        action="store_true",
        help="Supports uniquement depuis le plateau"
    )

    parser.add_argument("--infill", type=int, default=15, help="Remplissage en pourcentage")
    parser.add_argument("--infill-pattern", default="gyroid", help="Motif infill")
    parser.add_argument("--brim", type=float, default=5, help="Largeur brim en mm")
    parser.add_argument("--layer", type=float, default=0.2, help="Hauteur de couche")
    parser.add_argument("--wall-loops", type=int, default=2, help="Nombre de parois")

    parser.add_argument(
        "--allow-overflow",
        action="store_true",
        help="Ne pas échouer si la quantité ne tient pas sur le plateau réel "
             "(tronque silencieusement au lieu de lever une erreur)"
    )

    args = parser.parse_args()

    merge_3mf(
        cli_3mf=args.cli,
        gui_3mf=args.gui,
        output_3mf=args.output,
        scale=args.scale,
        support_type=args.support_type,
        support_threshold=args.support_threshold,
        support_bed_only=args.support_bed_only,
        infill=args.infill,
        infill_pattern=args.infill_pattern,
        brim=args.brim,
        layer=args.layer,
        wall_loops=args.wall_loops,
        quantity=args.quantity,
        strict_bed_check=not args.allow_overflow
    )


if __name__ == "__main__":
    main()