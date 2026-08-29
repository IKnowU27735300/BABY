content = open(r'S:\CODE\BABY\ui\qml\SettingsPanel.qml', 'r', encoding='utf-8').read()

# Fix 1: Indent ColumnLayout to be inside ScrollView
content = content.replace(
    '}\n\nColumnLayout {',
    '}\n\n        ColumnLayout {'
)

# Fix 2: Add ColumnLayout close before ScrollView close
content = content.replace(
    '        }  // closes ScrollView\n\n    // ',
    '        }  // closes ColumnLayout\n    }  // closes ScrollView\n\n    // '
)

with open(r'S:\CODE\BABY\ui\qml\SettingsPanel.qml', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed')
print('Braces:', content.count('{'), content.count('}'))


















