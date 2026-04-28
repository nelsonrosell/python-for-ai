# python-for-ai

## Run tests

For the nicest colored output, use `pytest`:

```powershell
.\.venv\Scripts\python -m pytest .\tests -v --color=yes
```

Run the targeted security-related tests with `pytest`:

```powershell
.\.venv\Scripts\python -m pytest .\tests\test_config.py .\tests\test_sql_security.py .\tests\test_streamlit_auth.py -v --color=yes
```

Run one module with `pytest`:

```powershell
.\.venv\Scripts\python -m pytest .\tests\test_streamlit_auth.py -v --color=yes
```

Run one specific test method with `pytest`:

```powershell
.\.venv\Scripts\python -m pytest .\tests\test_streamlit_auth.py -k trusted_header_auth_uses_header_value_as_principal -v --color=yes
```

## Run tests with unittest

From the repository root:

```powershell
.\.venv\Scripts\python .\run_unittests.py
```

Run the targeted security-related tests:

```powershell
.\.venv\Scripts\python .\run_unittests.py tests.test_config tests.test_sql_security tests.test_streamlit_auth
```

Run one test module in verbose mode:

```powershell
.\.venv\Scripts\python .\run_unittests.py tests.test_streamlit_auth
```

Run one specific test method:

```powershell
.\.venv\Scripts\python .\run_unittests.py tests.test_streamlit_auth.TestStreamlitAuth.test_trusted_header_auth_uses_header_value_as_principal
```

## VS Code task

A VS Code task named `Run pytest suite` is available and runs:

```powershell
.\.venv\Scripts\python -m pytest tests -v --color=yes
```

There are also unittest-based tasks if you want the custom `run_unittests.py` formatting.

A VS Code task named `Run unittest suite` is available and runs:

```powershell
.\.venv\Scripts\python .\run_unittests.py
```

You can run it from `Terminal: Run Task` in VS Code.
