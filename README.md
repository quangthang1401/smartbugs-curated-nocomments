# SmartBugs Curated — Line-Preserving Comment-Free Edition

A fork of [smartbugs/smartbugs-curated](https://github.com/smartbugs/smartbugs-curated) with **all comments replaced by whitespace**, preserving original line numbers.

## Purpose

This dataset is intended for **blind testing of LLM-based smart contract vulnerability detection**. By replacing comments with whitespace — including developer annotations, NatSpec documentation, and inline hints — the dataset forces models to reason purely from code structure and semantics, while **keeping line numbers identical to the original repository**. This ensures that any line-specific reports (e.g., "vulnerability at line 42") remain accurate and directly mappable to the source.

## What was replaced

- Single-line comments (`// ...`) replaced with spaces.
- Multi-line comments (`/* ... */`) characters replaced with spaces, **preserving `\n`**.
- NatSpec / documentation comments (`/** ... */`) characters replaced with spaces, **preserving `\n`**.

String literals containing `//` or `/*` characters are preserved correctly.

## Structure

```
dataset/             # Line-preserved .sol files (same folder structure as the original)
scripts/             # The Python script used to process comments
```

## Regenerating

To regenerate the dataset from the original source:

```bash
python scripts/remove_comments.py -i <path-to-original-dataset> -o dataset/
```

## Credits

Original dataset: [smartbugs/smartbugs-curated](https://github.com/smartbugs/smartbugs-curated)
