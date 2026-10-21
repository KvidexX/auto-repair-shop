"""Общее QSS-оформление светлого интерфейса «АвтоСервис»."""

STYLE = """
QWidget { font-family: 'Segoe UI'; font-size: 13px; color: #344054; }
QMainWindow, QWidget#central { background: #F5F7FA; }
QFrame#sidebar { background: #FFFFFF; border-right: 1px solid #E5E9F0; }
QLabel#brand { font-size: 22px; font-weight: 700; color: #24334B; }
QLabel#subtitle { font-size: 10px; color: #8A94A5; letter-spacing: 1px; }
QPushButton#nav, QPushButton#activeNav { text-align: left; padding-left: 12px;
    border: none; border-radius: 7px; }
QPushButton#nav:disabled { color: #7C8798; background: transparent; }
QPushButton#nav { color: #7C8798; background: transparent; }
QPushButton#nav:hover { background: #F5F7FA; }
QPushButton#activeNav { background: #EBF1FD; color: #3567C4; font-weight: 600; }
QLabel#pageTitle { font-size: 28px; font-weight: 650; color: #24334B; }
QLabel#muted { color: #8690A0; font-size: 12px; }
QPushButton#primary { background: #386BD6; border: 1px solid #386BD6;
    color: white; border-radius: 7px; font-weight: 600; }
QPushButton#primary:hover { background: #3060C5; }
QPushButton#primary:disabled { background: #F0F2F4; border-color: #E5E9F0; color: #929CAB; }
QPushButton#secondary, QPushButton#danger { background: white; border: 1px solid #DDE3EC;
    border-radius: 6px; padding: 6px 12px; }
QPushButton#secondary:hover { background: #F5F7FA; }
QPushButton#danger { color: #AD5353; border-color: #E9D6D6; }
QPushButton#danger:hover { background: #FDF2F2; }
QPushButton#secondary:disabled, QPushButton#danger:disabled { color: #A4ADBA;
    border-color: #EBEEF3; background: #FAFBFC; }
QDialog#clientDialog, QDialog#carDialog, QDialog#serviceDialog, QDialog#appointmentDialog, QDialog#orderDialog, QDialog#orderCard { background: #FFFFFF; }
QDateEdit { background: white; border: 1px solid #DDE3EC; border-radius: 6px; padding: 6px 9px; }
QDateEdit:focus { border-color: #7396DF; }
QDateEdit:disabled { background: #F8FAFC; color: #929CAB; }
QDateEdit::drop-down { border: none; width: 26px; }
QDateEdit::down-arrow { width: 0; height: 0; }
QCheckBox { spacing: 8px; }
QComboBox { background: white; border: 1px solid #DDE3EC; border-radius: 6px; padding: 6px 9px; }
QComboBox:focus { border-color: #7396DF; }
QComboBox:disabled { background: #F8FAFC; color: #929CAB; }
QComboBox::drop-down { width: 26px; border: none; }
QComboBox::down-arrow { width: 0; height: 0; }
QComboBox QAbstractItemView { background: white; selection-background-color: #EBF1FD;
    selection-color: #294F91; border: 1px solid #DDE3EC; }
QLabel#orderTotal { font-size: 19px; font-weight: 650; color: #24334B; }
QLabel#dialogTitle { font-size: 23px; font-weight: 650; color: #24334B; }
QLabel#formHint { color: #8690A0; font-size: 12px; }
QTextEdit { background: white; border: 1px solid #DDE3EC; border-radius: 6px; padding: 8px; }
QTextEdit:focus { border-color: #7396DF; }
QLineEdit#documentField, QLineEdit#documentField:focus,
QTextEdit#documentReason, QTextEdit#documentReason:focus {
    background: #F8FAFC; color: #344054; border: none; border-radius: 6px; padding: 6px 9px;
}
QFrame#card { background: white; border: 1px solid #E3E8F0; border-radius: 9px; }
QLabel#sectionTitle { font-size: 14px; font-weight: 600; color: #344054; }
QLabel#count { background: #F0F3F7; color: #778397; border-radius: 6px; font-size: 11px; }
QLineEdit { background: #FFFFFF; border: 1px solid #DDE3EC; border-radius: 6px;
    padding: 6px 9px; selection-background-color: #DFE9FF; }
QLineEdit:focus { border-color: #7396DF; }
QTableWidget { background: #FFFFFF; border: none; }
QTableWidget::item { padding-left: 16px; padding-right: 8px; border-bottom: 1px solid #EEF1F5; }
QTableWidget::item:selected { background: #EBF1FD; color: #294F91; }
QHeaderView::section { background: #F8FAFC; color: #818B9C; font-size: 11px;
    font-weight: 600; border: none; border-top: 1px solid #EBEEF3;
    border-bottom: 1px solid #EBEEF3; padding-left: 16px; }
QLabel#plate { color: #909AAA; font-size: 11px; }
QScrollBar:vertical { width: 8px; background: #F8FAFC; }
QScrollBar::handle:vertical { background: #CDD5E1; min-height: 24px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""
