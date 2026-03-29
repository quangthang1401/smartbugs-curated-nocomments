# SmartBugs Curated — Comment-Free Edition

A fork of [smartbugs/smartbugs-curated](https://github.com/smartbugs/smartbugs-curated) with **all comments removed** from Solidity source files.

## Purpose

This dataset is intended for **blind testing of LLM-based smart contract vulnerability detection**. By stripping comments — including developer annotations, NatSpec documentation, and inline hints — the dataset forces models to reason purely from code structure and semantics, without leaking vulnerability labels or contextual clues.

## What was removed

- Single-line comments (`// ...`)
- Multi-line comments (`/* ... */`)
- NatSpec / documentation comments (`/** ... */`)
- Consecutive blank lines collapsed to a single blank line

String literals containing `//` or `/*` characters are preserved correctly.

## Structure

```
dataset/             # Comment-free .sol files (same folder structure as the original)
scripts/             # The Python script used to strip comments
```

## Regenerating

To regenerate the dataset from the original source:

```bash
python scripts/remove_comments.py -i <path-to-original-dataset> -o dataset/
```

## Credits

Original dataset: [smartbugs/smartbugs-curated](https://github.com/smartbugs/smartbugs-curated)
