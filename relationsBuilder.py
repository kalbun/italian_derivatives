"""
This script builds an sqlite database of morphological derived forms
for Italian nouns using multiwordnet + a Mistral-based LLM assistant.

Changes made:
- code reorganised into small functions
- added a CLI `main()` that accepts an optional start index and chunk size
  (defaults: start=0, chunk_size=5)

Usage example:
    python relationsBuilder.py --start 10 --chunk-size 8

The script preserves the original behaviour but resets per-chunk results
so previously processed lemmas are not repeatedly re-inserted.
"""

import argparse
import json
import sqlite3
from typing import Dict, List

import requests
from multiwordnet.wordnet import WordNet
from multiwordnet.db import compile

from MistralInterface import MistralInterface


# Initialize multiwordnet for Italian (keeps original behaviour)
compile('italian', 'lemma')
LWN = WordNet('italian')


PROMPT_TEMPLATE = """
Riceverai una lista di sostantivi italiani. Per ogni parola restituisci aggettivo, avverbio
e verbo morfologicamente **esistenti** in italiano, oppure "N/A" se non esistono.
Segui queste regole:
- **Aggettivo**: derivato da radice del sostantivo.
- **Avverbio**: termina in "-ente" e deriva dall'aggettivo correlato.
- **Verbo**: derivato da radice del sostantivo.
- **Non inventare**! Piuttosto, usa "N/A".
- Restituisci JSON in questo formato:

{{
    "allegria": {{
        "morpho": {{
            "a": "allegro",
            "r": "allegramente",
            "v": "rallegrare"
        }}
    }},
    "bontà": {{
        "morpho": {{
            "a": "buono",
            "r": "N/A",
            "v": "N/A"
        }}
    }},
    ...
}}

Parole da analizzare:
{list}
"""


def ensure_db(conn: sqlite3.Connection) -> None:
    """Create tables if they do not exist."""
    c = conn.cursor()
    c.execute(
        '''
    CREATE TABLE IF NOT EXISTS words (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lemma TEXT NOT NULL UNIQUE,
        pos TEXT NOT NULL
    );
    '''
    )
    c.execute(
        '''
    CREATE TABLE IF NOT EXISTS derived_forms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lemma_id INTEGER NOT NULL,
        form TEXT NOT NULL,
        pos TEXT NOT NULL,
        relation_type TEXT NOT NULL,
        FOREIGN KEY (lemma_id) REFERENCES words(id)
    );
    '''
    )
    conn.commit()


def load_paisa_set(path: str = 'lemma-sorted-frequencies-paisa.txt') -> set:
    """Load the paisà lemma frequency file and return a set of lemmas.

    Lines starting with '#' or empty lines are ignored.
    If the file cannot be opened an empty set is returned.
    """
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            lines = fh.read().splitlines()
    except FileNotFoundError:
        print(f"Warning: paisa file not found at {path}. Continuing with empty set.")
        return set()
    s = set()
    for line in lines:
        if not line or line[0] == '#' or line.strip() == '':
            continue
        parts = [p.strip() for p in line.split(",")]
        if not parts:
            continue
        term = parts[0]
        s.add(term)
    return s


def build_word_list() -> List[str]:
    """Extract and filter noun lemmas from the loaded WordNet instance."""
    word_list: List[str] = []
    for lemma in LWN.lemmas:
        if getattr(lemma, 'pos', None) == 'n':
            text = getattr(lemma, '_lemma', None)
            if not isinstance(text, str):
                continue
            if any(char.isdigit() for char in text):
                continue
            if any(not char.isalnum() and char not in (' ', '-') for char in text):
                continue
            word_list.append(text)
    word_list = sorted(list(set(word_list)))
    return word_list


def process_chunk(chunk: List[str], chunk_index: int, paisa_set: set, mistral: MistralInterface) -> Dict[str, Dict[str, str]]:
    """Call the LLM for a chunk of words and validate results against paisa_set.

    Returns a dict mapping noun -> { 'a': adj or 'N/A', 'v': verb or 'N/A', 'r': adv or 'N/A' }
    """
    formatted = PROMPT_TEMPLATE.format(list='\n'.join(chunk))
    print(f"Processing chunk {chunk_index}: {chunk}")
    resp = mistral.invokeLLM(_prompt=formatted, _format='json_object')
    terms: Dict[str, Dict[str, str]] = {}
    try:
        # The original code used json.loads(resp[0])
        results = json.loads(resp[0]) if isinstance(resp, (list, tuple)) else json.loads(resp)
        for noun, entry in results.items():
            a = 'N/A'
            v = 'N/A'
            r = 'N/A'
            if isinstance(entry, dict) and 'morpho' in entry:
                morpho = entry.get('morpho') or {}
                a = morpho.get('a', 'N/A')
                v = morpho.get('v', 'N/A')
                r = morpho.get('r', 'N/A')
                if v != 'N/A' and v not in paisa_set:
                    v = 'N/A'
                if a != 'N/A' and a not in paisa_set:
                    a = 'N/A'
                if r != 'N/A' and r not in paisa_set:
                    r = 'N/A'
            terms[noun] = {'a': a, 'v': v, 'r': r}
    except Exception:
        print('Failed to parse JSON response for chunk:', chunk)
    return terms


def insert_terms(conn: sqlite3.Connection, terms: Dict[str, Dict[str, str]]) -> None:
    c = conn.cursor()
    for lemma, forms in terms.items():
        c.execute('INSERT OR IGNORE INTO words (lemma, pos) VALUES (?, ?)', (lemma, 'n'))
        c.execute('SELECT id FROM words WHERE lemma = ?', (lemma,))
        row = c.fetchone()
        if not row:
            # This should not happen but guard against it
            continue
        lemma_id = row[0]
        for pos, form in forms.items():
            if form and form != 'N/A':
                c.execute(
                    '''
                INSERT OR REPLACE INTO derived_forms (lemma_id, form, pos, relation_type)
                VALUES (?, ?, ?, ?)
                '''
                    , (lemma_id, form, pos, 'morphological')
                )
    conn.commit()


def main(start: int = 0, chunk_size: int = 5) -> None:
    conn = sqlite3.connect('relations_italian.db3')
    ensure_db(conn)
    print("Loading paisa set and building word list...")
    paisa_set = load_paisa_set()
    word_list = build_word_list()
    print(f'Number of nouns: {len(word_list)}')

    mistral = MistralInterface()

    # iterate chunks starting at `start` index
    for i in range(start, len(word_list), chunk_size):
        chunk = word_list[i:i + chunk_size]
        terms = process_chunk(chunk, i, paisa_set, mistral)
        if terms:
            insert_terms(conn, terms)

    conn.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Build relations_italian.db3 with derived forms')
    parser.add_argument('--start', type=int, default=0, help='initial lemma index (default: 0)')
    parser.add_argument('--chunk-size', type=int, default=5, help='number of lemmas per LLM call (default: 5)')
    args = parser.parse_args()
    main(start=args.start, chunk_size=args.chunk_size)
