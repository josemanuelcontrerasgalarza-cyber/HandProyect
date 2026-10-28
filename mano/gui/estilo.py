"""Tema oscuro de la aplicación."""

ACENTO = "#00e0b0"
AVISO = "#ffb020"
PELIGRO = "#ff5c5c"

HOJA_ESTILO = f"""
* {{ font-size: 10pt; }}
QWidget {{ background: #0f1119; color: #e6e8ef; }}
QMainWindow::separator {{ background: #2a2f40; width: 1px; height: 1px; }}
QToolBar {{ background: #141722; border: 0; border-bottom: 1px solid #2a2f40; spacing: 6px; padding: 4px; }}
QStatusBar {{ background: #141722; border-top: 1px solid #2a2f40; color: #9aa0b4; }}
QTabWidget::pane {{ border: 1px solid #2a2f40; border-radius: 6px; top: -1px; }}
QTabBar::tab {{ background: #141722; color: #9aa0b4; padding: 8px 16px; border: 1px solid #2a2f40;
               border-bottom: 0; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; }}
QTabBar::tab:selected {{ background: #181b26; color: {ACENTO}; }}
QTabBar::tab:hover {{ color: #e6e8ef; }}
QGroupBox {{ background: #181b26; border: 1px solid #2a2f40; border-radius: 8px; margin-top: 14px;
            padding: 10px 8px 8px 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #9aa0b4; }}
QGroupBox QWidget {{ background: transparent; }}
QPushButton {{ background: #232838; border: 1px solid #2f3548; border-radius: 6px; padding: 6px 12px; }}
QPushButton:hover {{ border-color: {ACENTO}; }}
QPushButton:pressed {{ background: #1b1f2c; }}
QPushButton:checked {{ background: #0f3b33; border-color: {ACENTO}; color: {ACENTO}; }}
QPushButton:disabled {{ color: #5b6178; border-color: #23283a; }}
QPushButton[rol="primario"] {{ background: #0f3b33; border-color: {ACENTO}; color: {ACENTO}; font-weight: bold; }}
QPushButton[rol="peligro"] {{ background: #3b1418; border-color: {PELIGRO}; color: {PELIGRO}; font-weight: bold; }}
QPushButton[rol="aviso"] {{ border-color: {AVISO}; color: {AVISO}; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
    background: #0b0d14; border: 1px solid #2a2f40; border-radius: 6px; padding: 4px 6px;
    selection-background-color: #1f5f53; }}
QComboBox QAbstractItemView {{ background: #141722; border: 1px solid #2a2f40; selection-background-color: #1f5f53; }}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{ border-color: {ACENTO}; }}
QSlider::groove:horizontal {{ height: 6px; background: #262b3b; border-radius: 3px; }}
QSlider::groove:vertical {{ width: 6px; background: #262b3b; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {ACENTO}; border-radius: 3px; }}
QSlider::add-page:vertical {{ background: {ACENTO}; border-radius: 3px; }}
QSlider::handle {{ background: #e6e8ef; border: 2px solid {ACENTO}; width: 14px; height: 14px;
                  margin: -6px; border-radius: 8px; }}
QTableWidget, QListWidget {{ background: #0b0d14; border: 1px solid #2a2f40; border-radius: 6px;
                             gridline-color: #232838; alternate-background-color: #11141d; }}
QTableWidget::item:selected, QListWidget::item:selected {{ background: #1f5f53; color: #ffffff; }}
QHeaderView::section {{ background: #141722; color: #9aa0b4; border: 0; border-right: 1px solid #2a2f40;
                       border-bottom: 1px solid #2a2f40; padding: 4px; }}
QProgressBar {{ background: #0b0d14; border: 1px solid #2a2f40; border-radius: 6px; text-align: center; height: 16px; }}
QProgressBar::chunk {{ background: {ACENTO}; border-radius: 5px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid #3a4157; border-radius: 4px; background: #0b0d14; }}
QCheckBox::indicator:checked {{ background: {ACENTO}; border-color: {ACENTO}; }}
QScrollBar:vertical {{ background: #0f1119; width: 10px; }}
QScrollBar::handle:vertical {{ background: #2a2f40; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QLabel[rol="titulo"] {{ font-size: 13pt; font-weight: bold; color: {ACENTO}; }}
QLabel[rol="grande"] {{ font-size: 16pt; font-weight: bold; color: #ffd166; }}
QLabel[rol="sub"] {{ color: #9aa0b4; }}
QLabel[rol="instruccion"] {{ font-size: 14pt; font-weight: bold; color: {AVISO}; }}
QToolTip {{ background: #232838; color: #e6e8ef; border: 1px solid {ACENTO}; }}
"""
