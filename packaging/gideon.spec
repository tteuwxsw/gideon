from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

root = Path(SPECPATH).parent
datas = [
    (str(root / "gideon" / "web" / "index.html"), "gideon/web"),
    (str(root / "gideon" / "web" / "dist"), "gideon/web/dist"),
    (str(root / "gideon" / "web" / "avatar"), "gideon/web/avatar"),
    (str(root / "gideon" / "voz" / "pockettts_sidecar.py"), "gideon/voz"),
    (str(root / "habilidades"), "habilidades"),
]
binaries = []
hiddenimports = collect_submodules("gideon")

for pacote in ("faster_whisper", "ctranslate2", "av", "onnxruntime", "_sounddevice_data", "keyring", "win32ctypes", "vosk"):
    pacote_datas, pacote_binaries, pacote_hidden = collect_all(pacote)
    datas += pacote_datas
    binaries += pacote_binaries
    hiddenimports += pacote_hidden

a = Analysis(
    [str(root / "packaging" / "entry_gideon.py")],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    excludes=["tkinter", "pytest", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Gideon",
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="Gideon",
)
