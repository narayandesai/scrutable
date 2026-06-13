# scrutable

## Naming conventions

Use control theory vocabulary throughout. Don't introduce service-oriented names (`ServiceProfile`, `ServiceEntry`, etc.) — the correct terms are `PlantProfile`, `PlantEntry`, and so on. When in doubt, prefer the CT term.

## Commands

- **Run tests:** `uv run pytest`
- **Run specific test file:** `uv run pytest tests/test_foo.py -v`
- **Run with marker:** `uv run pytest -m slow`
