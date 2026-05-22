import sys
from pathlib import Path

# Add python/ to path for examples.*
root = Path(__file__).resolve().parents[1]
if str(root) not in sys.path:
    sys.path.insert(0, str(root))
