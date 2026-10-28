from pathlib import Path

from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH).parent
datas = []
binaries = []
hiddenimports = []
for pacote in ("vosk", "sounddevice", "_sounddevice_data", "pystray", "PIL"):
    pacote_datas, pacote_binaries, pacote_hidden = collect_all(pacote)
    datas += pacote_datas
    binaries += pacote_binaries
    hiddenimports += pacote_hidden

a = Analysis(
    [str(root / "packaging" / "entry_wake.py")],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["faster_whisper", "google.genai", "fastapi", "uvicorn", "av", "onnxruntime"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="GideonWake",
    console=False,
    disable_windowed_traceback=False,
    onefile=True,
)
