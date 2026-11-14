"""The captcha image library is imported only when a captcha is shown.

Every page runs page_setup() from src.common.common, which imports
src.common.captcha_. Importing captcha.image at its top cost 0.4 to 1 s of each
app's first page after a restart, the local apps included, which never show a
captcha, and the hosted ones once the captcha is solved.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_page_modules_do_not_import_captcha_image():
    code = (
        "import sys\n"
        "import src.common.common, src.common.captcha_\n"
        "print('captcha.image' in sys.modules)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "False"
