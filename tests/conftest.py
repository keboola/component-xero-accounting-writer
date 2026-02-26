import sys
from pathlib import Path

# Add src/ to path so component.py can resolve its relative imports (client, writers, etc.)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
