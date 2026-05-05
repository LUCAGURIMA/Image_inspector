from __future__ import annotations

import sys

from PyQt5.QtWidgets import QApplication

from image_inspector.core.runtime import setup_logging
from image_inspector.ui.main_window import MainWindow


def main() -> int:
    setup_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("Image Inspector")
    window = MainWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
