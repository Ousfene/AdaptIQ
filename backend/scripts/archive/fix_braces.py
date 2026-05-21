import os

chapters_dir = 'c:/Users/mns/Desktop/mw/rapport/mo2nes/Chapitres'

for filename in os.listdir(chapters_dir):
    if not filename.endswith('.tex'): continue
    filepath = os.path.join(chapters_dir, filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    changed = False
    for i, line in enumerate(lines):
        if '\\begin{longtable}' in line:
            if '}|' in line:
                lines[i] = line.replace('}|', '|')
                changed = True
                
    if changed:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        print("Fixed braces in", filename)
