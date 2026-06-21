import pytest


@pytest.fixture(autouse=True)
def set_required_env_vars(monkeypatch):
    """Ensure required env vars are present for all tests."""
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-test")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
