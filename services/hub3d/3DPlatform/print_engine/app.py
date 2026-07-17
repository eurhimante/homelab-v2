from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from pathlib import Path
import shutil
import subprocess
import uuid
import glob
import os
import requests

from merge_v5_3mf import merge_3mf

# =========================
# APP
# =========================

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# CONFIG
# =========================

ROOT_DIR = Path(__file__).resolve().parent
BASE_DIR = ROOT_DIR / "jobs"
BASE_DIR.mkdir(exist_ok=True)

# Stockage permanent des fichiers générés sur le NAS.
NAS_3DPLATFORM_DIR = Path(
    os.getenv("NAS_3DPLATFORM_DIR", "/mnt/rasplex/3dplatform")
)

NAS_STL_DIR = NAS_3DPLATFORM_DIR / "stl"
NAS_3MF_DIR = NAS_3DPLATFORM_DIR / "3mf"
NAS_GCODE_DIR = NAS_3DPLATFORM_DIR / "gcode"

for directory in (
    NAS_STL_DIR,
    NAS_3MF_DIR,
    NAS_GCODE_DIR,
):
    directory.mkdir(parents=True, exist_ok=True)

# Archivage permanent des STL sur le NAS.
STL_ARCHIVE_DIR = NAS_STL_DIR

ORCA_PATH = os.getenv(
    "ORCASLICER_PATH",
    "/opt/orcaslicer/bin/orca-slicer"
)

PRINTER_IP = os.getenv("PRINTER_IP", "192.168.1.193")
MOONRAKER_URL = os.getenv(
    "MOONRAKER_URL",
    f"http://{PRINTER_IP}:7125"
)
PRINTER_INTERFACE_URL = os.getenv(
    "PRINTER_INTERFACE_URL",
    f"http://{PRINTER_IP}/#/home"
)

# Templates GUI 3MF par imprimante + filament.
# Ajoute les fichiers dans print_engine/templates_3mf/
# Exemple Ender 3 V3 KE :
# - gui_3v3ke_pla.3mf
# - gui_3v3ke_tpu.3mf
# - gui_3v3ke_abs.3mf
GUI_TEMPLATES = {
    "ender3v3ke": {
        "pla": ROOT_DIR / "templates_3mf" / "gui_3v3ke_pla.3mf",
        "tpu60": ROOT_DIR / "templates_3mf" / "gui_3v3ke_tpu60.3mf",
        "tpu90": ROOT_DIR / "templates_3mf" / "gui_3v3ke_tpu90.3mf",
        "abs": ROOT_DIR / "templates_3mf" / "gui_3v3ke_abs.3mf",
        "petg": ROOT_DIR / "templates_3mf" / "gui_3v3ke_petg.3mf",
    },
}

# =========================
# HELPERS
# =========================

def job_path(job_id: str) -> Path:
    return BASE_DIR / job_id


def nas_stl_path(job_id: str) -> Path | None:
    matches = sorted(NAS_STL_DIR.glob(f"{job_id}__*"))
    return matches[0] if matches else None


def nas_3mf_path(job_id: str) -> Path | None:
    matches = sorted(NAS_3MF_DIR.glob(f"{job_id}__*"))
    return matches[0] if matches else None


def nas_gcode_path(job_id: str) -> Path | None:
    matches = sorted(NAS_GCODE_DIR.glob(f"{job_id}__*"))
    return matches[0] if matches else None


def find_job_gcode(job_id: str) -> Path | None:
    folder = job_path(job_id)

    local_gcode = find_first_file(folder, "*.gcode") if folder.exists() else None
    if local_gcode:
        return local_gcode

    return nas_gcode_path(job_id)


def cleanup_job(job_id: str):
    folder = job_path(job_id)

    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)
        print(f"Workspace nettoyé : {folder}")


def run_command(command, log_file: Path | None = None):
    print("\n===== COMMAND =====")
    print(command)

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        shell=False,
    )

    print("\nRETURN CODE:", result.returncode)
    print("\nSTDOUT:", result.stdout)
    print("\nSTDERR:", result.stderr)

    if log_file:
        log_file.write_text(
            "COMMAND:\n"
            + " ".join(str(x) for x in command)
            + "\n\nRETURN CODE:\n"
            + str(result.returncode)
            + "\n\nSTDOUT:\n"
            + result.stdout
            + "\n\nSTDERR:\n"
            + result.stderr,
            encoding="utf-8",
        )

    return result


def find_first_file(folder: Path, pattern: str):
    files = glob.glob(str(folder / pattern))
    return Path(files[0]) if files else None



def _seconds_to_int(value):
    try:
        if value is None:
            return None
        return max(0, int(round(float(value))))
    except Exception:
        return None


def _format_state_label(state: str | None) -> str:
    labels = {
        "standby": "Prête",
        "printing": "Impression en cours",
        "paused": "En pause",
        "complete": "Terminée",
        "cancelled": "Annulée",
        "error": "Erreur",
        "offline": "Hors ligne",
    }
    return labels.get((state or "").lower(), state or "Inconnu")

# =========================
# STATUS
# =========================

@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/")
def home():
    return {"status": "backend_online"}


@app.get("/status")
def status():
    return {"status": "online"}

# =========================
# STEP 1 — UPLOAD STL
# =========================

@app.post("/upload-stl")
def upload_stl(file: UploadFile = File(...)):
    job_id = str(uuid.uuid4())
    folder = job_path(job_id)
    folder.mkdir(parents=True, exist_ok=True)

    filename = Path(file.filename or "model.stl").name
    stl_path = folder / filename

    with stl_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Copie permanente centralisée pour archivage NAS.
    # Le fichier original reste aussi dans jobs/<job_id>/ pour le pipeline Orca.
    archive_name = f"{job_id}__{filename}"
    archive_path = STL_ARCHIVE_DIR / archive_name
    shutil.copy2(stl_path, archive_path)

    return {
        "status": "uploaded",
        "job_id": job_id,
        "filename": filename,
        "stl_url": f"/stl/{job_id}",
        "archived_stl": str(archive_path),
    }


@app.get("/stl/{job_id}")
def get_stl(job_id: str):
    folder = job_path(job_id)

    stl = find_first_file(folder, "*.stl") if folder.exists() else None
    if not stl:
        stl = nas_stl_path(job_id)

    if not stl:
        return JSONResponse({"error": "No STL found"}, status_code=404)

    return FileResponse(stl, filename=stl.name)

# =========================
# STEP 2 — CREATE CLI 3MF + MERGE GUI 3MF
# =========================

@app.post("/generate-3mf")
def generate_3mf(
    job_id: str = Form(...),
    printer: str = Form("ender3v3ke"),
    filament: str = Form("pla"),
    scale: float = Form(1.0),
    quantity: int = Form(1),
    support_type: str = Form("off"),
    support_threshold: int = Form(45),
    support_bed_only: bool = Form(False),
    infill: int = Form(15),
    infill_pattern: str = Form("gyroid"),
    brim: float = Form(5.0),
    layer: float = Form(0.2),
    wall_loops: int = Form(2),
):
    folder = job_path(job_id)
    if not folder.exists():
        return JSONResponse({"error": "Job not found"}, status_code=404)

    stl = find_first_file(folder, "*.stl")
    if not stl:
        return JSONResponse({"error": "No STL found"}, status_code=404)

    printer_key = printer.strip().lower()
    filament_key = filament.strip().lower()

    printer_templates = GUI_TEMPLATES.get(printer_key)
    if not printer_templates:
        return JSONResponse(
            {
                "error": f"Printer template profile not found for printer '{printer}'",
                "available_printers": list(GUI_TEMPLATES.keys()),
            },
            status_code=400,
        )

    gui_template = printer_templates.get(filament_key)
    if not gui_template or not gui_template.exists():
        return JSONResponse(
            {
                "error": f"GUI template not found for printer '{printer}' and filament '{filament}'",
                "expected_file": str(gui_template) if gui_template else None,
                "available_filaments": list(printer_templates.keys()),
            },
            status_code=400,
        )

    cli_3mf = folder / "cli.3mf"
    merged_3mf = folder / "project_merged.3mf"

    # 1. STL -> CLI 3MF avec Orca
    export_cmd = [
        ORCA_PATH,
        str(stl),
        "--export-3mf",
        str(cli_3mf),
    ]

    export_result = run_command(export_cmd, folder / "export_3mf.log")

    if export_result.returncode != 0 or not cli_3mf.exists():
        return JSONResponse(
            {
                "status": "failed_export_3mf",
                "stdout": export_result.stdout,
                "stderr": export_result.stderr,
            },
            status_code=500,
        )

    # 2. Fusion CLI 3MF + GUI template
    try:
        merge_3mf(
            cli_3mf=cli_3mf,
            gui_3mf=gui_template,
            output_3mf=merged_3mf,
            scale=scale,
            quantity=quantity,
            support_type=support_type,
            support_threshold=support_threshold,
            support_bed_only=support_bed_only,
            infill=infill,
            infill_pattern=infill_pattern,
            brim=brim,
            layer=layer,
            wall_loops=wall_loops,
        )
    except Exception as exc:
        return JSONResponse(
            {"status": "failed_merge", "error": str(exc)},
            status_code=500,
        )

    if not merged_3mf.exists():
        return JSONResponse(
            {"status": "failed_merge", "error": "Merged 3MF was not created"},
            status_code=500,
        )

    # Archivage permanent du 3MF final sur le NAS.
    archived_3mf = NAS_3MF_DIR / f"{job_id}__{merged_3mf.name}"
    shutil.copy2(merged_3mf, archived_3mf)

    return {
        "status": "3mf_ready",
        "job_id": job_id,
        "project_url": f"/project/{job_id}",
        "printer": printer_key,
        "filament": filament_key,
        "template_3mf": str(gui_template),
        "quantity": max(1, quantity),
        "cli_3mf": str(cli_3mf),
        "merged_3mf": str(merged_3mf),
        "archived_3mf": str(archived_3mf),
    }


@app.get("/project/{job_id}")
def get_project(job_id: str):
    folder = job_path(job_id)
    project = folder / "project_merged.3mf"

    if not project.exists():
        project = nas_3mf_path(job_id)

    if not project:
        return JSONResponse({"error": "No merged 3MF found"}, status_code=404)

    return FileResponse(project, filename=project.name, media_type="model/3mf")

# =========================
# STEP 3 — SLICE FINAL 3MF
# =========================

@app.post("/slice")
def slice_project(job_id: str = Form(...)):
    folder = job_path(job_id)
    project = folder / "project_merged.3mf"

    if not project.exists():
        return JSONResponse({"error": "No merged 3MF found"}, status_code=404)

    command = [
        ORCA_PATH,
        str(project),
        "--slice",
        "0",
        "--outputdir",
        str(folder),
    ]

    result = run_command(command, folder / "slice.log")

    gcode = find_first_file(folder, "*.gcode")

    if result.returncode != 0 or not gcode:
        return JSONResponse(
            {
                "status": "failed_slice",
                "stdout": result.stdout,
                "stderr": result.stderr,
            },
            status_code=500,
        )

    # Archivage permanent du GCODE sur le NAS.
    archived_gcode = NAS_GCODE_DIR / f"{job_id}__{gcode.name}"
    shutil.copy2(gcode, archived_gcode)

    return {
        "status": "sliced",
        "job_id": job_id,
        "gcode_url": f"/gcode/{job_id}",
        "gcode": str(gcode),
        "archived_gcode": str(archived_gcode),
    }


@app.get("/gcode/{job_id}")
def get_gcode(job_id: str):
    gcode = find_job_gcode(job_id)

    if not gcode:
        return JSONResponse({"error": "No gcode found"}, status_code=404)

    return FileResponse(gcode, filename=gcode.name)



# =========================
# PRINTER — MOONRAKER / ENDER 3 V3 KE
# =========================

@app.get("/printer/config")
def printer_config():
    return {
        "printer_ip": PRINTER_IP,
        "moonraker_url": MOONRAKER_URL,
        "interface_url": PRINTER_INTERFACE_URL,
    }


@app.get("/printer/status")
def printer_status():
    try:
        info = requests.get(f"{MOONRAKER_URL}/printer/info", timeout=5).json()
        objects = requests.get(
            f"{MOONRAKER_URL}/printer/objects/query?print_stats&virtual_sdcard&extruder&heater_bed",
            timeout=5,
        ).json()

        return {
            "status": "online",
            "info": info.get("result", info),
            "objects": objects.get("result", objects),
        }
    except Exception as exc:
        return JSONResponse(
            {
                "status": "offline",
                "error": str(exc),
                "moonraker_url": MOONRAKER_URL,
            },
            status_code=503,
        )




@app.get("/printer/live-status")
def printer_live_status():
    """Statut simplifié pour le dashboard Hub 3D.

    Tous les appels Moonraker restent côté backend. Le navigateur ne parle jamais
    directement à http://192.168.1.193:7125, ce qui permet le reverse proxy
    Nginx/Cloudflare via /api.
    """
    try:
        response = requests.get(
            f"{MOONRAKER_URL}/printer/objects/query",
            params={
                "print_stats": "",
                "display_status": "",
                "virtual_sdcard": "",
                "extruder": "",
                "heater_bed": "",
                "webhooks": "",
            },
            timeout=5,
        )
        response.raise_for_status()
        payload = response.json()
        status = payload.get("result", {}).get("status", {})

        print_stats = status.get("print_stats", {}) or {}
        display_status = status.get("display_status", {}) or {}
        virtual_sdcard = status.get("virtual_sdcard", {}) or {}
        extruder = status.get("extruder", {}) or {}
        heater_bed = status.get("heater_bed", {}) or {}
        webhooks = status.get("webhooks", {}) or {}

        state = print_stats.get("state") or webhooks.get("state") or "unknown"
        filename = print_stats.get("filename") or None
        message = print_stats.get("message") or display_status.get("message") or webhooks.get("state_message") or ""

        progress_raw = virtual_sdcard.get("progress")
        if progress_raw is None:
            progress_raw = display_status.get("progress")
        progress = float(progress_raw or 0)
        progress_percent = round(max(0, min(1, progress)) * 100, 1)

        elapsed = float(print_stats.get("print_duration") or 0)
        total_estimated = None
        remaining = None
        if progress > 0 and state == "printing":
            total_estimated = elapsed / progress
            remaining = max(0, total_estimated - elapsed)

        return {
            "online": True,
            "state": state,
            "state_label": _format_state_label(state),
            "message": message,
            "filename": filename,
            "progress": progress_percent,
            "elapsed_seconds": _seconds_to_int(elapsed),
            "remaining_seconds": _seconds_to_int(remaining),
            "estimated_total_seconds": _seconds_to_int(total_estimated),
            "extruder_temp": round(float(extruder.get("temperature") or 0), 1),
            "extruder_target": round(float(extruder.get("target") or 0), 1),
            "bed_temp": round(float(heater_bed.get("temperature") or 0), 1),
            "bed_target": round(float(heater_bed.get("target") or 0), 1),
            "moonraker_url": MOONRAKER_URL,
            "interface_url": PRINTER_INTERFACE_URL,
        }
    except Exception as exc:
        return JSONResponse(
            {
                "online": False,
                "state": "offline",
                "state_label": "Hors ligne",
                "message": str(exc),
                "filename": None,
                "progress": 0,
                "elapsed_seconds": None,
                "remaining_seconds": None,
                "extruder_temp": None,
                "extruder_target": None,
                "bed_temp": None,
                "bed_target": None,
                "moonraker_url": MOONRAKER_URL,
                "interface_url": PRINTER_INTERFACE_URL,
            },
            status_code=503,
        )


@app.post("/printer/upload-gcode")
def printer_upload_gcode(job_id: str = Form(...)):
    gcode = find_job_gcode(job_id)

    if not gcode:
        return JSONResponse(
            {"error": "No GCODE found. Slice the job first."},
            status_code=404,
        )

    try:
        with gcode.open("rb") as buffer:
            response = requests.post(
                f"{MOONRAKER_URL}/server/files/upload",
                files={"file": (gcode.name, buffer)},
                data={"root": "gcodes"},
                timeout=120,
            )

        payload = response.json()

        if response.status_code >= 400:
            return JSONResponse(payload, status_code=response.status_code)

        item = payload.get("item", {})
        filename = item.get("path", gcode.name)

        return {
            "status": "uploaded_to_printer",
            "job_id": job_id,
            "filename": filename,
            "moonraker": payload,
            "workspace_cleaned": False,
        }

    except Exception as exc:
        return JSONResponse(
            {"status": "upload_failed", "error": str(exc)},
            status_code=500,
        )


@app.post("/printer/start")
def printer_start(filename: str = Form(...)):
    try:
        response = requests.post(
            f"{MOONRAKER_URL}/printer/print/start",
            json={"filename": filename},
            timeout=30,
        )

        payload = response.json()
        if response.status_code >= 400:
            return JSONResponse(payload, status_code=response.status_code)

        return {
            "status": "print_started",
            "filename": filename,
            "moonraker": payload,
        }
    except Exception as exc:
        return JSONResponse(
            {"status": "print_failed", "error": str(exc)},
            status_code=500,
        )


@app.post("/printer/upload-and-start")
def printer_upload_and_start(job_id: str = Form(...)):
    upload = printer_upload_gcode(job_id)
    if isinstance(upload, JSONResponse):
        return upload

    filename = upload.get("filename")
    if not filename:
        return JSONResponse({"error": "Upload succeeded but filename is missing"}, status_code=500)

    form_filename = filename
    try:
        response = requests.post(
            f"{MOONRAKER_URL}/printer/print/start",
            json={"filename": form_filename},
            timeout=30,
        )
        payload = response.json()
        if response.status_code >= 400:
            return JSONResponse(payload, status_code=response.status_code)

        return {
            "status": "uploaded_and_started",
            "job_id": job_id,
            "filename": filename,
            "moonraker": payload,
        }
    except Exception as exc:
        return JSONResponse(
            {"status": "print_failed", "filename": filename, "error": str(exc)},
            status_code=500,
        )

# =========================
# LEGACY ENDPOINT
# =========================

@app.post("/print")
def legacy_print(file: UploadFile = File(...)):
    uploaded = upload_stl(file)
    return {
        "status": "uploaded_only",
        "message": "Use /generate-3mf then /slice for the new pipeline",
        **uploaded,
    }
