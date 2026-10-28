from pathlib import Path

root = Path(SPECPATH).parent
a = Analysis(
    [str(root / "packaging" / "entry_updater.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    excludes=["faster_whisper", "google.genai", "fastapi", "uvicorn", "vosk", "pystray", "PIL"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="GideonUpdater",
    console=False,
    disable_windowed_traceback=False,
    onefile=True,
)
