from enum import Enum
import anthropic
import pandas as pd

example_input = f"""--- Target word:
πίνει [lemma: πίνω] (verb) | finite; present.active.indicative.third.singular
--- Phrase:
καὶ αὐτὸς ἐκ τῆς τοῦ ἑτέρου πίνει.
--- Source:
histories by herodotus
--- Words:
καὶ [lemma: καί] (coordinating_conjunction)
αὐτὸς [lemma: αὐτός] (adjective) | singular.masculine.nominative
ἐκ [lemma: ἐκ] (adposition)
τῆς [lemma: ὁ] (determiner) | singular.feminine.genitive
τοῦ [lemma: ὁ] (determiner) | singular.masculine.genitive
ἑτέρου [lemma: ἕτερος] (adjective) | singular.masculine.genitive
πίνει [lemma: πίνω] (verb) | finite; present.active.indicative.third.singular"""

example_output = f"""--- Lause: 
Ja [tema] ise teise [karikast] joob.
--- Märksõna:
joob [lemma: jooma]
--- Sõnad:
καὶ - ja
αὐτὸς - ise
ἐκ τῆς τοῦ ἑτέρου - teisest
πίνει - joob"""

def get_system_msg():
    sys_prompt = f"""Tõlgi järgnev vana-kreekakeelne lause ja märksõna eesti keelde. 
Ole grammatiliselt originaalile nii lähedane, kui võimalik. Ära tee eesti keeles grammatikavigu. Samuti tõlgi eraldi sõnad. 
Eraldi sõnad peavad lisaks semantilisele tõlkele sisaldama otsetõlget sulgude sees.
Kui lause tõlge sisaldab sõna, mida algses lauses ei esinenud, kasuta selle sõna ümber [ruutsulge], kuid ürita selliseid olukordi vältida.
Tõlkides märksõna, tõlgi lisaks märksõnale ka lemma.

Märksõna on tähistatud "Target word", lause on tähistatud "Phrase".

Näidissisend: 
{example_input}

Näidisväljund:
{example_output}
"""
    return sys_prompt

def get_user_prompt(prompt_input):
    full_prompt = f"""
Sisend:
{prompt_input}

Väljund:
"""
    return full_prompt


class ParseMode(Enum):
    PHRASE = "ee_phrase"
    TARGET = "ee_target"
    WORDS = "ee_words"

def getParseMode(split: str):
    if "Lause:" in split:
        return ParseMode.PHRASE
    elif "Märksõna:" in split:
        return ParseMode.TARGET
    elif "Sõnad:" in split:
        return ParseMode.WORDS
    else:
        return ParseMode.PHRASE

def parse_output(msg_output: anthropic.types.message.Message):
    text = msg_output.content[0].text
    splits = [split for split in text.split("\n") if len(split) > 0]
    parseMode = ParseMode(ParseMode.PHRASE)
    outputObj = {}
    # print(splits)
    for split in splits:
        if "---" in split:
            parseMode = getParseMode(split)
        else:
            if parseMode.value not in outputObj:
                outputObj[parseMode.value] = [split] if parseMode == ParseMode.WORDS else split
            else:
                outputObj[parseMode.value].append(split)

    return outputObj

def wordlist_matches(row: dict, text: str, lemma: str, pos: str):
    wl = row["sentence_obj"]
    return any(w["string"] == text and w["lemma"] == lemma and w["pos"] == pos for w in wl)
def find_matching_sentences(df_sents: pd.DataFrame, word_row: dict, sortby=["len_words", "len_chars"]):
    return df_sents[df_sents.apply(lambda row: wordlist_matches(row, word_row['text'], word_row['lemma'], word_row['pos']), axis=1)]\
        .sort_values(by=sortby)
def filter_matching_sentences(matching_sents: pd.DataFrame, words_lower_bound=3, topk=3):
    return matching_sents[matching_sents["len_words"] > words_lower_bound].head(topk)