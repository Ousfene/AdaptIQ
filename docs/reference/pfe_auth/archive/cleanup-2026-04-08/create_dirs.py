import os
base = r'c:\Users\mns\Desktop\pfe_auth\backend'
dirs = ['routers']
for d in dirs:
    path = os.path.join(base, d)
    os.makedirs(path, exist_ok=True)
    print(f'Created: {path}')
print('ALL DONE')

