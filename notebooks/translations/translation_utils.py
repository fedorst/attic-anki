from enum import Enum
import anthropic
import pandas as pd
import json

example_input_dict = {
    "märksõna": "πίνει [lemma: πίνω] (verb) | finite; present.active.indicative.third.singular",
    "lause": "καὶ αὐτὸς ἐκ τῆς τοῦ ἑτέρου πίνει.",
    "allikas": "histories by herodotus",
    "sõnad": [
        "καὶ [lemma: καί] (coordinating_conjunction)",
        "αὐτὸς [lemma: αὐτός] (adjective) | singular.masculine.nominative",
        "ἐκ [lemma: ἐκ] (adposition)",
        "τῆς [lemma: ὁ] (determiner) | singular.feminine.genitive",
        "τοῦ [lemma: ὁ] (determiner) | singular.masculine.genitive",
        "ἑτέρου [lemma: ἕτερος] (adjective) | singular.masculine.genitive",
        "πίνει [lemma: πίνω] (verb) | finite; present.active.indicative.third.singular"
    ]
}
example_output_dict = {
    "lause": "Ja [tema] ise teise [karikast] joob.",
    "märksõna": "joob [lemma: jooma]",
    "tõlked": [
        {"grc": "καὶ", "ee": "ja"},
        {"grc": "αὐτὸς", "ee": "ise"},
        {"grc": "ἐκ τῆς τοῦ ἑτέρου", "ee": "teisest"},
        {"grc": "πίνει", "ee": "joob"},
    ]
}
example_input = json.dumps(example_input_dict, ensure_ascii=False)
example_output = json.dumps(example_output_dict, ensure_ascii=False)

class PromptType(Enum):
    ANTHROPIC = 1
    GEMINI = 2

prompt_instruction_text = """Tõlgi järgnev vana-kreekakeelne lause ja märksõna eesti keelde. 
Ole grammatiliselt originaalile nii lähedane, kui võimalik. Ära tee eesti keeles grammatikavigu. Samuti tõlgi eraldi sõnad. 

Väljund peab olema korrektne JSON objekt, kus peavad olema väljad: 
"lause" - eestikeelne tõlge
"märksõna" - märksõna eestikeelne tõlge koos lemmaga. Lemma PEAB olema eestikeelne. (nt: loetav [lemma: lugema])
"tõlked" - list iga sõna individuaalse tõlkega. Listi elemendid on objektid võtmetega "grc" - algne sõne ja "ee" - tõlge. Nendele tõlgetele EI PEA lisama lemmat. Kui kontekst seda nõuab, võib ühe sõna asemel tõlkida terve sõnapaari või kombinatsiooni.
Kui märksõna liik on (determiner), lisa tõlkesse ("märksõna" välja) LEMMA ASEMEL RUUTSULGUDE SISSE selle sugu ja kääne, kui võimalik, formaadis: "nende (m. gen. pl.) [lemma: nemad]".

"lause" väljas võib semantilistele sõna või sõnapaari tõlkele järgneda otsetõlge (sulgude sees), kuid mitte "tõlked" väljas. 
Otsetõlke korral EI TOHI MITTE KUNAGI sulgudesse lisada midagi üleliigset, nagu märget "sõna-sõnalt" või vana-kreekakeelset algvarianti.
Kui lause tõlge sisaldab sõna, mida algses vana-kreekakeelses lauses ei esinenud, kasuta "lause" väljas selle sõna ümber [ruutsulge], kuid ürita selliseid olukordi vältida.
Tõlkides "märksõna", tõlgi lisaks märksõnale ka lemma. 

Lähtu näidissisendist ja näidisväljundist."""

def get_system_msg(promptType: PromptType = PromptType.ANTHROPIC):       
    sys_prompt = ""
    match promptType:
        case PromptType.ANTHROPIC:    
            sys_prompt = f"""{prompt_instruction_text}
<Näidissisend> 
{example_input}

<Näidisväljund>
{example_output}
"""
        case PromptType.GEMINI:
            sys_prompt = [
                f"""instruction: {prompt_instruction_text}""",
                f"""input: {example_input}""",
                f"""output: {example_output}"""
            ]
    return sys_prompt

def get_user_prompt(prompt_input, promptType: PromptType = PromptType.ANTHROPIC):
    user_prompt = ""
    match promptType:
        case PromptType.ANTHROPIC:
            user_prompt = f"""<Sisend>
{prompt_input}

<Väljund>
"""
        case PromptType.GEMINI:
            user_prompt = [
                f"""input: {prompt_input}""",
                "output: "
            ]
    return user_prompt


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
    sentence_wl: list = row["sentence_obj"]
    return any(w["string"] == text and w["lemma"] == lemma and w["pos"] == pos for w in sentence_wl)
def find_matching_sentences(df_sents: pd.DataFrame, word_row: dict, sortby=["len_words", "len_chars"]):
    return df_sents[df_sents.apply(lambda row: wordlist_matches(row, word_row['text'], word_row['lemma'], word_row['pos']), axis=1)]\
        .sort_values(by=sortby)
def filter_matching_sentences(matching_sents: pd.DataFrame, min_words=3, max_words=20, topk=3):
    return matching_sents[
        (matching_sents["len_words"] >= min_words) & \
        (matching_sents["len_words"] < max_words) & \
        (matching_sents["ee_sent_idx"].isnull())
    ].head(topk)

LINEBR = '\n' # backslashes unsupported in f-strings curly brackets

def word_to_simple_identifier(word: dict):
    # process a word object to something that an LLM can ingest painleslly
    base_features = f"{word['string']} [lemma: {word['lemma']}] ({word['pos']})"
    additional_features = f""
    feats = word["features"]
    match word['pos']:
        case 'verb' | 'auxiliary':
            vf = feats["VerbForm"]
            match vf:
                case "infinitive":
                    additional_features = f"{vf}; {feats['Tense']}.{feats['Voice']}"
                case "participle":
                    additional_features = f"{vf}; {feats['Tense']}.{feats['Voice']}.{feats['Number']}.{feats['Case']}"
                case "gerundive":
                    additional_features = f"{vf}; {feats['Number']}"
                case _:
                    additional_features = f"{vf}; {feats['Tense']}.{feats['Voice']}.{feats['Mood']}.{feats['Person']}.{feats['Number']}"
        
        case 'punctuation' | 'subordinating_conjunction' | 'coordinating_conjunction' | 'adposition' | 'adverb' | 'interjection' | 'particle':
                additional_features = ""
        case _:
            # works for pronoun noun proper_noun adjective determiner
            # noun pl masc nom
            additional_features = f"{feats['Number']}.{feats['Gender']}.{feats['Case']}"
    return f"{base_features}{(' | ' + additional_features) if additional_features != '' else ''}"

def sentence_to_prompt_input_dict(row: dict, targetWord: str):
    return {
    "märksõna": targetWord, # TODO "πίνει [lemma: πίνω] (verb) | finite; present.active.indicative.third.singular",
    "lause": row['sentence_txt'],
    "allikas": f"{row['metadata'].get('title', row['metadata'].get('work', 'unknown'))} by {row['metadata']['author']}",
    "sõnad": [word_to_simple_identifier(w) for w in row['sentence_obj'] if w['pos'] != 'punctuation']
    }
