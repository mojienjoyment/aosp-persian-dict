import os, glob, sys, regex
from spylls.hunspell import Dictionary
from wordlist import Wordlist
from wordlist_combined import WordlistCombined, DictionaryHeader

# --- CUSTOM FUNCTION TO BYPASS HUNSPELL FILTER ---
# This mimics add_line but trusts the cleaned text 100%, 
# allowing modern slang to enter the dict while still building bigrams.
def add_line_trusting_source(w, line):
    split_line = line.split()
    previous_word = None
    
    for word in split_line:
        if len(word) >= 48 or word.isspace() or word.isnumeric():
            previous_word = None
            continue
            
        # Clean up Persian/Arabic punctuation
        word = word.replace('’', '\'')
        
        # Use the regex from the Wordlist class to find valid word characters
        re_find = regex.findall(w.possible_word_regex, word)
        if not re_find:
            previous_word = None
            continue
            
        word = re_find[0]
        
        # Skip single characters if you want, or keep them. 
        # (Persian often uses single letter prefixes/suffixes, so we keep them)
        
        # 1. Add the word directly (NO dictionary check!)
        w.add_word(word, add_to_count=True)
        
        # 2. Build the bigram (next-word data for glide typing)
        if previous_word is not None:
            previous_info = w.word_infos[previous_word]
            previous_next = previous_info.get("next", {})
            previous_next[word] = previous_next.get(word, 0) + 1
            previous_info["next"] = previous_next
            
        previous_word = word

def add_sentence_file_trusting(w, filename):
    with open(filename, encoding='utf-8') as f:
        for line in f:
            add_line_trusting_source(w, line)
# -----------------------------------------------

print("=== 1. Loading Hunspell Dictionary ===")
# We still load it because we need it for Step 3 (Unmunching grammar rules)
hunspell_dict = Dictionary.from_files("fa-IR")
w = Wordlist(dictionary=hunspell_dict)

print("=== 2. Processing Cleaned Wikipedia Text (Trusting Source) ===")
cleaned_files = sorted(glob.glob("wiki_cleaned/**/wiki_*", recursive=True))
log_file = "processing_log.txt"

processed = set()
if os.path.exists(log_file):
    with open(log_file, 'r', encoding='utf-8') as f: processed = set(f.read().splitlines())

for filepath in cleaned_files:
    filename = os.path.relpath(filepath, "wiki_cleaned")
    if filename in processed: continue
    
    print(f"Processing {filename}...")
    
    # USE THE CUSTOM FUNCTION INSTEAD OF add_sentence_file
    add_sentence_file_trusting(w, filepath)
    
    with open(log_file, 'a', encoding='utf-8') as f: f.write(filename + '\n')

print("=== 3. Expanding Grammar Rules (Unmunching) ===")
# This uses the .aff and .dic to generate valid plurals and conjugations
w.add_words_from_dictionary(dict_word_cache_file="fa_unmunched_cache.txt")

print("=== 4. Generating .combined file ===")
combined = w.create_wordlist_combined(
    add_nosuggest=True,
    add_bigrams=True,
    header=DictionaryHeader("fa_IR", "main", "Persian Wikipedia Modern", 19)
)
combined.write_to_file("main_fa_IR.combined")
print("Saved main_fa_IR.combined")
