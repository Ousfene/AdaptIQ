import json, re

with open(r'c:\Users\mns\Desktop\mw\mhd\AdaptIQ_Complete_Postman.json') as f:
    data = json.load(f)

defined_vars = {v['key'] for v in data['variable']}
print('DEFINED VARIABLES:', sorted(defined_vars))

raw = json.dumps(data)
used_vars = set(re.findall(r'\{\{(\w+)\}\}', raw))
print('\nUSED VARIABLES:', sorted(used_vars))

set_vars = set(re.findall(r"collectionVariables\.set\('(\w+)'", raw))
print('\nSET BY SCRIPTS:', sorted(set_vars))

undefined = used_vars - defined_vars
if undefined:
    print('\nWARNING - Used but NOT defined:', undefined)
else:
    print('\nAll used variables are defined.')

dynamic = used_vars - {'baseUrl', 'email1', 'email2', 'password', 'adminBootstrapKey'}
unset = dynamic - set_vars
if unset:
    print('WARNING - Used but NOT set by any script:', unset)
else:
    print('All dynamic variables are set by test scripts.')

def count_items(items, count=0):
    for item in items:
        if 'item' in item:
            count = count_items(item['item'], count)
        elif 'request' in item:
            count += 1
    return count

total = count_items(data['item'])
print(f'\nTotal requests: {total}')
