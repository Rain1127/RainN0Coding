import os
import subprocess
import sys
from pathlib import Path


def test_cloud_generated_files_can_share_java_preview_directory():
    env = os.environ.copy()
    env['CODE_OUTPUT_DIR'] = '/opt/rainn0coding/shared/tmp/code_output'
    result = subprocess.run(
        [sys.executable, '-c', 'from config import Config; print(Config.CODE_OUTPUT_DIR)'],
        cwd=Path(__file__).resolve().parents[1], env=env,
        capture_output=True, text=True, check=True,
    )
    assert result.stdout.strip() == env['CODE_OUTPUT_DIR']
