# Student CRUD API

A student-record backend built with **Python**, **FastAPI**, and **SQLite**, following the EWB Edu Tech internship assignment. It supports create, read, full replacement, partial update, delete, filtering, validation, and persistent local storage.

> Use fictional/dummy student data for demonstrations. Do not commit real student information, passwords, or API keys.

## Requirements

- Python 3.10 or newer
- `pip`

## Install and run

From this directory:

```bash
python -m venv .venv
```

Activate the virtual environment:

```bash
# macOS / Linux
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
```

Install dependencies and start the API:

```bash
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API is available at <http://127.0.0.1:8000>. Interactive Swagger documentation is at <http://127.0.0.1:8000/docs>; ReDoc is at <http://127.0.0.1:8000/redoc>.

SQLite creates `students.db` in this directory on first start. To choose another database file, set `DATABASE_PATH` before starting the server:

```bash
# macOS / Linux
DATABASE_PATH=/path/to/students.db uvicorn app.main:app --reload

# Windows PowerShell
$env:DATABASE_PATH = "C:\path\to\students.db"
uvicorn app.main:app --reload
```

## API endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/students` | Create a student |
| `GET` | `/students` | List, search, filter, and paginate |
| `GET` | `/students/{student_id}` | Get one student |
| `PUT` | `/students/{student_id}` | Replace all editable fields |
| `PATCH` | `/students/{student_id}` | Update supplied fields |
| `DELETE` | `/students/{student_id}` | Delete a student |

Every student must have a name, date of birth, and at least one contact method (email or phone). `course`, `address`, and `enrollment_date` are optional. The database assigns each record a unique integer `student_id`.

### Example requests

Create a record:

```bash
curl -X POST http://127.0.0.1:8000/students \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Aarav Sharma",
    "date_of_birth": "2006-04-15",
    "email": "aarav@example.com",
    "course": "Computer Science",
    "enrollment_date": "2025-06-01"
  }'
```

List/search and filter:

```bash
curl "http://127.0.0.1:8000/students?q=Aarav&limit=20&offset=0"
curl "http://127.0.0.1:8000/students?course=Computer%20Science"
curl "http://127.0.0.1:8000/students?date_of_birth_after=2005-12-31"
```

Get, replace, partially update, and delete (replace `1` with the ID returned by `POST`):

```bash
curl http://127.0.0.1:8000/students/1

curl -X PUT http://127.0.0.1:8000/students/1 \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Aarav Sharma",
    "date_of_birth": "2006-04-15",
    "email": "aarav@example.com",
    "phone": "+91 98765 43210",
    "course": "Data Science"
  }'

curl -X PATCH http://127.0.0.1:8000/students/1 \
  -H "Content-Type: application/json" \
  -d '{"course": "Mathematics"}'

curl -X DELETE http://127.0.0.1:8000/students/1
```

`GET /students` supports `q` (name/email/phone search), exact `course`, `date_of_birth_after`, `date_of_birth_before`, `limit` (1–100), and `offset`. A missing record returns `404`; invalid input returns `422`.

## Run tests

```bash
python -m pip install -r requirements.txt
pytest -q
```

Tests use a temporary database and do not modify the demo database.

## Project structure

```text
app/
  __init__.py
  main.py          # App factory, validation models, SQLite access, API routes
tests/
  test_api.py      # CRUD, filtering, and validation tests
requirements.txt
README.md
```

## Design notes

- SQLite access uses Python's standard `sqlite3` module; SQL values are parameterized.
- FastAPI's generated `/docs` page is the quickest way to demonstrate requests.
- `PUT` requires the full student record; `PATCH` changes only fields supplied.
- `PATCH` can clear optional fields with `null`, but a record must keep either email or phone.
- The optional Ollama extension is intentionally not included: the assignment's mandatory CRUD requirements are complete without it.
