with open('run_compliance_claim.py', encoding='utf-8') as f:
    lines = f.readlines()
main_ln = None
name_ln = None
for i, line in enumerate(lines):
    if line.strip().startswith('def main():'):
        main_ln = i + 1
    if line.strip().startswith('if __name__'):
        name_ln = i + 1
print(f'Total lines: {len(lines)}')
print(f'def main() at line {main_ln}')
print(f'if __name__ at line {name_ln}')
if main_ln and name_ln:
    if main_ln < name_ln:
        print('OK: main defined before __name__')
    else:
        print('ERROR: main defined after __name__')
