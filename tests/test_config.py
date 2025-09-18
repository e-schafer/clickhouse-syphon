"""
Test module for configuration functionality including environment variable URI resolution.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic_core import ValidationError

from clickhouse_syphon.config import Config, TableConfig


class TestTableConfig:
    """Test class for TableConfig functionality."""

    def test_basic_table_config_creation(self):
        """Test creating a basic table configuration with all fields."""
        config = TableConfig(
            source_uri="clickhouse://admin:password@localhost:8123/default",
            source_table="test_table",
            target_uri="postgresql://user:password@localhost:5432/test_db",
            target_table="test_table",
            primary_keys=["id"],
            sync_mode="incremental",
            sync_column="created_at",
            batch_size=1000,
            number_of_workers=2,
        )

        assert config.source_uri == "clickhouse://admin:password@localhost:8123/default"
        assert config.target_uri == "postgresql://user:password@localhost:5432/test_db"
        assert config.source_table == "test_table"
        assert config.target_table == "test_table"
        assert config.primary_keys == ["id"]
        assert config.sync_mode == "incremental"
        assert config.sync_column == "created_at"
        assert config.batch_size == 1000
        assert config.number_of_workers == 2

    def test_empty_uris_allowed(self):
        """Test that empty URIs are allowed in configuration."""
        config = TableConfig(
            source_uri="",
            source_table="test_table",
            target_uri="",
            target_table="test_table",
            primary_keys=["id"],
            sync_mode="incremental",
            sync_column="created_at",
            batch_size=1000,
            number_of_workers=2,
        )

        assert config.source_uri == ""
        assert config.target_uri == ""

    def test_invalid_sync_mode(self):
        """Test that invalid sync mode raises ValueError."""
        with pytest.raises(ValueError, match="Sync mode must be one of"):
            TableConfig(
                source_uri="clickhouse://admin:password@localhost:8123/default",
                source_table="test_table",
                target_uri="postgresql://user:password@localhost:5432/test_db",
                target_table="test_table",
                primary_keys=["id"],
                sync_mode="invalid_mode",  # Invalid sync mode
                sync_column="created_at",
                batch_size=1000,
                number_of_workers=2,
            )

    def test_invalid_number_of_workers(self) -> None:
        """Test validation of number_of_workers field."""
        # Test too few workers
        with pytest.raises(ValidationError, match="Input should be greater than 0"):
            TableConfig(
                source_uri="clickhouse://admin:password@localhost:8123/default",
                source_table="test_table",
                target_uri="postgresql://user:password@localhost:5432/test_db",
                target_table="test_table",
                primary_keys=["id"],
                sync_mode="incremental",
                sync_column="created_at",
                batch_size=1000,
                number_of_workers=0,  # Invalid
            )

        # Test too many workers
        with pytest.raises(ValidationError, match="Input should be less than or equal to 16"):
            TableConfig(
                source_uri="clickhouse://admin:password@localhost:8123/default",
                source_table="test_table",
                target_uri="postgresql://user:password@localhost:5432/test_db",
                target_table="test_table",
                primary_keys=["id"],
                sync_mode="incremental",
                sync_column="created_at",
                batch_size=1000,
                number_of_workers=17,  # Invalid
            )

    def test_invalid_batch_size(self) -> None:
        """Test that batch size must be positive."""
        with pytest.raises(ValidationError, match="Input should be greater than 0"):
            TableConfig(
                source_uri="clickhouse://admin:password@localhost:8123/default",
                source_table="test_table",
                target_uri="postgresql://user:password@localhost:5432/test_db",
                target_table="test_table",
                primary_keys=["id"],
                sync_mode="incremental",
                sync_column="created_at",
                batch_size=0,  # Invalid
                number_of_workers=2,
            )

    def test_empty_primary_keys(self):
        """Test that empty primary keys list raises ValueError."""
        with pytest.raises(ValueError, match="Primary key column names cannot be empty"):
            TableConfig(
                source_uri="clickhouse://admin:password@localhost:8123/default",
                source_table="test_table",
                target_uri="postgresql://user:password@localhost:5432/test_db",
                target_table="test_table",
                primary_keys=[],  # Invalid
                sync_mode="incremental",
                sync_column="created_at",
                batch_size=1000,
                number_of_workers=2,
            )

    def test_invalid_uri_protocol(self):
        """Test that invalid URI protocols raise ValueError."""
        with pytest.raises(ValueError, match="protocol 'invalid' is not recognized"):
            TableConfig(
                source_uri="invalid://admin:password@localhost:8123/default",
                source_table="test_table",
                target_uri="postgresql://user:password@localhost:5432/test_db",
                target_table="test_table",
                primary_keys=["id"],
                sync_mode="incremental",
                sync_column="created_at",
                batch_size=1000,
                number_of_workers=2,
            )

    def test_uri_without_protocol(self):
        """Test that URIs without protocol raise ValueError."""
        with pytest.raises(ValueError, match="must contain a valid protocol"):
            TableConfig(
                source_uri="admin:password@localhost:8123/default",  # Missing protocol
                source_table="test_table",
                target_uri="postgresql://user:password@localhost:5432/test_db",
                target_table="test_table",
                primary_keys=["id"],
                sync_mode="incremental",
                sync_column="created_at",
                batch_size=1000,
                number_of_workers=2,
            )


class TestEnvironmentVariableURIResolution:
    """Test class for environment variable URI resolution functionality."""

    def setup_method(self):
        """Set up test environment variables."""
        self.original_source_uri = os.environ.get("SOURCE_DATABASE_URI")
        self.original_target_uri = os.environ.get("TARGET_DATABASE_URI")

    def teardown_method(self):
        """Clean up test environment variables."""
        # Restore original environment variables
        if self.original_source_uri is not None:
            os.environ["SOURCE_DATABASE_URI"] = self.original_source_uri
        elif "SOURCE_DATABASE_URI" in os.environ:
            del os.environ["SOURCE_DATABASE_URI"]

        if self.original_target_uri is not None:
            os.environ["TARGET_DATABASE_URI"] = self.original_target_uri
        elif "TARGET_DATABASE_URI" in os.environ:
            del os.environ["TARGET_DATABASE_URI"]

    def test_resolved_source_uri_from_config(self):
        """Test that non-empty config URI is returned directly."""
        config = TableConfig(
            source_uri="clickhouse://config:config@localhost:8123/config_db",
            source_table="test_table",
            target_uri="postgresql://user:password@localhost:5432/test_db",
            target_table="test_table",
            primary_keys=["id"],
            sync_mode="incremental",
            sync_column="created_at",
            batch_size=1000,
            number_of_workers=2,
        )

        resolved_uri = config.get_resolved_source_uri()
        assert resolved_uri == "clickhouse://config:config@localhost:8123/config_db"

    def test_resolved_source_uri_from_environment(self):
        """Test that empty config URI uses environment variable."""
        os.environ["SOURCE_DATABASE_URI"] = "clickhouse://env:env@localhost:8123/env_db"

        config = TableConfig(
            source_uri="",  # Empty, should use environment
            source_table="test_table",
            target_uri="postgresql://user:password@localhost:5432/test_db",
            target_table="test_table",
            primary_keys=["id"],
            sync_mode="incremental",
            sync_column="created_at",
            batch_size=1000,
            number_of_workers=2,
        )

        resolved_uri = config.get_resolved_source_uri()
        assert resolved_uri == "clickhouse://env:env@localhost:8123/env_db"

    def test_resolved_target_uri_from_environment(self):
        """Test that empty config target URI uses environment variable."""
        os.environ["TARGET_DATABASE_URI"] = "postgresql://env:env@localhost:5432/env_db"

        config = TableConfig(
            source_uri="clickhouse://admin:password@localhost:8123/default",
            source_table="test_table",
            target_uri="",  # Empty, should use environment
            target_table="test_table",
            primary_keys=["id"],
            sync_mode="incremental",
            sync_column="created_at",
            batch_size=1000,
            number_of_workers=2,
        )

        resolved_uri = config.get_resolved_target_uri()
        assert resolved_uri == "postgresql://env:env@localhost:5432/env_db"

    def test_missing_source_environment_variable(self):
        """Test error when source URI is empty and env var is not set."""
        # Ensure environment variable is not set
        if "SOURCE_DATABASE_URI" in os.environ:
            del os.environ["SOURCE_DATABASE_URI"]

        config = TableConfig(
            source_uri="",  # Empty
            source_table="test_table",
            target_uri="postgresql://user:password@localhost:5432/test_db",
            target_table="test_table",
            primary_keys=["id"],
            sync_mode="incremental",
            sync_column="created_at",
            batch_size=1000,
            number_of_workers=2,
        )

        with pytest.raises(
            ValueError, match="Source URI is empty in config and SOURCE_DATABASE_URI environment variable is not set"
        ):
            config.get_resolved_source_uri()

    def test_missing_target_environment_variable(self):
        """Test error when target URI is empty and env var is not set."""
        # Ensure environment variable is not set
        if "TARGET_DATABASE_URI" in os.environ:
            del os.environ["TARGET_DATABASE_URI"]

        config = TableConfig(
            source_uri="clickhouse://admin:password@localhost:8123/default",
            source_table="test_table",
            target_uri="",  # Empty
            target_table="test_table",
            primary_keys=["id"],
            sync_mode="incremental",
            sync_column="created_at",
            batch_size=1000,
            number_of_workers=2,
        )

        with pytest.raises(
            ValueError, match="Target URI is empty in config and TARGET_DATABASE_URI environment variable is not set"
        ):
            config.get_resolved_target_uri()

    def test_invalid_environment_uri_format(self):
        """Test that invalid URI format in environment variable raises error."""
        os.environ["SOURCE_DATABASE_URI"] = "invalid-uri-format"

        config = TableConfig(
            source_uri="",  # Empty, will use env var
            source_table="test_table",
            target_uri="postgresql://user:password@localhost:5432/test_db",
            target_table="test_table",
            primary_keys=["id"],
            sync_mode="incremental",
            sync_column="created_at",
            batch_size=1000,
            number_of_workers=2,
        )

        with pytest.raises(ValueError, match="must contain a valid protocol"):
            config.get_resolved_source_uri()

    def test_both_uris_from_environment(self):
        """Test that both source and target URIs can come from environment."""
        os.environ["SOURCE_DATABASE_URI"] = "clickhouse://env:env@localhost:8123/source_db"
        os.environ["TARGET_DATABASE_URI"] = "postgresql://env:env@localhost:5432/target_db"

        config = TableConfig(
            source_uri="",  # Empty
            source_table="test_table",
            target_uri="",  # Empty
            target_table="test_table",
            primary_keys=["id"],
            sync_mode="incremental",
            sync_column="created_at",
            batch_size=1000,
            number_of_workers=2,
        )

        source_uri = config.get_resolved_source_uri()
        target_uri = config.get_resolved_target_uri()

        assert source_uri == "clickhouse://env:env@localhost:8123/source_db"
        assert target_uri == "postgresql://env:env@localhost:5432/target_db"


class TestConfig:
    """Test class for main Config functionality."""

    def test_config_from_yaml_string(self):
        """Test creating config from YAML string."""
        yaml_content = """
tables:
  - source_uri: "clickhouse://admin:password@localhost:8123/default"
    source_table: "users"
    target_uri: "postgresql://user:password@localhost:5432/test_db"
    target_table: "users"
    primary_keys: ["id"]
    sync_mode: "incremental"
    sync_column: "created_at"
    batch_size: 1000
    number_of_workers: 2
"""

        config = Config.from_yaml_string(yaml_content)

        assert len(config.tables) == 1
        table_config = config.tables[0]
        assert table_config.source_table == "users"
        assert table_config.target_table == "users"
        assert table_config.sync_mode == "incremental"

    def test_config_from_yaml_file(self):
        """Test creating config from YAML file."""
        yaml_content = """
tables:
  - source_uri: ""
    source_table: "test_table"
    target_uri: ""
    target_table: "test_table"
    primary_keys: ["id"]
    sync_mode: "incremental"
    sync_column: "created_at"
    batch_size: 1000
    number_of_workers: 2
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            temp_file_path = f.name

        try:
            config = Config.from_yaml_file(temp_file_path)
            assert len(config.tables) == 1
            assert config.tables[0].source_uri == ""
            assert config.tables[0].target_uri == ""
        finally:
            Path(temp_file_path).unlink()

    def test_config_file_not_found(self):
        """Test error when config file doesn't exist."""
        with pytest.raises(FileNotFoundError, match="Configuration file not found"):
            Config.from_yaml_file("non_existent_file.yaml")

    def test_empty_yaml_content(self):
        """Test error when YAML content is empty."""
        with pytest.raises(ValueError, match="YAML content is empty"):
            Config.from_yaml_string("")

    def test_empty_tables_list(self):
        """Test error when tables list is empty."""
        yaml_content = """
tables: []
"""

        with pytest.raises(ValueError, match="At least one table configuration must be provided"):
            Config.from_yaml_string(yaml_content)

    def test_invalid_yaml_format(self):
        """Test error when YAML format is invalid."""
        invalid_yaml = """
tables:
  - source_uri: "clickhouse://admin:password@localhost:8123/default"
    source_table: "users"
    target_uri: "postgresql://user:password@localhost:5432/test_db"
    target_table: "users"
    primary_keys: ["id"]
    sync_mode: "incremental"
    sync_column: "created_at"
    batch_size: 1000
    number_of_workers: 2
    invalid_indentation
"""

        with pytest.raises(Exception):  # YAML parsing error
            Config.from_yaml_string(invalid_yaml)


class TestIntegrationWithSyphon:
    """Integration tests that verify config works with Syphon class."""

    def setup_method(self):
        """Set up test environment variables."""
        self.original_source_uri = os.environ.get("SOURCE_DATABASE_URI")
        self.original_target_uri = os.environ.get("TARGET_DATABASE_URI")

        # Set test environment variables
        os.environ["SOURCE_DATABASE_URI"] = "clickhouse://admin:admin@localhost:8123/default"
        os.environ["TARGET_DATABASE_URI"] = "postgresql://admin:admin@localhost:5432/postgres"

    def teardown_method(self):
        """Clean up test environment variables."""
        if self.original_source_uri is not None:
            os.environ["SOURCE_DATABASE_URI"] = self.original_source_uri
        elif "SOURCE_DATABASE_URI" in os.environ:
            del os.environ["SOURCE_DATABASE_URI"]

        if self.original_target_uri is not None:
            os.environ["TARGET_DATABASE_URI"] = self.original_target_uri
        elif "TARGET_DATABASE_URI" in os.environ:
            del os.environ["TARGET_DATABASE_URI"]

    def test_syphon_uri_resolution(self):
        """Test that Syphon correctly resolves URIs from environment variables."""
        from clickhouse_syphon.syphon import Syphon

        config = TableConfig(
            source_uri="",  # Use environment variable
            source_table="test_table",
            target_uri="",  # Use environment variable
            target_table="test_table",
            primary_keys=["id"],
            sync_mode="incremental",
            sync_column="created_at",
            batch_size=1000,
            number_of_workers=2,
        )

        # This should work without connection errors for URI resolution
        try:
            syphon = Syphon(config)
            assert syphon.source_uri == "clickhouse://admin:admin@localhost:8123/default"
            assert syphon.target_uri == "postgresql://admin:admin@localhost:5432/postgres"
        except Exception as e:
            # If there's a connection error, that's expected - we just want to test URI resolution
            if "connection" not in str(e).lower() and "connect" not in str(e).lower():
                raise e

    @patch("clickhouse_syphon.syphon.create_engine")
    def test_syphon_initialization_with_mocked_engines(self, mock_create_engine):
        """Test Syphon initialization with mocked database engines."""
        from clickhouse_syphon.syphon import Syphon

        # Mock the create_engine function to avoid actual database connections
        mock_create_engine.return_value = "mocked_engine"

        config = TableConfig(
            source_uri="",  # Use environment variable
            source_table="campagne",
            target_uri="",  # Use environment variable
            target_table="campagne",
            primary_keys=["id", "created_at"],
            sync_mode="incremental",
            sync_column="created_at",
            batch_size=100000,
            number_of_workers=4,
        )

        syphon = Syphon(config)

        # Verify that the resolved URIs are correct
        assert syphon.source_uri == "clickhouse://admin:admin@localhost:8123/default"
        assert syphon.target_uri == "postgresql://admin:admin@localhost:5432/postgres"

        # Verify that create_engine was called with the resolved URIs
        assert mock_create_engine.call_count == 2
        mock_create_engine.assert_any_call("clickhouse://admin:admin@localhost:8123/default")
        mock_create_engine.assert_any_call("postgresql://admin:admin@localhost:5432/postgres")
