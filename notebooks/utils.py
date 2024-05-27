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

def sentence_to_string_repr(row: dict):
    return f"""--- Phrase:
{row['sentence_txt']}
--- Source:
{row['metadata'].get('title', row['metadata'].get('work', 'unknown'))} by {row['metadata']['author']}
--- Words:
{LINEBR.join(word_to_simple_identifier(w) for w in row['sentence_obj'] if w['pos'] != 'punctuation')}"""
