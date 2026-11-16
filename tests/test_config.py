from app.config import Settings


def test_password_special_characters_are_url_encoded():
    config = Settings(
        postgres_user="user",
        postgres_password="a#b@c/d%",
        postgres_db="webhook_db",
        db_host="db",
    )
    rendered = config.database_url.render_as_string(hide_password=False)
    assert "a%23b%40c%2Fd%25" in rendered
    assert rendered.endswith("@db:5432/webhook_db")
