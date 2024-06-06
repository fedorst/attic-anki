from textual.app import App, ComposeResult
from textual.containers import HorizontalScroll, Container
from textual.screen import Screen
from textual.widgets import Placeholder, Input, Label, Pretty, Markdown, Header, Footer, Static
from textual.binding import Binding
from textual.validation import Function, ValidationResult, Validator
from textual import on
import pandas as pd
import beta_code
import re

df = pd.read_parquet("app_data.parquet")
def get_row(row_id: int):
    row = df.iloc[row_id]
    
    sentence_grc = row.sentence_obj_masked
    sentence_ee = row.ee_phrase
    target_grc = row.target_grc
    target_ee = row.ee_target
    return sentence_grc, sentence_ee, target_grc, target_ee

# beta_code.beta_code_to_greek(u'mh=nin a)/eide qea\\ *phlhi+a/dew *)axilh=os')
example_str = "mh=nin a)/eide qea\ *phlhi+a/dew *)axilh=os"
# returns index of next word/sentence combination 
def get_next_word() -> int:
    # 
    pass

def temp_fun():
    return "καὶ"

class BetaCodeCorrect(Validator): 
    def __init__(self, target: str):
        self.target = target
    def validate(self, value: str) -> ValidationResult:
        """Check an entered string, translated to betaCode, matches the target."""
        bc_value = beta_code.beta_code_to_greek(value)
        if self.matches_target(bc_value, self.target):
            return self.success()
        else:
            return self.failure(f"Entered input {bc_value}, which does not match target {self.target}")

    @staticmethod
    def matches_target(value: str, target: str) -> bool:
        return value == target



def sentence_grc_to_rich(sentence_grc: dict, current_input: str = ""):
    output_str = ""
    for w in sentence_grc:
        if w["masked"]:
            output_str += f"[bold yellow]{current_input if current_input != '' else '***'}[/bold yellow]"
        else:
            output_str += w["string"]
        output_str += " "
    return output_str

class TweetScreen(Screen):
    CSS_PATH = "dock_layout1_sidebar.tcss"
    def compose(self) -> ComposeResult:
        # word = temp_fun()

        sentence_grc, sentence_ee, target_grc, target_ee = get_row(0)
        self.sentence_grc = sentence_grc
        yield Static("Sidebar", id="sidebar")
        yield Header(id="Header", name="Attic-Anki")

        with Container(id="app-grid"):
            # yield Label("Trying out rich text: [bold red]alert![/bold red] Something happened")
            yield Label(sentence_grc_to_rich(sentence_grc), id="grc_sentence")
            # yield Pretty([], id="text")
            yield Input(
                placeholder="Sisesta tõlge:",
                type="text",
                validators=[
                    BetaCodeCorrect(target_grc)
                ]
            )
            yield Label('[yellow]' + re.sub("\[", "\\\[", target_ee) + '[/yellow]', id="target_ee")
            yield Label(re.sub("\[", "\\\[", sentence_ee), id="ee_sentence")
            yield Pretty("", id="error")

        yield Footer(id="Footer")
        yield HorizontalScroll()  

    @on(Input.Submitted)
    def show_invalid_reasons(self, event: Input.Submitted) -> None:
        # Updating the UI to show the reasons why validation failed
        if not event.validation_result.is_valid:  
            self.query_one("#error").update(event.validation_result.failure_descriptions[0])
        else:
            self.query_one("#error").update("Correct!")

    @on(Input.Changed)
    def update_entered_text_label(self, event: Input.Changed) -> None:
        try:
            greek_value = beta_code.beta_code_to_greek(event.value)
            self.query_one("#grc_sentence").update(sentence_grc_to_rich(self.sentence_grc, greek_value))
        except:
            pass
        #except:
        #    self.query_one("#text").update("Not valid beta code!")


class LayoutApp(App):
    BINDINGS = [
        Binding(key="q", action="quit", description="Quit the app"),
        Binding(
            key="question_mark",
            action="help",
            description="Show help screen",
            key_display="?",
        )
        # Binding(key="delete", action="delete", description="Delete the thing"),
        # Binding(key="j", action="down", description="Scroll down", show=False),
]

    def on_mount(self):
        self.title = "Attic-Anki"
    def on_ready(self) -> None:
        self.push_screen(TweetScreen())


if __name__ == "__main__":
    app = LayoutApp()
    app.run()