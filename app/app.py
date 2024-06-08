from textual.app import App, ComposeResult
from textual.containers import HorizontalScroll, Container, Center, Vertical
from textual.screen import Screen
from textual.widgets import Input, Label, Header, Footer, Static, DataTable
from textual.binding import Binding
from textual.validation import ValidationResult, Validator
from textual.reactive import reactive
from textual import on
import pandas as pd
import beta_code
import re
import os
import asyncio
import difflib
import sys

USER_DATA_PATH = "user_data.parquet"
APP_DATA_PATH = "app_data.parquet"

df_words = pd.read_parquet(APP_DATA_PATH)

def get_user_data():
    if not os.path.exists(USER_DATA_PATH):
        df_user_data = pd.DataFrame(columns=["memory_score", "order"], index=df_words.index)
        df_user_data["memory_score"] = df_words["memory_score"]
        df_user_data["order"] = df_user_data.index
        df_user_data.index.name = "ee_sent_idx"
        df_user_data.to_parquet(USER_DATA_PATH)
    return pd.read_parquet(USER_DATA_PATH)

df_user_data = get_user_data()

def get_debug_df():
    return df_user_data.merge(df_words[["target_grc", "ee_target"]], how="left", left_index=True, right_index=True).set_index(df_user_data.index)[["target_grc", "ee_target", "memory_score", "order"]].sort_values(by=["order"])

def get_user_data_table(topk=5):
    dt = DataTable(id="debug_table")
    shown_df = get_debug_df()
    col_keys = dt.add_columns(*shown_df.reset_index().columns.to_list())
    # cols = df_user_data.reset_index().columns.to_list()
    row_keys = dt.add_rows(shown_df.reset_index().head(topk).to_numpy())
    return dt

def memory_score_to_string(memory_score: int):
    elements = ["new", "seen", "answered", "remembered", "proficient"]
   #  elements = [f"{i+1}" for i in range(5)]
    for i in range(5):
        if memory_score == i:
            elements[i] = f"[bold]\[{elements[i] }][/bold]"
        elif memory_score < i:
            elements[i] = f"[red]{elements[i] }[/red]"
        else:
            elements[i] = f"[grey strike]{elements[i] }[/grey strike]"
    if memory_score > 4:
        elements[4] = f"[bold]\[{elements[i] }][/bold]"
    return "Word level: "+ " ".join(elements)

def get_row(row_id: int):
    row = df_words.loc[row_id]
    sentence_grc = row.sentence_obj_masked
    sentence_ee = row.ee_phrase
    words_ee = row.ee_words
    target_grc = row.target_grc
    target_ee = row.ee_target
    return sentence_grc, sentence_ee, target_grc, target_ee, words_ee

# returns index of next word/sentence combination 
def get_next_word_idx() -> int:
    reorder_user_data()
    return df_user_data.index[0]

def word_to_simple_identifier(word: dict):
    # process a word object to something that an LLM can ingest painleslly
    base_features = f"{word['string']} [lemma: {word['lemma']}] ({word['pos']})"
    additional_features = ""
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


class BetaCodeCorrect(Validator): 
    def __init__(self, target: str):
        self.target = target
    def validate(self, value: str) -> ValidationResult:
        # """Check an entered string, translated to betaCode, matches the target."""
        bc_value = beta_code.beta_code_to_greek(value)
        if self.matches_target(bc_value, self.target):
            return self.success()
        elif bc_value == "":
            return self.failure(f"Expected {self.target} ( {beta_code.greek_to_beta_code(self.target)} )")
        else:
            s = difflib.SequenceMatcher(None, bc_value, self.target)
            blocks = s.get_matching_blocks()
            diff_str = bc_value
            step = len("[green][/]")
            offset = 0
            for block in blocks[:-1]:
                diff_str = diff_str[:offset+block.a] + "[green]" + bc_value[block.a:block.a+block.size] + "[/]" + bc_value[block.a+block.size:]
                offset += step
            return self.failure(f"{diff_str} - expected {self.target} ( {beta_code.greek_to_beta_code(self.target)} )")

    @staticmethod
    def matches_target(value: str, target: str) -> bool:
        return value == target

def wrap_word_link(w: dict) -> str:
    word_str = w['string']
    word_idx = w['index_token']
    return f"[@click=screen.select_word('{word_idx}')]{word_str}[/]"

def wrap_word_target(current_input: str) -> str:
    return f"[bold yellow]{current_input if current_input != '' else '***'}[/bold yellow]"

def wrap_word_error(word: str) -> str:
    return f"[bold red]{word}[/bold red]"

def wrap_word(w: dict, current_input: str, error: bool=False):
    if w["pos"] == "punctuation":
        return w["string"]
    elif w["masked"]:
        if not error:
            return wrap_word_target(current_input)
        else:
            return wrap_word_error(w["string"])
    else:
        return wrap_word_link(w)

def sentence_grc_to_rich(sentence_grc: dict, current_input: str = "", error: bool = False):
    output_str = ""
    for i, w in enumerate(sentence_grc):
        output_str += wrap_word(w, current_input, error)
        if i < len(sentence_grc)-1 and sentence_grc[i+1]["pos"] != "punctuation": 
            output_str += " "
    return output_str

def escape_brackets(s: str):
    return re.sub("\[","\\\[",s)

def decrement_memory_score(idx: int) -> None:
    curr_score = df_user_data.loc[idx]["memory_score"]
    min_threshold = 1
    if curr_score >= 2:
        min_threshold = 2
    df_user_data.loc[idx, "memory_score"] = max(curr_score-2, min_threshold)

def increment_memory_score(idx: int) -> None:
    curr_score = df_user_data.loc[idx]["memory_score"]
    df_user_data.loc[idx, "memory_score"] = min(10, max(2, curr_score+1))

def reorder_user_data():
    df_user_data["order"] = df_user_data.index + 2**(df_user_data["memory_score"]+1)
    # df_user_data["order"] += 5000*(df_user_data["memory_score"] = 4)
    df_user_data.sort_values(by=["order"], ascending=[True], inplace=True)

class SentenceScreen(Screen):
    CSS_PATH = "dock_layout1_sidebar.tcss"
    # selected_idx = reactive(0, recompose=True)
    force_refresh = reactive(True, recompose=True)

    def __init__(self):
        super().__init__()
        self.already_decremented_memory_score = False        
        self.selected_idx = get_next_word_idx()
        if len(sys.argv) > 1 and sys.argv[1] == "debug":
            self.debug_mode = True
        else:
            self.debug_mode = False

    def compose(self) -> ComposeResult:
        df_user_data.to_parquet(USER_DATA_PATH) # save progress
        
        self.highlighted_word = None
        curr_idx = self.selected_idx
        sentence_grc, sentence_ee, target_grc, target_ee, words_ee = get_row(curr_idx)
        curr_memory_score = df_user_data.loc[curr_idx]["memory_score"]
        memory_score_str = memory_score_to_string(int(curr_memory_score))
        self.memory_score_label = Label(memory_score_str)
        self.sentence_grc = sentence_grc
        self.sentence_ee = sentence_ee
        self.words_ee = words_ee

        self.greek_sentence_label = Label(sentence_grc_to_rich(self.sentence_grc), id="grc_sentence")
        self.ee_sentence_label = Label(escape_brackets(sentence_ee), id="ee_sentence")
        self.ee_target_label = Label(f'[yellow]{escape_brackets(target_ee)}[/yellow]', id="target_ee")
        self.input = Input(
                    placeholder="Sisesta tõlge:",
                    type="text",
                    id="input",
                    validators=[
                        BetaCodeCorrect(target_grc)
                    ]
                )
        debug_container = Container(id="debug-container")
        debug_container.border_title="DEBUG INFO"
        
        yield Static("Sidebar", id="sidebar_left", classes="sidebar")
        yield Static("Sidebar", id="sidebar_right", classes="sidebar")

        yield Header(id="Header", name="Attic-Anki")

        with Container(id="app-grid"):
            with Vertical():
                yield self.memory_score_label
                yield self.greek_sentence_label
                yield self.ee_sentence_label
                yield self.input
                yield self.ee_target_label
                yield Label(" ", id="error") # for debugging rn
                yield Label(" ", id="grc_words")
                yield Label(" ", id="ee_words")

                if self.debug_mode:
                    with debug_container:
                        yield get_user_data_table(10)

        yield Footer(id="Footer")
        self.set_focus(self.input)

    def action_select_word(self, word_id: str) -> None:
        if self.highlighted_word == int(word_id):
            self.query_one("#grc_words").update(" ")
            self.query_one("#ee_words").update(" ")
            self.highlighted_word = None
            return
        self.highlighted_word = int(word_id)
        matching_word_grc = [w for w in self.sentence_grc if int(w["index_token"]) == self.highlighted_word]
        if len(matching_word_grc) < 1:
            return
        matching_word_grc = matching_word_grc[0]
        matching_words_ee = [w for w in self.words_ee if matching_word_grc["string"] in w["grc"].split(" ")]
        if len(matching_words_ee) < 1:
            return
        self.query_one("#grc_words").update(
            escape_brackets(word_to_simple_identifier(matching_word_grc))
        )
        self.query_one("#ee_words").update(
            "\n".join(f"{w['grc']} - {escape_brackets(w['ee'])}" for w in matching_words_ee)
        )

    async def show_next_word(self):
        self.input.disabled = True
        await asyncio.sleep(2)
        self.selected_idx = get_next_word_idx()
        self.force_refresh = not self.force_refresh
        self.set_focus(self.input)

    async def repeat_curr_word(self):
        self.greek_sentence_label.styles.background = "darkred"
        self.input.disabled = True
        await asyncio.sleep(2)
        self.input.disabled = False
        self.force_refresh = not self.force_refresh
        self.set_focus(self.input)
        # self.greek_sentence_label.styles.background = "#141414"

    @on(Input.Submitted)
    async def handle_submit(self, event: Input.Submitted) -> None:
        # Updating the UI to show the reasons why validation failed
        if not event.validation_result.is_valid:
            self.query_one("#error").update(event.validation_result.failure_descriptions[0])
            # flash red for 2sec
            self.greek_sentence_label.update(sentence_grc_to_rich(self.sentence_grc, error=True))
            if not self.already_decremented_memory_score:
                self.already_decremented_memory_score = True
                decrement_memory_score(self.selected_idx)
            self.run_worker(self.repeat_curr_word())
        else:
            if not self.already_decremented_memory_score:
                increment_memory_score(self.selected_idx)
                self.greek_sentence_label.styles.background = "darkgreen"
            else:
                self.greek_sentence_label.styles.background = "#443209"

            self.already_decremented_memory_score = False
            self.query_one("#error").update("Correct!")

            self.run_worker(self.show_next_word())
            
    @on(Input.Changed)
    def update_entered_text_label(self, event: Input.Changed) -> None:
        try:
            greek_value = beta_code.beta_code_to_greek(event.value)
            self.query_one("#grc_sentence").update(sentence_grc_to_rich(self.sentence_grc, greek_value))
        except:  # noqa: E722
            pass


class LayoutApp(App):
    BINDINGS = [
        Binding(key="q", action="quit", description="Quit the app"),
        Binding(
            key="question_mark",
            action="help",
            description="Show help screen",
            key_display="?",
        )]

    def on_mount(self):
        self.title = "Attic-Anki"

    def on_ready(self) -> None:
        self.push_screen(SentenceScreen())


if __name__ == "__main__":
    app = LayoutApp()
    app.run()