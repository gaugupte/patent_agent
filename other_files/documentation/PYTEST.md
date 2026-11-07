Here’s the pytest work, starting with the files it added or changed.

### Pytest setup

- [pytest.ini](E:/Gautam/work_folder/own/nlp/patent_agent/pytest.ini) tells pytest how to find and configure the Django project. It points pytest-django at `portal_config.settings`, adds `web_portal` to Python’s import path, and selects the account and patents test files.

- [requirements-test.txt](E:/Gautam/work_folder/own/nlp/patent_agent/requirements-test.txt) lists the test dependencies and includes the application’s regular requirements. That lets you install everything needed to run the tests with one command:
  ```powershell
  python -m pip install -r requirements-test.txt
  ```

- [web_portal/conftest.py](E:/Gautam/work_folder/own/nlp/patent_agent/web_portal/conftest.py) defines shared pytest fixtures: sample organizations, a portal user, an authenticated test client, and customers. A fixture is reusable setup that pytest supplies to a test when the test requests it.

- [web_portal/patents/conftest.py](E:/Gautam/work_folder/own/nlp/patent_agent/web_portal/patents/conftest.py) sets up in-memory file storage for patent tests. Uploaded test files don’t need to be written to the normal media directory.

### The tests

- [web_portal/accounts/tests.py](E:/Gautam/work_folder/own/nlp/patent_agent/web_portal/accounts/tests.py) checks account and session behaviour, including sign-in and sign-out, invalid credentials, inactive organizations, single-session enforcement, and email verification codes.

- [web_portal/patents/tests.py](E:/Gautam/work_folder/own/nlp/patent_agent/web_portal/patents/tests.py) checks patent-related API behaviour, including authentication, organization data isolation, duplicate customers, and file upload validation. It also checks a successful IDF flow while mocking the analysis step, so the test doesn’t need to call Ollama.

Most tests use pytest functions and fixtures instead of Django’s `TestCase` class setup. The tests still exercise Django’s client and database; pytest-django connects pytest to those Django features.

### Other changes related to the tests

- [.github/workflows/ci.yml](E:/Gautam/work_folder/own/nlp/patent_agent/.github/workflows/ci.yml) installs the test requirements and runs `pytest` in CI.
- [deployment/civo/README.md](E:/Gautam/work_folder/own/nlp/patent_agent/deployment/civo/README.md) now includes the local test command.
- [web_portal/patents/api.py](E:/Gautam/work_folder/own/nlp/patent_agent/web_portal/patents/api.py) has a small transaction handling change. A duplicate-customer test exposed that catching a database integrity error inside an outer transaction could leave that transaction unusable. The create operation now uses a nested transaction so the error can be handled safely.

I ran the suite locally with a temporary SQLite database: **20 tests passed**. For local runs, the commands are:

```powershell
$env:DATABASE_URL = "sqlite:///:memory:"
python -m pytest
```