import subprocess
import os

ORCA_PATH = r"C:\Program Files\OrcaSlicer\orca-slicer.exe"

def slice_job(project_file, output_dir):

    cmd = [
        ORCA_PATH,
        "--slice", "0",
        project_file,
        "--outputdir", output_dir
    ]

    subprocess.run(cmd, check=True)

    # on suppose qu'un gcode est généré
    gcode_path = os.path.join(output_dir, "output.gcode")

    return gcode_path