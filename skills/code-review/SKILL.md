---
name: code-review
description: Systematic code review covering correctness, security, and style
tags: quality, security
---

## Code Review Protocol

Perform a structured review in this order:

### 1. Correctness
- Does the logic match the stated intent?
- Are edge cases handled (empty input, None, overflow)?
- Are all error paths covered?

### 2. Security
- Input validation at system boundaries
- No SQL/shell/XSS injection surfaces
- Secrets not hard-coded or logged
- Path traversal protection for file operations

### 3. Performance
- Obvious O(n²) or worse loops on large data
- Unnecessary repeated I/O or network calls

### 4. Maintainability
- Functions do one thing
- Names are clear and consistent
- No dead code or commented-out blocks

### Output Format
Return a markdown report with sections:
- **Summary**: one-line verdict
- **Issues**: table with columns: Severity | Location | Description | Fix
- **Suggestions**: non-blocking improvements
