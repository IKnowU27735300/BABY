# Custom PyInstaller hook override for PySide6.QtQml
# Bypasses qmlimportscanner hang while relying on explicitly bundled PySide6/qml assets.

hiddenimports = [
    'PySide6.QtQml',
    'PySide6.QtQuick',
    'PySide6.QtQuickControls2',
]

datas = []



















