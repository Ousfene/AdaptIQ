import os
import re

chapters_dir = 'c:/Users/mns/Desktop/mw/rapport/mo2nes/Chapitres'

def fix_table(content):
    pattern = re.compile(
        r'\\begin\{longtable\}\{(.*?)\n'
        r'(?:\\caption\{(.*?)\}\n)?'
        r'(?:\\label\{(.*?)\}\s*\\\\\n| \\\\\n)?'
        r'(.*?)\}\s*\n',
        re.DOTALL
    )
    
    def repl(m):
        fmt1 = m.group(1).strip()
        caption = m.group(2)
        label = m.group(3)
        fmt2 = m.group(4).strip()
        
        full_fmt = f"{fmt1}}}{fmt2}" if fmt2 else fmt1 + "}"
        
        res = f"\\begin{{longtable}}{{{full_fmt}}}\n"
        if caption:
            res += f"\\caption{{{caption}}}\n"
        if label:
            res += f"\\label{{{label}}} \\\\\n"
        elif caption:
            res += "\\\\\n"
        return res
        
    return pattern.sub(repl, content)

for filename in os.listdir(chapters_dir):
    if not filename.endswith('.tex'): continue
    filepath = os.path.join(chapters_dir, filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    new_content = fix_table(content)
    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print("Fixed", filename)
