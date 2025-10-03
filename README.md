# free-deepl-translator

**Unofficial free DeepL translator client for Python** — this package lets you translate text using DeepL without requiring an API key by or an Auth token.

> ⚠️ **Unofficial**: this project reverse-engineers DeepL's web protocol. It may break if DeepL changes their site and may violate DeepL's Terms of Service. Use at your own risk.


## Installation

Install from PyPI:

```bash
pip install free-deepl-translator
```

## Quick example

```python
import free_deepl_translator as deepl

# Create the client
deepl_instance = deepl.DeeplTranslator()

# Create a session (returns True on success and False on failure)
d = deepl_instance.Session() # use *.SessionAsync() for async version

if d != True:
    print(f"Error")
    exit(1)
print("Session created")

# Simple translate to French
translated = deepl_instance.Translate("H-h-how are you ?\nPlease answer me", target_lang="fr") # use *.TranslateAsync() for async version
if translated["status"] == 0:
    print(f"Translated text: {translated['text']}")
#time.sleep(5)
# Translate from French to English
translated = deepl_instance.Translate("Je vais bien, merci", target_lang="en", source_lang="fr")
if translated["status"] == 0:
    print(f"Translated text: {translated['text']}")

# Advanced call: specify model, glossary and formality
translated = deepl_instance.Translate(
    "Can you please send me the report?",
    target_lang="ja",
    source_lang="en",
    target_model="next-gen",
    glossary=[{"source": "report", "target": "動画"}],
    formality="formal",
)
if translated["status"] == 0:
    print(f"Translated text: {translated['text']}")

# Close the Session
deepl_instance.Close() # use *.CloseAsync() for async version
```

To use it with Async you can use `SessionAsync()`, `TranslateAsync()` and `CloseAsync()`.

## Return format

`Translate()` and `TranslateAsync()` return a dictionary like:

```python
{
  "status": 0,    # 0 = success, non-zero = error
  "text": "...", # translated text when successful
  "msg": "...", # error message (when status != 0)
}
```

## Features

- Translate text without an API key (no auth).
- Supports explicit `source_lang`.
- `target_model` selection (e.g. `next-gen` or `classic`).
- Glossary entries (list of `{source, target}` mappings).
- `formality | tone` control.
