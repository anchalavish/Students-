from fastapi.testclient import TestClient

from app.main import create_app


def make_client(tmp_path):
    return TestClient(create_app(tmp_path / "test_students.db"))


def sample_student(**overrides):
    payload = {
        "name": "Aarav Sharma",
        "date_of_birth": "2006-04-15",
        "email": "aarav@example.com",
        "course": "Computer Science",
        "address": "Sample City",
        "enrollment_date": "2025-06-01",
    }
    payload.update(overrides)
    return payload


def test_full_crud_lifecycle(tmp_path):
    with make_client(tmp_path) as client:
        created = client.post("/students", json=sample_student())
        assert created.status_code == 201
        student = created.json()
        student_id = student["student_id"]
        assert student["name"] == "Aarav Sharma"

        fetched = client.get(f"/students/{student_id}")
        assert fetched.status_code == 200
        assert fetched.json()["email"] == "aarav@example.com"

        replaced = client.put(
            f"/students/{student_id}",
            json=sample_student(name="Aarav S.", phone="+91 98765 43210"),
        )
        assert replaced.status_code == 200
        assert replaced.json()["name"] == "Aarav S."

        patched = client.patch(
            f"/students/{student_id}", json={"course": "Data Science"}
        )
        assert patched.status_code == 200
        assert patched.json()["course"] == "Data Science"

        deleted = client.delete(f"/students/{student_id}")
        assert deleted.status_code == 204
        assert client.get(f"/students/{student_id}").status_code == 404


def test_list_search_and_filter(tmp_path):
    with make_client(tmp_path) as client:
        client.post("/students", json=sample_student())
        client.post(
            "/students",
            json=sample_student(
                name="Mira Patel",
                date_of_birth="2007-08-12",
                email=None,
                phone="555-0101",
                course="Mathematics",
            ),
        )

        assert len(client.get("/students").json()) == 2
        assert len(client.get("/students", params={"q": "Mira"}).json()) == 1
        assert len(
            client.get("/students", params={"course": "Computer Science"}).json()
        ) == 1
        assert len(
            client.get(
                "/students", params={"date_of_birth_after": "2006-12-31"}
            ).json()
        ) == 1


def test_validation_and_missing_records(tmp_path):
    with make_client(tmp_path) as client:
        no_contact = client.post(
            "/students",
            json=sample_student(email=None),
        )
        assert no_contact.status_code == 422

        bad_email = client.post(
            "/students",
            json=sample_student(email="not-an-email"),
        )
        assert bad_email.status_code == 422

        assert client.get("/students/999").status_code == 404
        assert client.put(
            "/students/999", json=sample_student()
        ).status_code == 404
        assert client.delete("/students/999").status_code == 404


def test_patch_cannot_remove_all_contact_information(tmp_path):
    with make_client(tmp_path) as client:
        created = client.post("/students", json=sample_student())
        student_id = created.json()["student_id"]

        response = client.patch(f"/students/{student_id}", json={"email": None})
        assert response.status_code == 422
        assert client.get(f"/students/{student_id}").json()["email"] == "aarav@example.com"
