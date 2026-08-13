from pathlib import Path

ROOT = Path.cwd()
DIST_DIR = ROOT / "dist"
APP_BUNDLE = "台账报表生成器.app"
INSTALL_GUIDE = "安装说明.md"

files = [str(DIST_DIR / APP_BUNDLE), str(DIST_DIR / INSTALL_GUIDE)]
symlinks = {"Applications": "/Applications"}
icon_locations = {
    APP_BUNDLE: (145, 180),
    "Applications": (435, 180),
    INSTALL_GUIDE: (290, 285),
}
window_rect = ((200, 200), (580, 400))
default_view = "icon-view"
show_status_bar = False
show_tab_view = False
show_toolbar = False
