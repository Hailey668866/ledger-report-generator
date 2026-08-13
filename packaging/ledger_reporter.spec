from pathlib import Path


ROOT = Path(SPECPATH).resolve().parent
RESOURCE_DIR = ROOT / "src" / "ledger_reporter" / "resources"

a = Analysis(
    [str(ROOT / "src" / "ledger_reporter" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=[(str(RESOURCE_DIR), "ledger_reporter/resources")],
    hiddenimports=["PySide6.QtSvg"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="台账报表生成器",
    console=False,
)
collection = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    name="台账报表生成器",
)
app = BUNDLE(
    collection,
    name="台账报表生成器.app",
    icon=str(ROOT / "packaging" / "app-icon.icns"),
    bundle_identifier="com.local.ledger-report-generator",
    info_plist={
        "CFBundleName": "台账报表生成器",
        "CFBundleDisplayName": "台账报表生成器",
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
    },
)
