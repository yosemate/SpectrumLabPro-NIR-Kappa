import os
from pathlib import Path
base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home()/".local"/"share"))) / "SpectrumLabPro"
os.environ.setdefault("SPECTRUM_LAB_DATA_DIR", str(base))
from main import main
if __name__ == "__main__":
    main()
