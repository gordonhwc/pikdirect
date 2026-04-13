# AGENTS.md

## Purpose

This project prioritizes clean final implementation over incremental preservation.
Design for the codebase that should exist, not for compatibility with code that no longer matters.

## Core Principles

- Prefer the simplest design that cleanly solves the real problem end to end.
- Prioritize overall system coherence over preserving incidental structure.
- Do not keep compatibility shims, legacy branches, or transitional abstractions unless they are genuinely required.
- If a cleaner solution requires refactoring nearby code into a more logical structure, prefer the refactor.
- Optimize for final code quality, not minimal diff size.
- Keep refactors purposeful and bounded, but do not preserve internal complexity for compatibility alone.
- Avoid redundant wrappers, one-off adapters, and special-case code paths when a unified model is clearer.

## Python Style

- Use `uv` for dependency and environment management.
- Keep the project virtual environment in `.venv`.
- Target the latest Python version used by the project. Do not add backward-compatibility code for older versions.
- Prefer direct, modern Python over defensive patterns carried over from older code.
- Use type annotations consistently, but do not add noisy annotations that do not improve clarity.
- Keep modules flat and readable. Order functions and methods by logical reading flow.
- In modules, place code in the order a reader would naturally need to understand it.
- In classes, keep magic methods first, then public methods, then internal helpers.
- Prefer long CLI flags when possible.
- Do not use explicit success exit codes when normal function return is sufficient. Let failures raise naturally unless
  there is a clear reason to intercept them.

## Comments And Docstrings

- Add brief file docstrings for non-trivial modules.
- Add brief function or method docstrings when they help explain purpose or behavior.
- Regular comments should be short and direct, and should not end with a period.
- Docstrings should be complete sentences and should end with proper punctuation.

## Refactoring Guidance

- Remove unused fields, helper functions, and abstractions when they no longer serve the current design.
- Collapse overly indirect flows when a more direct structure is easier to read.
- Prefer one clear model over parallel models for single-file vs multi-file, old flow vs new flow, or similar splits.
- When reviewing structure, look for signs of historical residue and simplify them away.
