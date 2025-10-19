# The relations_italian.db database
A database of Italian nouns and related adjectives, verbs and adverbs.

## Why this database

This database contains 26565 nouns and 17142 forms derived from them (7161 verbs, 9124 adjectives and 857 adverbs). Most nouns, specifically 14180, have no derived forms.
The creation of this database is part of the activity for training a small model to recognize oximora. The idea to extend the dataset was to create good quality pairs noun-adjective like "speranza tragica" and use a database of derived terms to create more forms like "sperare tragicamente" or "tragedia speranzosa".
It seems that such a database does not exist in open source, at least for Italian. Multiwordnet Italian version only contains the database of words but not the relationships (apparently, FBK offers a complete, paid version, far too expensive for a small research project).
Not even large databases like Paisà contain relationships between terms. Moreover, neither spacy nor stanza offer methods for creating derived terms. In the end, the logical conclusion was to create such a database.

# Operations involved

The operation involved many steps:
1) extraction of nouns (POS = 'n') from multiwordnet, removing words with symbols, numbers, spaces or shorter than two characters.
2) creation of derivative adjectives, verbs, and adverbs by invoking an LLM (Mistral Large)
3) filtering LLM results using a customised version of the Paisà Italian Corpus with only words with minimum frequency 5 and minimum lenght 3.
4) creation of a database with table of nouns and table of derived forms, connected via a key.
5) second pass where LLM challenges the noun-derived connections and collects suspicious relationship into a list
6) human involvement to confirm or keep the suspicious terms and consequent finalization of the database.

Note that the filter removes invented or misspelled terms, but not morphological mistakes. For example, Mistral returned "gattino" as a derived adjective of "gatto". The word is in Paisà corpus, so it was accepted. More wrong derivatives can be catched in the last step.

## Database schema

The table definitions here below illustrate the contents and the relationship.

    CREATE TABLE IF NOT EXISTS words (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lemma TEXT NOT NULL UNIQUE,
        pos TEXT NOT NULL  # always 'n'
    );

    CREATE TABLE IF NOT EXISTS derived_forms (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      lemma_id INTEGER NOT NULL,
      form TEXT NOT NULL,
      pos TEXT NOT NULL,      # can be 'a', 'v' or 'r'
      relation_type TEXT NOT NULL,  # always 'morphological'. Used for future expansions.
      FOREIGN KEY (lemma_id) REFERENCES words(id)
    );

## The Paisà corpus
You can download the Paisà corpus from this page: https://clarin.eurac.edu/repository/xmlui/handle/20.500.12124/3
For this work, I downloaded the version lemma-WITHOUTnumberssymbols-frequencies-paisa.txt.gz and applied a further filtering, removing words with frequency below 5 or lenght below 3. The resulting file of circa 105000 lemmas is found in the repo as lemma-sorted-frequencies-paisa.txt.zip.

## Rebuild the files
If you want to rebuild the database from scratch:

1) extract lemma-sorted-frequencies-paisa.txt.zip in the same directory of relationBuilder.py
2) invoke:
       python relationBuilder.py
   There are some command line parameters that allow to change the script's behaviour, but the defaults will work fine.
3) to execute the second LLM step, I used batch files rather than API calls: they cost less and are significantly faster if you are lucky. There is a file called batchBuilder.py and another called dbRelationCleanup.py.
batchBuilder creates the batch in JSONL according to Mistral format, but it should be easy to adapt it to other vendors.
Once you get the file, you can invoke dbRelationCleanup passing the name of the input batch file and the output that you download when the batch is completed. The script creates a file called deletions.sql and gives you instruction on how to run it into sqlite3.
