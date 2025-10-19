#!/usr/bin/env python3
"""dbRelationsCleanup.py

Reads an input JSONL (`dictionaryCheckBatch.jsonl`) and an output JSONL
from the Mistral batch run (e.g. `acc803eb-...jsonl`). Matches records by
`custom_id`. For responses answering "no" (no morphological connection),
asks the human to confirm. For confirmed pairs, finds matching rows in
`relations_italian.db3` where `derived_term` equals the derived form and
prints SQL DELETE statements (dry-run only).

Usage:
    python fix_relations_cleanup.py \
        --input dictionaryCheckBatch.jsonl \
        --output acc803eb-76b4-49d9-a0ee-c6c4e0b0efb4.jsonl \
        [--db relations_italian.db3] [--yes]

Options:
    --yes    Skip interactive confirmation and accept all 'no' answers

This script will NOT execute deletes by default. It prints what would be
deleted and saves a small JSON file `to_delete.json` containing the pairs.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Tuple


def read_jsonl(path: Path) -> List[dict]:
    data = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data.append(json.loads(line))
    return data


def build_input_map(input_records: List[dict]) -> Dict[str, dict]:
    # Map custom_id -> input record
    m = {}
    for r in input_records:
        cid = r.get("custom_id")
        if cid is None:
            continue
        m[str(cid)] = r
    return m


def prompt_yes_no(prompt: str, default: bool = False) -> bool:
    if default:
        prompt = f"{prompt} [Y/n]: "
    else:
        prompt = f"{prompt} [y/N]: "
    resp = input(prompt).strip().lower()
    if resp == "":
        return default
    return resp[0] == "y"


def find_matches(conn: sqlite3.Connection, derived: str) -> List[sqlite3.Row]:
    cur = conn.cursor()
    # derived_forms.form stores the derived term. Return id, lemma_id, form, pos, relation_type
    cur.execute(
        "SELECT id, lemma_id, form, pos, relation_type FROM derived_forms WHERE form = ? COLLATE NOCASE",
        (derived,),
    )
    return cur.fetchall()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, help="Input JSONL with questions")
    p.add_argument("--output", required=True, help="Output JSONL from model")
    p.add_argument("--db", default="relations_italian.db3", help="Path to sqlite DB")
    p.add_argument("--yes", action="store_true", help="Assume confirmation for all 'no' answers")
    args = p.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    db_path = Path(args.db)

    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")
    if not output_path.exists():
        raise SystemExit(f"Output file not found: {output_path}")
    if not db_path.exists():
        raise SystemExit(f"DB file not found: {db_path}")

    print("Reading input and output JSONL...")
    inputs = read_jsonl(input_path)
    outputs = read_jsonl(output_path)

    input_map = build_input_map(inputs)

    # Collect confirmed deletions: derived_term -> root_term
    to_delete: Dict[str, str] = {}

    print(f"Found {len(outputs)} outputs to check")

    counter: int = 0

    for out in outputs:
        cid = out.get("custom_id")
        if cid is None:
            continue
        in_rec = input_map.get(str(cid))
        if in_rec is None:
            print(f"Warning: no input record for custom_id={cid}")
            continue

        # Extract derived term. The template to find is "La parola '<derived>'
        index = in_rec["body"]["messages"][0]["content"].find("La parola '")
        if index == -1:
            print(f"Warning: couldn't find derived term in input for custom_id={cid}")
            continue
        # crude extraction of derived term between quotes
        start = index + len("La parola '")  
        end = in_rec["body"]["messages"][0]["content"].find("'", start)
        derived = in_rec["body"]["messages"][0]["content"][start:end]
        # Extract root term. The template to find is "con il lemma '<root>'?"
        index = in_rec["body"]["messages"][0]["content"].find("con il lemma '")
        if index == -1:
            print(f"Warning: couldn't find root term in input for custom_id={cid}")
            continue    
        start = index + len("con il lemma '")
        end = in_rec["body"]["messages"][0]["content"].find("'", start)
        root = in_rec["body"]["messages"][0]["content"][start:end]

        if not derived or not root:
            # fallback: try to parse from a 'question' field
            q = in_rec.get("question") or in_rec.get("text") or ""
            # crude attempt: look for pattern 'derived -> root' or 'derived / root'
            if "->" in q:
                parts = [p.strip() for p in q.split("->", 1)]
                if len(parts) == 2:
                    derived, root = parts[0], parts[1]

        if not derived or not root:
            print(f"Skipping custom_id={cid}: couldn't determine derived/root")
            continue

        # Normalize
        derived = derived.strip()
        root = root.strip()

        answer = out["response"]["body"]["choices"][0]["message"]["content"]
        ans_norm = str(answer).strip().lower()

        if ans_norm.find("no") != -1:
            confirm = args.yes or prompt_yes_no(
                f"Model answered NO for derived='{derived}' root='{root}'. Confirm delete relation?",
                default=False,
            )
            if confirm:
                to_delete[derived] = root

    if not to_delete:
        print("No confirmed deletions. Exiting.")
        return

    # Connect DB and show matches
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    print("\nDry-run: the following matches were found in DB for the confirmed derived terms:")
    deletions: List[Tuple[str, str, int]] = []  # derived, root, derived_forms.id

    for derived, root in to_delete.items():
        # find the row with the root term
        root_row = conn.execute("SELECT id FROM words WHERE lemma = ? COLLATE NOCASE", (root,)).fetchone()
        if not root_row:
            print(f"  - No DB row found with lemma='{root}' in words")
            continue
        root_id = root_row[0]
        # now find matching derived forms
        derived_rows = conn.execute("SELECT id, form FROM derived_forms WHERE lemma_id = ? COLLATE NOCASE", (root_id,)).fetchall()
        if not derived_rows:
            print(f"  - No DB rows found with derived form='{derived}' for root lemma_id={root_id}")
            continue
        # put derived_rows in the deletions list
        for r in derived_rows:
            # r: id, form
            df_id = r[0]
            deletions.append((derived, root, df_id))

    if not deletions:
        print("\nNo rows to delete (dry-run). Exiting.")
        return

    print("\nDry-run summary: the following DELETE statements would be executed:")
    with open("deletions.sql", "w", encoding="utf-8") as sql_file:
        for derived, root, df_id in deletions:
            print(f"  DELETE FROM derived_forms WHERE id = {df_id};  -- form='{derived}' expected_root='{root}'")
            sql_file.write(f"DELETE FROM derived_forms WHERE id = {df_id};  -- form='{derived}' expected_root='{root}'\n")

    print(f"\nSaved dry-run report and pairs to {sql_file.name}")
    print("You can use sqlite3 to execute the DELETE statements following this procedure:\n")
    print("1) Make a backup copy of your database file.")
    print("2) Open sqlite3 shell: sqlite3 relations_italian.db3")
    print("3) Read and execute the SQL file: .read deletions.sql")

if __name__ == "__main__":
    main()
