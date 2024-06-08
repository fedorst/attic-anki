# Here's the plan:

Overall idea: a command-line app that serves you greek phrases with the word masked out. You are provided with the estonian translation of the entire phrase as well as the word. As you enter the word, if it matches the one masked out the "memory score" of the word increases by one. Possible values:

0 - never seen
1 - seen at least once
2 - responded at least once correctly
3 - responded last time correctly
4 - responded last 3 times in a row correctly

After reaching level 4, the word is considered to be "learned"

The higher the value, the less frequently the word is shown - except for 0, which is also shown rarely.

For words you've seen, it's not possible to drop below 1.
For words you've responded correctly to, it's not possible to drop below 2.
After responding to a word incorrectly, you are shown the correct writing. You cannot proceed until you respond correctly (but it will not be counted as a correct response in this case)

Requirements: a small refactor of the grc_sentences, ee_sentences and grc_words datasets.
We need:

1. word/sentence recommendation engine (e.g. based on combination of frequency AND memory score)
2. When a word/sentence is being recommended, the following is required:
    1. A target word (greek) - this is what we are matching user input against (but take into account the beta code input)
    2. A corresponding greek sentence, with the target word masked out
    3. Greek word hints (optional?)
    4. Estonian translation of the phrase and the target word  


I think I'll do this all in python to save on time.

https://textual.textualize.io/widgets/input/#__tabbed_2_1
maybe on https://textual.textualize.io/widgets/input/#textual.widgets._input.Input.Changed do beta code stuff
