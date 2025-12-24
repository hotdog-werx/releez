import sys
from pathlib import Path

# Allow `import releez` when running tests from the repo root without installing the package.
PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))
