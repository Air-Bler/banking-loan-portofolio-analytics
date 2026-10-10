from api.settings import Settings


def test_azure_openai_settings_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://oai-test.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "secret-key")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
    settings = Settings()
    assert settings.azure_openai_endpoint == "https://oai-test.openai.azure.com/"
    assert settings.azure_openai_deployment == "gpt-4o-mini"
    assert settings.azure_openai_api_key.get_secret_value() == "secret-key"


def test_azure_openai_api_version_has_a_default(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_API_VERSION", raising=False)
    assert Settings().azure_openai_api_version == "2024-10-21"


def test_azure_openai_key_is_never_printed(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "secret-key")
    settings = Settings()
    assert "secret-key" not in repr(settings)
    assert "secret-key" not in str(settings.model_dump())
