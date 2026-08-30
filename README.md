# aosp-persian-dict
🇮🇷 Modern Persian (Farsi) dictionary for HeliBoard &amp; AOSP keyboards. Optimized for accurate glide typing, modern vocabulary, and next-word suggestions using Wikipedia data.
# aosp-persian-dict

# 🇮🇷 HeliBoard Persian Dictionary (Wikipedia-Based)

A highly optimized, modern, and comprehensive Persian (Farsi) dictionary for [HeliBoard](https://github.com/Helium314/HeliBoard) and other AOSP-based Android keyboards. 

Default Persian dictionaries often suffer from outdated vocabulary, poor glide-typing accuracy. This project solves that by dynamically generating a dictionary from the latest [**Persian Wikipedia**](https://dumps.wikimedia.org/fawiki/latest/) (05-Aug-2026) dumps and [**Hunspell** grammar rules](https://github.com/LibreOffice/dictionaries/tree/master/fa_IR). It ensures accurate next-word suggestions and flawless swipe-typing paths.

## ✨ Features

- **Optimized for Glide Typing:** Accurate word frequencies (`f` values) calculated from millions of real sentences ensure the keyboard guesses the correct word when you swipe.
- **Modern Vocabulary:** Captures contemporary slang, tech terms, and modern names directly from Wikipedia by bypassing outdated spell-check filters.
- **Next-Word Suggestions (Bigrams):** Real sentence structures from Wikipedia train the keyboard to suggest logical next words.
- **Grammar & Conjugation:** Uses Hunspell `.aff` rules to "unmunch" and include all valid Persian plurals, verb conjugations, and ZWNJ (نیم‌فاصله) compounds.

---

## 📱 Installation (For Users)

If you just want to use the dictionary on your phone, follow these steps:

1. **Download the Dictionary:** 
   Go to the [Releases](../../releases) page or the [`dicts/`](./dicts/) folder and download `main_fa_IR.dict`.
2. **Transfer to your Phone:** 
   Copy the `.dict` file to your Android device's internal storage.
3. **Enable in HeliBoard:**
   - Open **HeliBoard Settings** -> **Dictionary**
   - Add Dict file to it.

---

## 🛠️ Building from Source

If you want to update the dictionary with the latest Wikipedia dump or modify the build process, you can build it yourself. 

### Prerequisites
- **OS:** Linux (Arch, Ubuntu, etc.) is highly recommended for performance. 
- **Python 3.10+** and **PyPy3** (PyPy is crucial for speed).
- **Java Runtime Environment (JRE)** (for the final compilation step).
- **~20 GB of free disk space** and at least **8 GB of RAM** (plus swap space recommended).

### Step 1: Clone and Setup

```bash
git clone https://github.com/mojienjoyment/aosp-persian-dict.git
cd aosp-persian-dict/scripts

# Install Python dependencies for PyPy
pypy3 -m pip install spylls regex wikiextractor

# Download the Persian Hunspell Dictionary
wget https://raw.githubusercontent.com/LibreOffice/dictionaries/master/fa_IR/fa-IR.aff
wget https://raw.githubusercontent.com/LibreOffice/dictionaries/master/fa_IR/fa-IR.dic
```

### Step 2: Download and Extract Wikipedia
```bash
# Download the Persian Wikipedia dump (~1.5 GB)
wget -O fawiki.xml.bz2 https://dumps.wikimedia.org/fawiki/latest/fawiki-latest-pages-articles-multistream.xml.bz2

# Extract to JSON files (Takes ~15-30 mins)
pypy3 -m wikiextractor.WikiExtractor fawiki.xml.bz2 -o wiki_extracted --json
```

### Step 3: Clean the Text
Strip out wiki-markup, HTML, and URLs so they don't become dictionary words.
```bash
pypy3 clean_wiki.py
```

### Step 4: Build the Dictionary
This script processes the text, injects titles, unmunches the Hunspell grammar, and generates the `.combined` file.
```bash
pypy3 build_dict.py
```
*(Note: This is the longest step. On a standard laptop, it takes 2-4 hours. If it crashes due to RAM, just run it again; it uses a log file to resume exactly where it left off!)*

### Step 5: Compile to `.dict`
Use the AOSP Java compiler to create the final binary.
```bash
# Download dicttool if you don't have it in the tools/ folder
wget -O ../tools/dicttool_aosp.jar https://codeberg.org/Helium314/aosp-dictionaries/raw/branch/main/tools/dicttool_aosp.jar

# Compile the dictionary
java -jar ../tools/dicttool_aosp.jar makedict -s main_fa_IR.combined -d ../dicts/main_fa_IR.dict
```

---

## 🧠 How it Works

1. **The "Trust Source" Bypass:** The default Hunspell dictionary for Persian is quite small (~10k roots). To ensure new words from Wikipedia aren't rejected, the `build_dict.py` script uses a custom logic that trusts the cleaned Wikipedia text, allowing modern vocabulary to enter the dictionary with accurate frequencies.
2. **Hunspell Unmunching:** Even though we trust the text for modern words, we still need correct grammar. The script reads the `fa-IR.aff` rules and generates all valid Persian plurals, verb conjugations, and ZWNJ compounds, ensuring the keyboard doesn't mark correct grammar as a typo.
3. **Glide Typing Math:** The keyboard's glide engine uses the formula: `Final Score = (Geometric Match) × (Dictionary Frequency)`. By calculating frequencies from millions of Wikipedia words, common words like "سلام" get a massive frequency weight, ensuring they win the glide-typing match against geometrically similar but less common words.

---

## 🙏 Acknowledgments & Sources

This project would not be possible without the incredible work of the open-source community:

- **[HeliBoard](https://github.com/Helium314/HeliBoard)** & **[Helium314](https://codeberg.org/Helium314)**: For maintaining the best HeliBoard keyboard and providing the core Python scripts (`wordlist.py`, `wordlist_combined.py`, `dicttool_aosp.jar`).
- **[Wikimedia Foundation](https://www.wikimedia.org/)**: For providing the massive, constantly updated Persian Wikipedia dumps used as the primary corpus.
- **[LibreOffice / Hunspell](https://github.com/LibreOffice/dictionaries)**: For maintaining the Persian (`fa_IR`) Hunspell dictionary, which provides the grammatical rules.
- **[spylls](https://github.com/zverok/spylls)**: For the pure-Python Hunspell implementation.
- **[wikiextractor](https://github.com/attardi/wikiextractor)**: For the excellent tool used to parse the massive Wikipedia XML dumps.

---

## ⚖️ License

- **The Build Scripts (`wordlist.py`, `build_dict.py`, `clean_wiki.py`, etc.):** Licensed under the **Apache License 2.0** (inherited from the AOSP/HeliBoard project).
- **The Dictionary Data (`main_fa_IR.dict`):** The compiled dictionary contains data derived from Wikipedia and Hunspell. It is licensed under **CC BY-SA 4.0** (Creative Commons Attribution-ShareAlike) and the **GNU LGPL** (for the Hunspell wordlists), respectively. You are free to use, modify, and distribute it for your keyboard projects.

See the [LICENSE](./LICENSE) file for details.
