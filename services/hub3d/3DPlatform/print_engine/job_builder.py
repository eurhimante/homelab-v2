import shutil
import os

TEMPLATE = "templates/base.3mf"

def build_3mf_job(job, output_dir):

    project_path = os.path.join(output_dir, "project.3mf")

    # 1. copie template
    shutil.copy(TEMPLATE, project_path)

    # 2. copie STL dans job folder
    stl_dest = os.path.join(output_dir, "model.stl")
    shutil.copy(job.file_path, stl_dest)

    # ⚠️ ici version SIMPLE
    # (plus tard on injectera STL dans 3MF proprement)

    return project_path