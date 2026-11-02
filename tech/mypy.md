# mypy

## 1. What it is

mypy is a **static type checker** for Python. Python lets you write **type hints** such as `def increment(self) -> int:` but does not enforce them when the program runs. mypy reads the hints, follows the data through the code without running it, and reports places where the types cannot be right (passing text where a number is required, returning `None` from a function that promises an `int`).

## 2. Why this repository uses it

The layers talk to each other through typed interfaces (`VisitStore`, `Connections`). With `strict = true`, mypy proves those contracts hold for every call, which catches whole classes of mistakes before a test is even written. `make lint` runs it.

## 3. Where it appears

| File | Role |
| --- | --- |
| `pyproject.toml` | `[tool.mypy]` and one override for tests (see `toml.md`). |
| `Makefile` | Target `lint` runs `mypy`. |
| `src/`, `tests/` | The checked code. `types-PyYAML` supplies hints for the YAML library. |

## 4. How it works underneath

mypy parses every file named by `files`, builds a table of the type of every name, function and class, and checks each statement against it. A **Protocol** is a type that says "anything with these methods"; mypy checks structurally that an object has them. `strict = true` switches on a bundle of options: every function must have annotated parameters and return value, no implicit `Any`, no untyped calls, warnings for unused ignores. A comment `# type: ignore[misc]` silences one specific error on one line. Libraries without hints need separate "stub" packages (`types-PyYAML`).

## 5. Walkthrough of this repository's use



## 6. Try it yourself

```bash
.venv/bin/mypy
```

Prints `Success: no issues found in N source files`.

```bash
printf 'def f(x: int) -> str:\n    return x\n' > /tmp/m.py && .venv/bin/mypy --strict /tmp/m.py
```

Reports `Incompatible return value type (got "int", expected "str")`.

```bash
grep -rn "type: ignore" src tests
```

Lists every silenced line; there are only a few, each with an error code.

## 7. Mistakes people make

- **Using `Any` to make errors disappear.** It switches checking off for that value.
- **Blanket `# type: ignore`.** Always give the error code.
- **Treating mypy as proof of correctness.** It checks types, not behaviour.

## 8. Check yourself

1. Does Python enforce type hints when running? *No.*
2. What does `strict = true` demand of every function? *Fully annotated parameters and return type.*
3. Why are test functions allowed to be untyped? *The override removes annotation noise; names carry the meaning.*
4. What is a Protocol? *A type defined by the methods an object has.*
5. Which command runs mypy for the project? *`make lint` (it calls `mypy`).*

## 9. Further reading

- mypy documentation: https://mypy.readthedocs.io/en/stable/
- Strict mode options: https://mypy.readthedocs.io/en/stable/command_line.html#cmdoption-mypy-strict
- Protocols: https://mypy.readthedocs.io/en/stable/protocols.html
- Python typing: https://docs.python.org/3.13/library/typing.html
