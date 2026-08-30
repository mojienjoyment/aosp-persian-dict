#!/bin/python
import math
import os
import sys
import time
import regex
from spylls.hunspell import Dictionary
from wordlist_combined import WordlistCombined, DictionaryHeader, WordAttributes

# todo:
#  maybe ignore compound words like 'long-term'? will android actually suggest them?


# from https://github.com/zverok/spylls/blob/master/examples/unmunch.py
def unmunch_word(word, aff):
    result = set()

    if aff.FORBIDDENWORD and aff.FORBIDDENWORD in word.flags:
        return result

    if not (aff.NEEDAFFIX and aff.NEEDAFFIX in word.flags):
        result.add(word.stem)

    suffixes = [
        suffix
        for flag in word.flags
        for suffix in aff.SFX.get(flag, [])
        if suffix.cond_regexp.search(word.stem)
    ]
    prefixes = [
        prefix
        for flag in word.flags
        for prefix in aff.PFX.get(flag, [])
        if prefix.cond_regexp.search(word.stem)
    ]

    for suffix in suffixes:
        root = word.stem[0:-len(suffix.strip)] if suffix.strip else word.stem
        suffixed = root + suffix.add
        if not (aff.NEEDAFFIX and aff.NEEDAFFIX in suffix.flags):
            result.add(suffixed)

        secondary_suffixes = [
            suffix2
            for flag in suffix.flags
            for suffix2 in aff.SFX.get(flag, [])
            if suffix2.cond_regexp.search(suffixed)
        ]
        for suffix2 in secondary_suffixes:
            root = suffixed[0:-len(suffix2.strip)] if suffix2.strip else suffixed
            result.add(root + suffix2.add)

    for prefix in prefixes:
        root = word.stem[len(prefix.strip):]
        prefixed = prefix.add + root
        if not (aff.NEEDAFFIX and aff.NEEDAFFIX in prefix.flags):
            result.add(prefixed)

        if prefix.crossproduct:
            additional_suffixes = [
                suffix
                for flag in prefix.flags
                for suffix in aff.SFX.get(flag, [])
                if suffix.crossproduct and not suffix in suffixes and suffix.cond_regexp.search(prefixed)
            ]
            for suffix in suffixes + additional_suffixes:
                root = prefixed[0:-len(suffix.strip)] if suffix.strip else prefixed
                suffixed = root + suffix.add
                result.add(suffixed)

                secondary_suffixes = [
                    suffix2
                    for flag in suffix.flags
                    for suffix2 in aff.SFX.get(flag, [])
                    if suffix2.crossproduct and suffix2.cond_regexp.search(suffixed)
                ]
                for suffix2 in secondary_suffixes:
                    root = suffixed[0:-len(suffix2.strip)] if suffix2.strip else suffixed
                    result.add(root + suffix2.add)

    return result


def unmunch_dictionary(dictionary: Dictionary) -> set[str]:
    result = set()
    for word in dictionary.dic.words:
        result.update(unmunch_word(word, dictionary.aff))
    return result


class Wordlist:
    def __init__(self,
                 # spylls dictionary, or locale or path
                 dictionary: Dictionary | str | None = None,
                 # words that should be ignored, typically (international) names we don't want in a language word list,
                 #  can also be common issues, e.g. "i" is recommended for English as usually "I" is meant, but "i" is
                 #  correct too according to spylls/hunspell
                 ignore_words: set[str] | None = None
                 ):
        if isinstance(dictionary, str):
            if "/" in dictionary:
                self.dictionary = Dictionary.from_files(dictionary)
            else:
                self.dictionary = find_dict(dictionary)
        else:
            self.dictionary = dictionary
        self.dict_words: set[str] = set()
        if ignore_words is None:
            self.ignore_words = set()
        else:
            self.ignore_words = ignore_words
        # number of identified words
        self.count = 0

        # number of words used for frequency
        self.count_valid = 0

        # words to ignore, as they should be in some additional dictionary (mostly names)
        # these are not counted as valid or invalid, and not used for next-word data
        self.ignore_word_count = 0

        # words detected as invalid, these are mostly names and capitalized words (possibly also part of names)
        self.invalid_words: set[str] = set()
        self.not_words: set[str] = set()

        # unclear words with more than one match group in above regex
        # check and decide in the end what to do
        self.weird_things: set[str] = set()

        # for each word, contains a dict with:
        #  count: int (always)
        #  next: dict[str, int] (not always)
        #   how often the word is followed by some others (next_word, count)
        #  nosuggest: bool (usually only if True, as determined by hunspell dict)
        self.word_infos: dict = {}

    # regex for that kicks out things that are definitely not words
    # next word will be treated as ngram start
    # allow letters, and ' and - (but not at start/end)
    possible_word_regex = r"(?!['-])([\p{L}\d'-]+)(?<!['-])"  # \p{L} requires regex, not re

    # adds words that are valid according to dictionary (hunspell "unmunch")
    # this is useful for adding many word form that are valid but not used frequently
    def add_words_from_dictionary(self, dict_word_cache_file: str | None = None):
        unmunched: set[str] = set()
        if dict_word_cache_file is not None and os.path.isfile(dict_word_cache_file):
            try:
                with open(dict_word_cache_file) as f:
                    for w in f:
                        unmunched.add(w.strip())
            except:
                print(f"error reading {dict_word_cache_file}")
        if len(unmunched) == 0:
            s = unmunch_dictionary(self.dictionary)
            # unmunch may create word fragments
            #  remove words that are not valid according to dictionary
            #  or that start or end with -
            #  and ignore words that contains numbers, such as 65th
            # unfortunately this can be really slow depending on language, seen from a few seconds up to hours (cs)
            #  but with the cache it's ok
            for word in s:
                if not word.startswith("-") and not word.endswith("-") and not regex.search(r"\d", word):
                    # don't care about whether word is already in word_infos, we only want hunspell words
                    if self.dictionary.lookuper(word, capitalization=False, allow_nosuggest=False):
                        unmunched.add(word)
                    elif self.dictionary.lookuper(word, capitalization=False, allow_nosuggest=True):
                        unmunched.add(f"nosuggest:{word}")
            if dict_word_cache_file is not None:
                try:
                    with open(dict_word_cache_file, 'w') as f:
                        f.writelines([str(i) + '\n' for i in unmunched])
                except:
                    print(f"could not write to {dict_word_cache_file}")

        count = 0
        for word in unmunched:
            if word not in self.ignore_words and word not in self.word_infos:
                if word.startswith("nosuggest:"):
                    word = word[10:]
                    self.add_word(word, True)
                else:
                    self.add_word(word)
                count += 1
        print(count, "words added using add_unmunched_dictionary")

    # tries adding a line, which is a sentence or sentence fragment
    # if next-word information is not wanted, use add_word instead
    # currently ngram ends after every non-word character
    #  like 2, ", ,, ., -
    #  any cases where this shouldn't happen?
    def add_line(self, line: str,
                 # True: all words will be added, except if they start with an uppercase letter and
                 #  previous_word is None (careful, this can easily add spelling mistakes)
                 # False: if no dictionary, no words will be added
                 #  if dictionary, words will still be added if they are found in a case-sensitive lookup
                 add_unknown_words: bool = False) -> None:

        # first check whether more than half of the words start with uppercase
        # this is a strong hint that the line is title case, which is not wanted
        split_line = line.split()
        uppercount = 0
        for word in split_line:
            if word[0].isupper():
                uppercount += 1
                if uppercount > len(split_line) / 2:
                    return

        previous_word: str | None = None
        for word in split_line:
            if word in self.word_infos:
                # shortcut: we already know the word, avoid doing the regex check and dict lookup if possible
                # only increase count and add next word info
                self.add_word(word)
                if previous_word is not None:
                    previous_info = self.word_infos[previous_word]
                    previous_next = previous_info.get("next", {})
                    previous_next[word] = previous_next.get(word, 0) + 1
                    previous_info["next"] = previous_next
                previous_word = word
                continue
            if len(word) >= 48:
                # android dicttool ignores those, so let's skip them already here
                previous_word = None
                continue
            if word.isspace():
                # don't treat spaces as countable word (assuming a line does not contain a line break)
                continue
            if word.isnumeric():
                # don't put numbers info not_words
                previous_word = None
                continue
            if regex.search(r"\d", word):
                # words with numbers are not valid for the dictionary (e.g. 65th)
                self.invalid_words.add(word)
                previous_word = None
                continue
            if "--" in word:
                # words with "--" are seen as valid by spylls/hunspell, but we don't want them
                self.invalid_words.add(word)
                previous_word = None
                continue
            if not regex.search(r"\p{L}", word):
                # no letters, no word (but ngram ends here)
                self.not_words.add(word)
                previous_word = None
                continue
            # hunspell dict has ', not ’, but we want to understand both
            word = word.replace('’', '\'')
            # must find something, because r"\p{L}" non-matches are already removed
            re_find = regex.findall(self.possible_word_regex, word)
            self.count += 1
            if len(re_find) > 1:
                # just write down and end sentence for now
                self.weird_things.add(word)
                previous_word = None
            # treat re_find[0] as the actual word, but need to investigate weird_things to maybe improve possible_word_regex
            full_word = word
            word = re_find[0]
            # if the match is not at the start, treat as ngram start
            if not full_word.startswith(word):
                previous_word = None

            if word in self.ignore_words:
                self.ignore_word_count += 1
                previous_word = None
                continue

            if word in self.invalid_words:
                previous_word = None
                continue

            if word not in self.word_infos:
                if add_unknown_words:
                    if previous_word is None and word[0].isupper():
                        continue
                else:
                    try:
                        valid, word = self.dict_check(word, previous_word is None)
                    except IndexError:
                        # happens for "İsmail" when using German dictionary, also for other words starting with "İ"
                        previous_word = None
                        continue
                    if not valid:
                        if previous_word is not None:  # otherwise uppercase at sentence start would end up here
                            self.invalid_words.add(word)
                        previous_word = None
                        continue

            self.count_valid += 1
            self.add_word(word, add_to_count=False)

            if previous_word is not None:
                previous_info = self.word_infos[previous_word]
                previous_next = previous_info.get("next", {})
                previous_next[word] = previous_next.get(word, 0) + 1
                previous_info["next"] = previous_next
            # set new previous word, or None if ngram end is suspected (this could be optimized, but no priority)
            if full_word.endswith(word):
                previous_word = word
            else:
                previous_word = None

    # returns whether word is valid according to the dictionary, and, for the case it was capitalized, the valid form
    def dict_check(self, word: str, try_decapitalize: bool) -> tuple[bool, str]:
        if try_decapitalize and word[0].isupper():
            decapitalized = word[0].lower() + word[1:]
            if decapitalized in self.word_infos:
                return True, decapitalized
            # todo: lookup can be slow, optimize order with capitalization and nosuggest
            if not self.dictionary.lookuper(word, capitalization=True, allow_nosuggest=True):
                return False, word
            # word may be valid, check capitalization and nosuggest
            if self.dictionary.lookuper(word, capitalization=False, allow_nosuggest=False):
                return True, word
            if self.dictionary.lookuper(decapitalized, capitalization=False, allow_nosuggest=False):
                return True, decapitalized
            if self.dictionary.lookuper(word, capitalization=False, allow_nosuggest=True):
                self.word_infos[word] = {"nosuggest": True}
                return True, word
            if self.dictionary.lookuper(decapitalized, capitalization=False, allow_nosuggest=True):
                self.word_infos[decapitalized] = {"nosuggest": True}
                return True, decapitalized
            return False, word
        # we always want correct capitalization
        # maybe invert order for better performance, similar to above
        if not self.dictionary.lookuper(word, capitalization=False, allow_nosuggest=True):
            return False, word
        if self.dictionary.lookuper(word, capitalization=False, allow_nosuggest=False):
            return True, word
        self.word_infos[word] = {"nosuggest": True}
        return True, word

    def add_word(self, word: str, nosuggest: bool = False, add_to_count: bool = True):
        word_info = self.word_infos.get(word, {})
        word_info["count"] = word_info.get("count", 0) + 1
        if nosuggest:
            word_info["nosuggest"] = True
        self.word_infos[word] = word_info
        if add_to_count:
            self.count += 1
            self.count_valid += 1

    def add_sentence_file(self, filename: str, add_unknown_words: bool = False):
        with open(filename) as f:
            for line in f:
                self.add_line(line, add_unknown_words)

    def add_word_file(self, filename: str):
        with open(filename) as f:
            for line in f:
                for word in line.split():
                    re_find = regex.findall(self.possible_word_regex, word)
                    if len(re_find) == 0:
                        continue
                    word = re_find[0]
                    self.add_word(word)

    # when adding bigrams, the bigram f will be 1 for the most frequent, 2 for the next, then 3, ...
    # this creates warnings when compiling the dict, but it's the same for the original en_US AOSP wordlist
    def create_wordlist_combined(self, add_nosuggest=True, add_bigrams=True,
                                 header: DictionaryHeader = None) -> WordlistCombined:
        min_frequency = 15  # values below 15 are special values, better don't use them for normal words'
        max_frequency = 254
        min_next_word_count_for_bigram = 2  # just a single occurrence is not enough

        (min_count, max_count) = min_max_counts(self.word_infos)
        if max_count == 0:
            print("Warning: created WordlistCombined is empty")
            return WordlistCombined(header=header)
        min_f = math.log(min_count)
        f_diff = max(math.log(max_count) - min_f, 1)
        wordlist = WordlistCombined(header=header)

        for word, infos in self.word_infos.items():
            if regex.search(r"\d", word):
                continue  # this is valid for Wordlist, but not usable in Android, as digits area not seen as parts of a word
            f = math.log(infos["count"])
            attributes = WordAttributes()
            attributes.f = int((f - min_f) * (max_frequency - min_frequency) / f_diff + min_frequency)
            if add_nosuggest and infos.get("nosuggest", False):
                attributes.possibly_offensive = True
            if add_bigrams and "next" in infos:
                bigram_count = 1
                for next_word, next_count in sorted(infos["next"].items(), key=lambda item: -item[1]):
                    if next_count < min_next_word_count_for_bigram:
                        break
                    attributes.bigrams[next_word] = bigram_count
                    bigram_count += 1
            wordlist.words[word] = attributes

        return wordlist


def min_max_counts(word_infos: dict) -> (int, int):
    max_count = 0
    min_count = 2147483647  # simply start with a very large number (int32 max)
    for _, infos in word_infos.items():
        count = infos["count"]
        if count < min_count:
            min_count = count
        if count > max_count:
            max_count = count
    return min_count, max_count


# try guessing (p)hunspell locale for given language
def hun_loc(loc: str) -> str:
    if len(loc) == 2:
        if loc == "cs":
            return "cs_CZ"
        if loc == "en":
            print("using en_US for locale en")
            return "en_US"
        elif loc == "bn":
            return "bn_BD"
        elif loc == "uk":
            return "uk_UA"
        elif loc == "ar":
            return "ar"
        elif loc == "ko":
            return "ko_KR"
        elif loc == "vi":
            return "vi_VN"
        elif loc == "af":
            return "af_ZA"
        elif loc == "kk":
            return "kk_KZ"
        elif loc == "sl":
            return "sl_SI"
        elif loc == "et":
            return "et_EE"
        elif loc == "da":
            return "da_DK"
        elif loc == "sv":
            return "sv_SE"
        elif loc == "gl":
            return "gl_ES"
        elif loc == "ne":
            return "ne_NP"
        else:
            return loc + "_" + loc.upper()
    else:
        return loc


def find_dict(loc: str) -> Dictionary:
    try:
        d = Dictionary.from_system(loc)
        return d
    except LookupError:
        pass
    h_loc = hun_loc(loc)
    try:
        d = Dictionary.from_system(h_loc)
        return d
    except LookupError:
        pass
    try:
        import phunspell
        dict_path = f"{phunspell.__path__[0]}/data/dictionary/"
    except:
        raise FileNotFoundError("dictionary not found")
    language = loc.split("_")[0]
    if os.path.isdir(f"{dict_path}/{language}"):
        try:
            return Dictionary.from_files(f"{dict_path}/{language}/{h_loc}")
        except FileNotFoundError:
            return Dictionary.from_files(f"{dict_path}/{language}/{loc}")
    elif os.path.isdir(f"{dict_path}/{h_loc}"):
        return Dictionary.from_files(f"{dict_path}/{h_loc}/{h_loc}")
    raise FileNotFoundError("dictionary not found")
