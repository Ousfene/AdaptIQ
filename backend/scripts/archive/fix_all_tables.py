import os
import re

chapters_dir = 'c:/Users/mns/Desktop/mw/rapport/mo2nes/Chapitres'

for filename in os.listdir(chapters_dir):
    if not filename.endswith('.tex'): continue
    filepath = os.path.join(chapters_dir, filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    def fix_longtable_format(match):
        # The entire matched line is \begin{longtable}{FORMAT}
        # We need to extract the FORMAT and fix it.
        fmt = match.group(1)
        
        # 1. Fix missing closing braces on p columns: p{1.2cm| -> p{1.2cm}|
        fmt = re.sub(r'p\{([0-9\.]+(?:cm|pt|mm|in|ex|em))\|', r'p{\1}|', fmt)
        
        # 2. Fix extra closing braces: }| -> |  (but wait, p{1.2cm}| is correct! It contains }| )
        # If there are stray braces at the end like |c|c|}
        if fmt.endswith('|}'):
            fmt = fmt[:-1]
        
        # 3. Clean up consecutive braces like }}
        fmt = fmt.replace('}}', '}')
        
        # 4. If there's a stray } at the end but the format is correct.
        # Let's just remove any } that does not correspond to a p{...}
        # A simple way to reconstruct the format:
        # Just find all occurrences of column specifiers.
        
        # Actually, let's just do a clean pass.
        # Find all valid specifiers in the messy string.
        # Valid specifiers: |, c, l, r, p{...}
        
        clean_fmt = ""
        i = 0
        while i < len(fmt):
            if fmt[i] in '|clr':
                clean_fmt += fmt[i]
                i += 1
            elif fmt[i] == 'p':
                if i+1 < len(fmt) and fmt[i+1] == '{':
                    clean_fmt += 'p{'
                    i += 2
                    val = ""
                    while i < len(fmt) and fmt[i] not in '}|':
                        val += fmt[i]
                        i += 1
                    clean_fmt += val + '}'
                    # skip any extra '}' or '{'
                    while i < len(fmt) and fmt[i] in '}':
                        i += 1
                else:
                    clean_fmt += 'p'
                    i += 1
            else:
                # ignore stray characters like extra } or {
                i += 1
                
        return f"\\begin{{longtable}}{{{clean_fmt}}}"

    new_content = re.sub(r'\\begin\{longtable\}\{(.*?)\}', fix_longtable_format, content)

    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print("Fixed format in", filename)
