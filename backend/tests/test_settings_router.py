from unittest.mock import AsyncMock, MagicMock, patch

from app.routers import settings_router

MOCK_USER_ID = "11111111-2222-3333-4444-555555555555"


def setup_function(_):
    settings_router._VERIFY_CACHE.clear()
    settings_router._VERIFY_USER_CALLS.clear()


def teardown_function(_):
    settings_router._VERIFY_CACHE.clear()
    settings_router._VERIFY_USER_CALLS.clear()


def test_settings_providers_unauthenticated_returns_401(client):
    """Verify that GET /api/settings/providers without token returns HTTP 401."""
    response = client.get("/api/settings/providers")
    assert response.status_code == 401


def test_create_openai_compatible_missing_base_url_validation_error(authed_client):
    """Verify validation failure when creating OpenAI-Compatible provider without base_url."""
    response = authed_client.post(
        "/api/settings/providers",
        json={
            "provider": "openai_compatible",
            "api_key": "sk-test-key",
            "model_name": "llama-3"
        }
    )
    assert response.status_code == 422


@patch("app.routers.settings_router.get_supabase_client")
def test_create_provider_config_success(mock_get_supabase, authed_client):
    """Verify successful creation of Gemini provider config with masked key response."""
    mock_supabase = MagicMock()
    mock_get_supabase.return_value = mock_supabase

    # Mock DB insert response
    mock_insert_response = MagicMock()
    mock_insert_response.data = [{
        "id": "c1111111-2222-3333-4444-555555555555",
        "user_id": MOCK_USER_ID,
        "provider": "gemini",
        "display_name": "My Gemini Key",
        "api_key_enc": "enc_data_string",
        "base_url": None,
        "model_name": "gemini-2.5-flash",
        "is_default": True,
        "created_at": "2026-07-24T12:00:00Z",
        "updated_at": "2026-07-24T12:00:00Z"
    }]

    mock_supabase.table.return_value.insert.return_value.execute.return_value = mock_insert_response
    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

    with patch("app.routers.settings_router.CryptoService") as mock_crypto_cls:
        mock_crypto = MagicMock()
        mock_crypto.encrypt.return_value = "enc_data_string"
        mock_crypto_cls.return_value = mock_crypto

        response = authed_client.post(
            "/api/settings/providers",
            json={
                "provider": "gemini",
                "api_key": "AIzaSy123456789",
                "display_name": "My Gemini Key",
                "model_name": "gemini-2.5-flash",
                "is_default": True
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "c1111111-2222-3333-4444-555555555555"
        assert data["provider"] == "gemini"
        assert data["is_default"] is True


@patch("app.routers.settings_router.get_supabase_client")
def test_list_provider_configs_success(mock_get_supabase, authed_client):
    """Verify GET /api/settings/providers returns list of configs with masked keys."""
    mock_supabase = MagicMock()
    mock_get_supabase.return_value = mock_supabase

    mock_select_response = MagicMock()
    mock_select_response.data = [{
        "id": "c1111111-2222-3333-4444-555555555555",
        "user_id": MOCK_USER_ID,
        "provider": "openai",
        "display_name": None,
        "api_key_enc": "enc_openai_key",
        "base_url": None,
        "model_name": "gpt-4o-mini",
        "is_default": True,
        "created_at": "2026-07-24T12:00:00Z",
        "updated_at": "2026-07-24T12:00:00Z"
    }]

    mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = mock_select_response

    response = authed_client.get("/api/settings/providers")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 1
    assert data[0]["provider"] == "openai"


@patch("app.routers.settings_router.get_supabase_client")
def test_save_embedding_config_locked_when_documents_exist_returns_400(mock_get_supabase, authed_client):
    """Verify POST /api/settings/embedding rejects update when user has uploaded documents (locked)."""
    mock_supabase = MagicMock()
    mock_get_supabase.return_value = mock_supabase

    # Mock documents count > 0 (has documents)
    mock_doc_res = MagicMock()
    mock_doc_res.count = 5

    # Mock existing embedding config present
    mock_existing_res = MagicMock()
    mock_existing_res.data = [{"user_id": MOCK_USER_ID, "provider": "gemini"}]

    def mock_table(table_name):
        mock_t = MagicMock()
        if table_name == "documents":
            mock_t.select.return_value.eq.return_value.execute.return_value = mock_doc_res
        elif table_name == "user_embedding_configs":
            mock_t.select.return_value.eq.return_value.execute.return_value = mock_existing_res
        return mock_t

    mock_supabase.table.side_effect = mock_table

    response = authed_client.post(
        "/api/settings/embedding",
        json={
            "provider": "openai",
            "model_name": "text-embedding-3-small",
            "embedding_dimensions": 1536
        }
    )
    assert response.status_code == 400
    assert "terkunci" in response.json()["detail"]


@patch("app.routers.settings_router.get_supabase_client")
def test_save_embedding_config_auto_dimensions_stores_null_on_verify_success(mock_get_supabase, authed_client):
    """Verify omitted dimensions store NULL so the provider uses model default."""
    mock_supabase = MagicMock()
    mock_get_supabase.return_value = mock_supabase

    mock_doc_res = MagicMock()
    mock_doc_res.count = 0
    mock_existing_res = MagicMock()
    mock_existing_res.data = []
    mock_upsert_res = MagicMock()
    mock_upsert_res.data = [{
        "provider": "openai_compatible", "base_url": "https://9router.aes.my.id/v1",
        "model_name": "jina-ai/jina-embeddings-v5-omni-small",
        "embedding_dimensions": None,
    }]

    mock_provider_res = MagicMock()
    mock_provider_res.data = [{"api_key_enc": "enc"}]

    tables: dict[str, MagicMock] = {}

    def mock_table(table_name):
        if table_name not in tables:
            mock_t = MagicMock()
            if table_name == "documents":
                mock_t.select.return_value.eq.return_value.execute.return_value = mock_doc_res
            elif table_name == "user_embedding_configs":
                mock_t.select.return_value.eq.return_value.execute.return_value = mock_existing_res
                mock_t.upsert.return_value.execute.return_value = mock_upsert_res
            elif table_name == "user_provider_configs":
                mock_t.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = mock_provider_res
            tables[table_name] = mock_t
        return tables[table_name]

    mock_supabase.table.side_effect = mock_table

    with patch("app.routers.settings_router.model_service.fetch_available_models",
               new=AsyncMock(return_value={"success": True, "models": ["m"],
                                           "default_model": "m", "error": None})), \
         patch("app.routers.settings_router.CryptoService") as mock_crypto_cls:
        mock_crypto_cls.return_value.decrypt.return_value = "9router-key"
        response = authed_client.post(
            "/api/settings/embedding",
            json={"provider": "openai_compatible", "model_name": "jina-ai/jina-embeddings-v5-omni-small"},
        )
    assert response.status_code == 200
    assert response.json()["embedding_dimensions"] is None
    upsert_payload = tables["user_embedding_configs"].upsert.call_args[0][0]
    assert upsert_payload["embedding_dimensions"] is None


@patch("app.routers.settings_router.model_service.fetch_available_models",
       new_callable=AsyncMock)
def test_verify_models_success(mock_fetch, authed_client):
    """Verify POST /api/settings/providers/verify-models returns model list."""
    mock_fetch.return_value = {
        "success": True,
        "models": ["gemini-2.5-flash", "gemini-2.5-pro"],
        "default_model": "gemini-2.5-flash",
        "error": None
    }
    response = authed_client.post(
        "/api/settings/providers/verify-models",
        json={
            "provider": "gemini",
            "api_key": "AIzaSyTest"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "gemini-2.5-flash" in data["models"]
    assert data["default_model"] == "gemini-2.5-flash"


@patch("app.routers.settings_router.model_service.fetch_available_models",
       new_callable=AsyncMock)
def test_verify_embedding_models_success(mock_fetch, authed_client):
    """Verify POST /api/settings/providers/verify-models with model_type=embedding and live vector probing."""
    mock_fetch.return_value = {
        "success": True,
        "models": ["models/gemini-embedding-001", "models/text-embedding-004"],
        "default_model": "models/gemini-embedding-001",
        "probed_dimension": 768,
        "error": None
    }
    response = authed_client.post(
        "/api/settings/providers/verify-models",
        json={
            "provider": "gemini",
            "model_type": "embedding",
            "api_key": "AIzaSyTest"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "models/gemini-embedding-001" in data["models"]
    assert data["probed_dimension"] == 768


@patch("app.routers.settings_router.get_supabase_client")
def test_get_enrichment_config_defaults_to_standard(mock_get_supabase, authed_client):
    """Verify GET /api/settings/enrichment returns the default preset when unset."""
    mock_supabase = MagicMock()
    mock_get_supabase.return_value = mock_supabase

    mock_response = MagicMock()
    mock_response.data = []
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response

    response = authed_client.get("/api/settings/enrichment")
    assert response.status_code == 200
    assert response.json() == {"preset": "standard", "max_enriched_paragraphs": 75}


@patch("app.routers.settings_router.get_supabase_client")
def test_save_enrichment_config_upserts_user_preset(mock_get_supabase, authed_client):
    """Verify PUT /api/settings/enrichment persists the user's preset."""
    mock_supabase = MagicMock()
    mock_get_supabase.return_value = mock_supabase

    mock_response = MagicMock()
    mock_response.data = [{"user_id": MOCK_USER_ID, "preset": "high"}]
    mock_supabase.table.return_value.upsert.return_value.execute.return_value = mock_response

    response = authed_client.put("/api/settings/enrichment", json={"preset": "high"})
    assert response.status_code == 200
    assert response.json() == {"preset": "high", "max_enriched_paragraphs": 150}
    mock_supabase.table.return_value.upsert.assert_called_once_with(
        {"user_id": MOCK_USER_ID, "preset": "high"},
        on_conflict="user_id"
    )
