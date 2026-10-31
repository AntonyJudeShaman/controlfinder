"""Answers written from the retrieved controls, checked in code and graded by a judge.

`llm` is the one door to every model call, with a cache on disk. `prompt` builds the generation
prompt and recognizes an abstention, `citations` checks an answer's bracketed control IDs
against its context, and `judge` scores faithfulness with a fixed rubric.
"""
