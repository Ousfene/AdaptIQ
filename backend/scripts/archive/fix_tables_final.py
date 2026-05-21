import glob
import re

for f in glob.glob('c:/Users/mns/Desktop/mw/rapport/mo2nes/Chapitres/*.tex'):
    with open(f, 'r', encoding='utf-8') as file:
        lines = file.readlines()
        
    changed = False
    for i, line in enumerate(lines):
        if r'\begin{longtable}' in line:
            prefix = r'\begin{longtable}{'
            idx = line.find(prefix)
            if idx != -1:
                # get everything after \begin{longtable}{
                fmt = line[idx + len(prefix):].strip()
                
                # if there is a trailing brace from a previous mess up, we might have it in fmt.
                # replace }}}| and }}|
                fmt = fmt.replace('}}}|', '}|')
                fmt = fmt.replace('}}|', '}|')
                
                # fix unclosed p{...|
                fmt = re.sub(r'p\{([^}|]+)\|', r'p{\1}|', fmt)
                
                if not fmt.endswith('}'):
                    fmt = fmt + '}'
                    
                # rebuild line
                lines[i] = line[:idx] + prefix + fmt + '\n'
                changed = True
                
    if changed:
        with open(f, 'w', encoding='utf-8') as file:
            file.writelines(lines)
        print("Fixed tables in", f)
