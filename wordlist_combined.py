#!/bin/python
from __future__ import annotations
import os
import gzip
import time
import tempfile
import shutil

# todo:
#  allow adding shortcuts
#  use/handle f=whitelist for shortcuts?


class WordAttributes:
    def __init__(self):
        self.f: int = 0
        self.possibly_offensive: bool = False
        self.not_a_word: bool = False
        self.bigrams: dict[str, int] = dict()
        self.shortcuts: dict[str, str] = dict()  # but f can be "whitelist", maybe use string?
        #  or is f=15 always whitelist?
        #  test shortcut with f=15 vs f=whitelist
        #   and word with f=whitelist
        # there are others, like flags=*, or whitelist=*, but those don't seem to have an effect
        self.unknown: dict[str, str] = dict()  # flags=, originalFreq=, whitelist=, and more


class DictionaryHeader:
    def __init__(self, locale: str, dict_type: str = "main", description: str = " ", version: int = 18, date: int = int(time.time())):
        if version < 18:
            print(f"Warning: Version is {version}, dictionaries with version < 18"
                  f" may be ignored by some AOSP-based keyboard apps.")
        self.version: int = version
        if len(description) == 0:
            print("Warning: description can't be empty, replacing with " "")
            self.description = " "
        else:
            self.description: str = description
        self.type: str = dict_type
        if (len(locale) > 2 and "_" not in locale) or len(locale) > 5:
            print(f"Warning: Locale {locale} does not look like a valid locale. The dictionary will work,"
                  f" but the locale might not be recognized by the keyboard")
        self.locale: str = locale
        self.date = date

    def write(self):
        if self.locale == "de" or self.locale.split("_")[0] == "de":
            add = ",REQUIRES_GERMAN_UMLAUT_PROCESSING=1"
        else:
            add = ""
        return f"dictionary={self.type}:{self.locale.lower()},locale={self.locale},description={self.description}," \
               f"date={self.date},version={self.version}{add}"

    @classmethod
    def parse(cls, line: str) -> DictionaryHeader | None:
        split = line.strip().split(",")
        locale = get_attribute(split, "locale=")
        if locale is None:
            print("Error: no locale")
            return None
        dict_type = get_attribute(split, "dictionary=")
        if dict_type is None:
            print("Error: no dictionary type")
            return None
        actual_dict_type = dict_type.split(f":{locale.lower()}")[0]
        if actual_dict_type == dict_type:
            print(f"Error: lowercase locale {locale.lower()} not in {dict_type}")
            return None
        description = get_attribute(split, "description=")
        if description is None:
            print("Warning: no description, using empty string")
            description = ""
        version = get_attribute(split, "version=")
        if version is None or not version.isdigit():
            print(f"Warning: no valid version: {version}, using 18")
            version = 18
        else:
            version = int(version)
        date = get_attribute(split, "date=")
        if date is None or not date.isdigit():
            print("Warning: no valid date, using current date")
            date = int(time.time())
        else:
            date = int(date)
        return DictionaryHeader(locale, actual_dict_type, description, version, date)


class WordlistCombined:
    def __init__(self, header: DictionaryHeader = None, words: dict[str, WordAttributes] = None):
        if header is None:
            # show warning only when writing
            # print("the word list needs a header, otherwise it cannot be compiled")
            self.header = None
        else:
            self.header: DictionaryHeader = header
        if words is None:
            self.words: dict[str, WordAttributes] = dict()
        else:
            self.words = words

    # is the f for bigrams also limited to 255? then many bigrams might cause errors!
    # anyway, this will adjust bigram frequencies, so it's 1, 2, ... in the end
    def filter_bigrams(self, max_bigram_count: int = 3, max_f: int = -1):
        for word, attributes in self.words.items():
            bigram_count = 1  # number of bigrams that are kept
            for (next_word, f) in sorted(attributes.bigrams.items(), key=lambda item: item[1]):
                if bigram_count > max_bigram_count:
                    # we already have enough
                    del attributes.bigrams[next_word]
                    continue
                if next_word not in self.words:
                    # not in word list for some reason, we should to remove it
                    del attributes.bigrams[next_word]
                    continue
                if self.words[next_word].f > max_f:
                    # f too high
                    del attributes.bigrams[next_word]
                    continue
                attributes.bigrams[next_word] = bigram_count
                bigram_count += 1

    # replaces existing word
    def add_word(self, word: str, f: int, possibly_offensive: bool = False):
        attr = WordAttributes()
        attr.f = f
        attr.possibly_offensive = possibly_offensive
        self.words[word] = attr

    def add_shortcut(self, word: str, f: int, replace_word: bool, shortcut: str, shortcut_f: str, not_a_word: bool):
        attr = WordAttributes()
        attr.f = f
        if not replace_word and word in self.words:
            attr = self.words[word]
        attr.shortcuts[shortcut] = shortcut_f
        attr.not_a_word = not_a_word

    def add_bigram_entry(self, word: str, f: int, replace_word: bool, bigram: str, bigram_f: int):
        attr = WordAttributes()
        attr.f = f
        if not replace_word and word in self.words:
            attr = self.words[word]
        attr.bigrams[bigram] = bigram_f

    # note: be aware that merge_list re-uses attributes of the source list, and may also change them
    def merge_list(
            self,
            source: dict[str, WordAttributes],
            words=True,  # add new words to target
            f="keep",  # keep, overwrite or average target f
            possibly_offensive=True,  # add "possibly_offensive" attribute to target (only if true)
            not_a_word=True,  # add "not_a_word" attribute to target (only if true)
            shortcuts=True,  # add shortcuts to target (overwrite if same shortcut exists with different f)
            bigrams=True,  # add bigrams to target (overwrite if same bigram exists with different f)
            other=True  # add other (unknown) attributes to target (overwrite if same attribute exists with different value)
    ):
        target = self.words
        for x in source.items():
            (word, attributes) = x
            if word not in target:
                if words:
                    target[word] = attributes
                    if not bigrams:
                        attributes.bigrams = {}
                    if not not_a_word:
                        attributes.not_a_word = False
                    if not shortcuts:
                        attributes.shortcuts = {}
                    if not other:
                        attributes.unknown = {}
                    if not possibly_offensive:
                        attributes.possibly_offensive = False
                continue
            if f == "overwrite":
                target[word].f = attributes.f
            elif f == "average":
                target[word].f = int((attributes.f + target.f) / 2)
            # else keep
            if shortcuts:
                for (shortcut, f) in attributes.shortcuts.items():
                    target[word].shortcuts[shortcut] = f
            if bigrams:  # todo: this will likely result in several bigrams with the same f -> what do? should not be bad though
                for (bigram, f) in attributes.bigrams.items():
                    target[word].bigrams[bigram] = f
            if possibly_offensive and attributes.possibly_offensive:
                target[word].possibly_offensive = True
            if not_a_word and attributes.not_a_word:
                target[word].not_a_word = True
            if other:
                for (name, value) in attributes.unknown.items():
                    target[word].unknown[name] = value

    def write_to_file(self, filename: str):
        if filename.endswith(".gz"):
            with gzip.open(filename, 'wt') as f:
                write_it(self, f)
        else:
            with open(filename, 'w') as f:
                write_it(self, f)

    def compile(self, target_path: str, overwrite: bool = True):
        if self.header is None:
            raise ValueError("Error: can't compile without header")
        dicttool = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dicttool_aosp.jar")
        if not os.path.isfile(dicttool):
            raise FileNotFoundError("Error: dicttool_aosp.jar not found in parent directory")
        with tempfile.TemporaryDirectory() as tmpdir:
            if target_path.endswith(".dict"):
                (target_path, dictfilename) = os.path.split(target_path)
            else:
                dictfilename = f"{self.header.type}_{self.header.locale.lower()}.dict"
            dictfile = os.path.join(tmpdir, dictfilename)
            if not overwrite and os.path.isfile(dictfile):
                print(f"Error: file {dictfile} already exists, not writing")
                return
            filename = os.path.join(tmpdir, f"{self.header.locale.lower()}_{self.header.type}.combined")
            self.write_to_file(filename)
            execute = f"java -jar {dicttool} makedict -s {filename} -d {dictfile} > /dev/null"
            os.system(execute)
            if not os.path.exists(target_path):
                os.mkdir(target_path)
            shutil.move(dictfile, os.path.join(target_path, dictfilename))

    @classmethod
    def read_from_file(cls, filename: str) -> WordlistCombined:
        if filename.endswith(".gz"):
            with gzip.open(filename, 'rt') as f:
                return read_it(f)
        else:
            with open(filename, 'r') as f:
                return read_it(f)


def get_attribute(attributes: list[str], match: str) -> str | None:
    for entry in attributes:
        if entry.startswith(match):
            return entry.split(match)[1]
    return None


def read_it(file) -> WordlistCombined:
    word_list = dict()
    header = None
    current_word = None
    current_attributes = None
    for line in file:
        if line.startswith("dictionary"):
            header = DictionaryHeader.parse(line)
        if len(line) == 0:
            continue
        # extract word, frequency, possibly_offensive, not_a_word
        split = line.rstrip().split(",")
        i = 0
        # deal with e.g. "word=a, f=5": the space is allowed, but obstructs parsing
        for s in split:
            split[i] = s.lstrip()
            i += 1
        if split[0].startswith("word="):
            if current_word is not None:
                word_list[current_word] = current_attributes
            current_word = split[0].split("word=")[1]
            current_attributes = WordAttributes()
            current_attributes.f = int(get_attribute(split, "f="))
            split.remove(f"f={current_attributes.f}")
            possibly_offensive = get_attribute(split, "possibly_offensive=")
            if possibly_offensive == "true":
                current_attributes.possibly_offensive = True
                split.remove("possibly_offensive=true")
            not_a_word = get_attribute(split, "not_a_word=")
            if not_a_word == "true":
                current_attributes.not_a_word = True
                split.remove("not_a_word=true")
            if len(split) > 1:
                # the rest is "unknown"
                for attribute in split[1:]:
                    (name, value) = attribute.split("=")
                    current_attributes.unknown[name] = value
        elif split[0].startswith("shortcut="):
            shortcut = split[0].split("shortcut=")[1]
            f = get_attribute(split, "f=")  # can be "whitelist", thus not necessarily int
            current_attributes.shortcuts[shortcut] = f
        elif split[0].startswith("bigram="):
            bigram = split[0].split("bigram=")[1]
            f = int(get_attribute(split, "f="))
            current_attributes.bigrams[bigram] = f
    if current_word is not None:
        word_list[current_word] = current_attributes
    return WordlistCombined(header=header, words=word_list)


def write_it(wordlist: WordlistCombined, file):
    if wordlist.header is None:
        print("Warning: wordlist without header, resulting wordlist.combined will not compile")
    else:
        file.write(wordlist.header.write() + "\n")
    for x in sorted(wordlist.words.items(), key=lambda item: -item[1].f):
        (word, attributes) = x
        if attributes.not_a_word:
            not_a_word = ",not_a_word=true"
        else:
            not_a_word = ""
        if attributes.possibly_offensive:
            possibly_offensive = ",possibly_offensive=true"
        else:
            possibly_offensive = ""
        if len(attributes.unknown) > 0:
            unknown = ""
            for (name, value) in attributes.unknown.items():
                unknown += f",{name}={value}"
        else:
            unknown = ""
        file.write(f" word={word},f={attributes.f}{not_a_word}{possibly_offensive}{unknown}\n")
        for (bigram_word, bigram_f) in sorted(attributes.bigrams.items(), key=lambda item: item[1]):
            file.write(f"  bigram={bigram_word},f={bigram_f}\n")
        for (shortcut_word, shortcut_f) in attributes.shortcuts.items():
            file.write(f"  shortcut={shortcut_word},f={shortcut_f}\n")
