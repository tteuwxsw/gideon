from pathlib import Path

root = Path(SPECPATH).parent

a = Analysis(
    [str(root / "packaging" / "entry_cli.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    excludes=[
        "gideon.tools",
        "gideon.voz",
        "gideon.servidor",
        "gideon.cerebro",
        "gideon.mcp",
        "numpy",
        "faster_whisper",
        "google",
        "sounddevice",
        "vosk",
        "PIL",
        "fastapi",
        "uvicorn",
        "pydantic",
        "keyring",
        "av",
        "ctranslate2",
        "onnxruntime",
        "edge_tts",
        "anyio",
        "websockets",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="GideonCtl",
    console=True,
    disable_windowed_traceback=False,
    onefile=True,
    strip=False,
    upx=True,
)
