import os
import re

chapters_dir = 'c:/Users/mns/Desktop/mw/rapport/mo2nes/Chapitres'

table_pattern = re.compile(r'\\begin\{table\}\[H\]\s*\\centering\s*(.*?)\\end\{table\}', re.DOTALL)
tabular_pattern = re.compile(r'\\begin\{tabular\}\{(.*?)\}(.*?)\\end\{tabular\}', re.DOTALL)
caption_pattern = re.compile(r'\\caption\{(.*?)\}', re.DOTALL)
label_pattern = re.compile(r'\\label\{(.*?)\}', re.DOTALL)

for filename in os.listdir(chapters_dir):
    if not filename.endswith('.tex'): continue
    filepath = os.path.join(chapters_dir, filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    def replace_table(match):
        inner = match.group(1)
        
        tab_match = tabular_pattern.search(inner)
        if not tab_match:
            return match.group(0) # don't replace if no tabular
            
        format_str = tab_match.group(1)
        body = tab_match.group(2).strip()
        
        cap_match = caption_pattern.search(inner)
        caption = cap_match.group(1) if cap_match else ""
        
        lab_match = label_pattern.search(inner)
        label = lab_match.group(1) if lab_match else ""
        
        # Build longtable
        res = f"\\begin{{longtable}}{{{format_str}}}\n"
        if caption:
            res += f"\\caption{{{caption}}}\n"
        if label:
            res += f"\\label{{{label}}} \\\\\n"
        elif caption:
            res += " \\\\\n"
            
        res += body + "\n"
        res += "\\end{longtable}"
        
        return res

    new_content = table_pattern.sub(replace_table, content)
    
    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Updated {filename}")
