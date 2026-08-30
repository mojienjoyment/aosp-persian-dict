import os, re, json, glob

input_dir = "wiki_extracted"
output_dir = "wiki_cleaned"
os.makedirs(output_dir, exist_ok=True)

patterns = [
    re.compile(r'<ref.*?</ref>', re.DOTALL),
    re.compile(r'<[^>]+>'),
    re.compile(r'https?://\S+'),
    re.compile(r'\[\[([^\]|]*\|)?([^\]]*)\]\]'),
    re.compile(r'\{\{[^\}]*\}\}'),
    re.compile(r'&[a-zA-Z]+;|&#[0-9]+;'),
]

def clean_text(text):
    for pattern in patterns:
        text = pattern.sub(' ', text)
    return re.sub(r'\s+', ' ', text).strip()

print("Cleaning files...")
for filepath in glob.glob(f"{input_dir}/**/wiki_*", recursive=True):
    outpath = filepath.replace(input_dir, output_dir)
    os.makedirs(os.path.dirname(outpath), exist_ok=True)
    with open(filepath, 'r', encoding='utf-8') as f_in, open(outpath, 'w', encoding='utf-8') as f_out:
        for line in f_in:
            try:
                data = json.loads(line)
                if 'text' in data:
                    cleaned = clean_text(data['text'])
                    if cleaned: f_out.write(cleaned + '\n')
            except: continue
print("Cleaning complete!")
