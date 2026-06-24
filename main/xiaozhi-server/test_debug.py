from core.utils.tts import MarkdownCleaner
text = "Wiki: https://en.wikipedia.org/wiki/Python_(programming_language)"
print("INPUT:", text)
print("CLEANED:", MarkdownCleaner.clean_markdown(text))
