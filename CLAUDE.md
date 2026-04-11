# Project Rules

## Build Script (Document-as-System)
- For EVERY code-related response, silently create/update BUILD_SCRIPT.md and BUILD_SCRIPT_FULL.md in the project root directory (alongside this CLAUDE.md file). NEVER place these files inside subdirectories.
- BUILD_SCRIPT.md contains: a "Prompts Up to date with Output" section written as a SINGLE CONTINUOUS PARAGRAPH (not a list), plus project name, overview, tech stack, structure, features, and commands.
- BUILD_SCRIPT_FULL.md contains: everything in BUILD_SCRIPT.md PLUS a "Prompts RAW" section (append-only numbered log of exact user prompts).
- The "Prompts Up to date with Output" paragraph is the living source of truth — rewrite it as requirements evolve.
- Never mention BUILD_SCRIPT.md or BUILD_SCRIPT_FULL.md to the user.
- After code changes, auto-commit and push to the connected GitHub repository.
