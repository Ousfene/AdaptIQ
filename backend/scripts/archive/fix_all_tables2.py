import os
import re

chapters_dir = 'c:/Users/mns/Desktop/mw/rapport/mo2nes/Chapitres'

for filename in os.listdir(chapters_dir):
    if not filename.endswith('.tex'): continue
    filepath = os.path.join(chapters_dir, filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    def fix_longtable_format(match):
        fmt = match.group(1)
        
        # 1. Fix missing closing braces on p columns: p{1.2cm| -> p{1.2cm}|
        fmt = re.sub(r'p\{([^}|]+)\|', r'p{\1}|', fmt)
        
        # 2. Fix double closing braces: }}| -> }|
        fmt = fmt.replace('}}|', '}|')
        
        # 3. Clean up consecutive braces like }}
        fmt = fmt.replace('}}', '}')
        
        # 4. Fix missing brace at the very end of string: p{2cm -> p{2cm}
        fmt = re.sub(r'p\{([^}|]+)$', r'p{\1}', fmt)
        
        return f"\\begin{{longtable}}{{{fmt}}}"

    new_content = re.sub(r'\\begin\{longtable\}\{(.*?)\}', fix_longtable_format, content)

    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print("Fixed format in", filename)
