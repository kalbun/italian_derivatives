# italian_derivatives
A database of Italian nouns and related adjectives, verbs and adverbs.

This database was created because I did not find a dataset where Italian nouns are directly linked to morphologically derived terms (like "felice" from "felicità").
The Italian version of MultiWordNet has quite a considerable number of terms, but unlike English it lacks the derivatives database.
To build this database I executed the following operations:

1) extraction of nouns (POS = 'n') from MWN, removing words with symbols, numbers, spaces or shorter than two characters.
2) creation of derivative adjectives, verbs, and adverbs by invoking an LLM (Mistral Large)
3) filtering LLM results using a customised version of the Paisà Italian Corpus with only words with minimum frequency 5 and minimum lenght 3.

Note that the filter removes invented or misspelled terms, but not morphological mistakes. For example, Mistral returned "gattino" as a derived adjective of "gatto". The word is in Paisà corpus, so it was accepted.

The database contains 26402 nouns and only 18016 related terms because only a small percentage of nouns leads to derived terms.
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

# The Paisà corpus
You can download the Paisà corpus from this page: https://clarin.eurac.edu/repository/xmlui/handle/20.500.12124/3
For this work, I downloaded the version lemma-WITHOUTnumberssymbols-frequencies-paisa.txt.gz and applied a further filtering, removing words with frequency below 5 or lenght below 3. The resulting file of circa 105000 lemmas is found in the repo as lemma-sorted-frequencies-paisa.txt.zip.

# Rebuild the files
If you want to rebuild the database from scratch:

1) extract lemma-sorted-frequencies-paisa.txt.zip in the same directory of relationBuilder.py
2) invoke:
       python relationBuilder.py
   There are some command line parameters that allow to change the script's behaviour, but the defaults will work fine.
   
