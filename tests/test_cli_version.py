"""Every command answers --version with the package version."""
import subprocess
import sys

import pytest

from lyrics_tool import __version__


@pytest.mark.parametrize("module, prog", [
    ("lyrics_tool.cli_visualizer", "lyricsooo"),
    ("lyrics_tool.cli_fetch", "lyricsooo-fetch"),
    ("lyrics_tool.cli_cook", "lyricsooo-cook"),
])
def test_version_flag(module, prog):
    code = f"import sys; sys.argv = ['{prog}', '--version']; from {module} import main; main()"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.returncode == 0
    assert out.stdout.strip() == f"{prog} {__version__}"
