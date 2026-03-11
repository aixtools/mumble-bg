# Repository Notes

- Prefer `~/.venv/codex` for local Python and pytest runs unless the user says otherwise.
- If pytest is blocked only by writes under `<repo>/.pytest_cache`, rerun with either:
  - `-o cache_dir=/tmp/pytest-cache`, or
  - escalated permissions when appropriate.
- Do not treat `.pytest_cache` sandbox write failures as a code failure by default.
