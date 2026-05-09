"""Unit tests for the three-layer config loader."""

from __future__ import annotations

from app.config_layers import apply_env_overrides


def test_apply_env_overrides_no_env_passes_through():
    yaml_dict = {
        "mode": "normal",
        "server": {"host": "127.0.0.1", "port": 8000, "cors_origins": ["a"]},
    }
    out = apply_env_overrides(yaml_dict, {})
    assert out == yaml_dict
    # Returns a copy, not the same dict.
    assert out is not yaml_dict
    assert out["server"] is not yaml_dict["server"]


def test_apply_env_overrides_top_level_mode():
    out = apply_env_overrides({"mode": "normal"}, {"VIBE_MODE": "demo"})
    assert out["mode"] == "demo"


def test_apply_env_overrides_secret_key_top_level_special_case():
    out = apply_env_overrides({}, {"VIBE_SECRET_KEY": "abc123"})
    assert out["secret_key"] == "abc123"


def test_apply_env_overrides_nested_server_host():
    yaml_dict = {"server": {"host": "127.0.0.1", "port": 8000}}
    out = apply_env_overrides(yaml_dict, {"VIBE_SERVER_HOST": "0.0.0.0"})
    assert out["server"]["host"] == "0.0.0.0"
    assert out["server"]["port"] == 8000


def test_apply_env_overrides_int_coercion():
    out = apply_env_overrides(
        {"server": {"host": "x", "port": 1}},
        {"VIBE_SERVER_PORT": "9001"},
    )
    assert out["server"]["port"] == 9001
    assert isinstance(out["server"]["port"], int)


def test_apply_env_overrides_csv_cors_origins():
    out = apply_env_overrides(
        {"server": {"cors_origins": ["a"]}},
        {"VIBE_SERVER_CORS_ORIGINS": "http://a, http://b ,, http://c"},
    )
    assert out["server"]["cors_origins"] == [
        "http://a",
        "http://b",
        "http://c",
    ]


def test_apply_env_overrides_csv_empty_string_is_noop():
    yaml_dict = {"server": {"cors_origins": ["http://default"]}}
    out = apply_env_overrides(yaml_dict, {"VIBE_SERVER_CORS_ORIGINS": ""})
    assert out["server"]["cors_origins"] == ["http://default"]


def test_apply_env_overrides_creates_missing_section():
    out = apply_env_overrides({}, {"VIBE_DEFAULTS_REQUEST_TIMEOUT_SECONDS": "30"})
    assert out["defaults"]["request_timeout_seconds"] == 30


def test_apply_env_overrides_unknown_env_var_ignored():
    yaml_dict = {"mode": "normal"}
    out = apply_env_overrides(yaml_dict, {"VIBE_NOT_A_REAL_VAR": "x"})
    assert out == yaml_dict


def test_apply_env_overrides_does_not_mutate_input():
    yaml_dict = {"server": {"host": "127.0.0.1", "port": 8000}}
    apply_env_overrides(yaml_dict, {"VIBE_SERVER_HOST": "0.0.0.0"})
    assert yaml_dict["server"]["host"] == "127.0.0.1"


def test_apply_env_overrides_max_upload_bytes():
    out = apply_env_overrides(
        {"defaults": {"request_timeout_seconds": 120, "max_upload_bytes": 10485760}},
        {"VIBE_DEFAULTS_MAX_UPLOAD_BYTES": "12345"},
    )
    assert out["defaults"]["max_upload_bytes"] == 12345
    assert isinstance(out["defaults"]["max_upload_bytes"], int)
    assert out["defaults"]["request_timeout_seconds"] == 120


def test_apply_env_overrides_executor_fields():
    out = apply_env_overrides(
        {"executor": {"default_concurrency": 1, "default_queue_size": 1,
                       "max_concurrency": 1, "max_queue_size": 1}},
        {
            "VIBE_EXECUTOR_DEFAULT_CONCURRENCY": "4",
            "VIBE_EXECUTOR_MAX_QUEUE_SIZE": "5000",
        },
    )
    assert out["executor"]["default_concurrency"] == 4
    assert out["executor"]["max_queue_size"] == 5000
    # Untouched fields preserved.
    assert out["executor"]["default_queue_size"] == 1
