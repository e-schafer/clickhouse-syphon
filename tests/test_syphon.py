"""
Test module for Syphon class functionality.
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import Connection, Engine

from clickhouse_syphon.config import TableConfig
from clickhouse_syphon.syphon import Syphon


class TestSyphon:
    """Test class for Syphon functionality."""

    def setup_method(self) -> None:
        """Set up test environment variables and configuration."""
        self.original_source_uri = os.environ.get("SOURCE_DATABASE_URI")
        self.original_target_uri = os.environ.get("TARGET_DATABASE_URI")

        # Set test environment variables
        os.environ["SOURCE_DATABASE_URI"] = "clickhouse://admin:admin@localhost:8123/default"
        os.environ["TARGET_DATABASE_URI"] = "postgresql://admin:admin@localhost:5432/postgres"

        # Create a test configuration
        self.test_config = TableConfig(
            source_uri="",  # Use environment variables
            source_table="test_table",
            target_uri="",  # Use environment variables
            target_table="test_table_target",
            primary_keys=["id"],
            sync_mode="incremental",
            sync_column="created_at",
            batch_size=1000,
            number_of_workers=2,
        )

    def teardown_method(self) -> None:
        """Clean up test environment variables."""
        if self.original_source_uri is not None:
            os.environ["SOURCE_DATABASE_URI"] = self.original_source_uri
        elif "SOURCE_DATABASE_URI" in os.environ:
            del os.environ["SOURCE_DATABASE_URI"]

        if self.original_target_uri is not None:
            os.environ["TARGET_DATABASE_URI"] = self.original_target_uri
        elif "TARGET_DATABASE_URI" in os.environ:
            del os.environ["TARGET_DATABASE_URI"]

    @patch("clickhouse_syphon.syphon.create_engine")
    def test_syphon_initialization(self, mock_create_engine: MagicMock) -> None:
        """Test Syphon initialization with proper URI resolution."""
        mock_engine = MagicMock(spec=Engine)
        mock_create_engine.return_value = mock_engine

        syphon = Syphon(self.test_config)

        # Verify URI resolution
        assert syphon.source_uri == "clickhouse://admin:admin@localhost:8123/default"
        assert syphon.target_uri == "postgresql://admin:admin@localhost:5432/postgres"

        # Verify configuration attributes
        assert syphon.source_table == "test_table"
        assert syphon.target_table == "test_table_target"
        assert syphon.primary_keys == ["id"]
        assert syphon.sync_mode == "incremental"
        assert syphon.sync_column == "created_at"
        assert syphon.batch_size == 1000
        assert syphon.number_of_workers == 2

        # Verify engines were created
        assert mock_create_engine.call_count == 2
        mock_create_engine.assert_any_call("clickhouse://admin:admin@localhost:8123/default")
        mock_create_engine.assert_any_call("postgresql://admin:admin@localhost:5432/postgres")

    @patch("clickhouse_syphon.syphon.create_engine")
    def test_syphon_with_explicit_uris(self, mock_create_engine: MagicMock) -> None:
        """Test Syphon initialization with explicit URIs in config."""
        config = TableConfig(
            source_uri="clickhouse://explicit:password@source:8123/db",
            source_table="source_table",
            target_uri="postgresql://explicit:password@target:5432/db",
            target_table="target_table",
            primary_keys=["id", "uuid"],
            sync_mode="rewind",
            sync_column="updated_at",
            batch_size=5000,
            number_of_workers=4,
        )

        mock_engine = MagicMock(spec=Engine)
        mock_create_engine.return_value = mock_engine

        syphon = Syphon(config)

        # Verify explicit URIs are used
        assert syphon.source_uri == "clickhouse://explicit:password@source:8123/db"
        assert syphon.target_uri == "postgresql://explicit:password@target:5432/db"

        # Verify other configuration
        assert syphon.sync_mode == "rewind"
        assert syphon.batch_size == 5000
        assert syphon.number_of_workers == 4

    @patch("clickhouse_syphon.syphon.create_engine")
    def test_retrieve_checkpoint(self, mock_create_engine: MagicMock) -> None:
        """Test checkpoint retrieval functionality."""
        mock_engine = MagicMock(spec=Engine)
        mock_create_engine.return_value = mock_engine
        mock_connection = MagicMock(spec=Connection)

        # Mock SQLAlchemy execution pattern
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row.max_value = "2023-01-01 00:00:00"
        mock_result.fetchone.return_value = mock_row
        mock_connection.execute.return_value = mock_result

        syphon = Syphon(self.test_config)
        checkpoint = syphon.retrieve_checkpoint(mock_connection, "test_table", "created_at")

        assert checkpoint == "2023-01-01 00:00:00"
        mock_connection.execute.assert_called_once()

    @patch("clickhouse_syphon.syphon.create_engine")
    def test_retrieve_checkpoint_no_data(self, mock_create_engine: MagicMock) -> None:
        """Test checkpoint retrieval when no checkpoint exists."""
        mock_engine = MagicMock(spec=Engine)
        mock_create_engine.return_value = mock_engine
        mock_connection = MagicMock(spec=Connection)

        # Mock SQLAlchemy execution pattern with no results
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_connection.execute.return_value = mock_result

        syphon = Syphon(self.test_config)
        checkpoint = syphon.retrieve_checkpoint(mock_connection, "test_table", "created_at")

        assert checkpoint is None

    @patch("clickhouse_syphon.syphon.create_engine")
    def test_build_source_query_incremental_with_checkpoint(self, mock_create_engine: MagicMock) -> None:
        """Test source query building with incremental mode and checkpoint."""
        mock_engine = MagicMock(spec=Engine)
        mock_create_engine.return_value = mock_engine
        mock_connection = MagicMock(spec=Connection)

        syphon = Syphon(self.test_config)

        # Mock retrieve_checkpoint to return a value
        with patch.object(syphon, "retrieve_checkpoint", return_value="2023-01-01 00:00:00"):
            query = syphon.build_source_query("test_table", mock_connection)

        expected_query = "SELECT * FROM test_table WHERE created_at > '2023-01-01 00:00:00'"
        assert query == expected_query

    @patch("clickhouse_syphon.syphon.create_engine")
    def test_build_source_query_incremental_no_checkpoint(self, mock_create_engine: MagicMock) -> None:
        """Test source query building with incremental mode but no checkpoint."""
        mock_engine = MagicMock(spec=Engine)
        mock_create_engine.return_value = mock_engine
        mock_connection = MagicMock(spec=Connection)

        syphon = Syphon(self.test_config)

        # Mock retrieve_checkpoint to return None
        with patch.object(syphon, "retrieve_checkpoint", return_value=None):
            query = syphon.build_source_query("test_table", mock_connection)

        expected_query = "SELECT * FROM test_table"
        assert query == expected_query

    @patch("clickhouse_syphon.syphon.create_engine")
    def test_build_source_query_rewind_mode(self, mock_create_engine: MagicMock) -> None:
        """Test source query building with rewind mode."""
        config = TableConfig(
            source_uri="clickhouse://admin:admin@localhost:8123/default",
            source_table="test_table",
            target_uri="postgresql://admin:admin@localhost:5432/postgres",
            target_table="test_table_target",
            primary_keys=["id"],
            sync_mode="rewind",
            sync_column="created_at",
            batch_size=1000,
            number_of_workers=2,
        )

        mock_engine = MagicMock(spec=Engine)
        mock_create_engine.return_value = mock_engine
        mock_connection = MagicMock(spec=Connection)

        syphon = Syphon(config)

        with patch.object(syphon, "retrieve_checkpoint", return_value="2023-01-01 00:00:00"):
            query = syphon.build_source_query("test_table", mock_connection)

        expected_query = "SELECT * FROM test_table"
        assert query == expected_query

    @patch("clickhouse_syphon.syphon.create_engine")
    @patch("clickhouse_syphon.syphon.inspect")
    def test_truncate_staging_table_exists(self, mock_inspect: MagicMock, mock_create_engine: MagicMock) -> None:
        """Test truncating staging table when it exists."""
        mock_engine = MagicMock(spec=Engine)
        mock_create_engine.return_value = mock_engine
        mock_connection = MagicMock(spec=Connection)

        # Mock inspector to return that table exists
        mock_inspector = MagicMock()
        mock_inspector.has_table.return_value = True
        mock_inspect.return_value = mock_inspector

        syphon = Syphon(self.test_config)
        syphon.truncate_staging("test_staging", mock_connection)

        # Verify truncate was called
        mock_connection.execute.assert_called_once()
        mock_connection.commit.assert_called_once()

    @patch("clickhouse_syphon.syphon.create_engine")
    @patch("clickhouse_syphon.syphon.inspect")
    def test_truncate_staging_table_not_exists(self, mock_inspect: MagicMock, mock_create_engine: MagicMock) -> None:
        """Test truncating staging table when it doesn't exist."""
        mock_engine = MagicMock(spec=Engine)
        mock_create_engine.return_value = mock_engine
        mock_connection = MagicMock(spec=Connection)

        # Mock inspector to return that table doesn't exist
        mock_inspector = MagicMock()
        mock_inspector.has_table.return_value = False
        mock_inspect.return_value = mock_inspector

        syphon = Syphon(self.test_config)
        syphon.truncate_staging("test_staging", mock_connection)

        # Verify no truncate was attempted
        mock_connection.execute.assert_not_called()
        mock_connection.commit.assert_not_called()

    @patch("clickhouse_syphon.syphon.create_engine")
    @patch("clickhouse_syphon.syphon.pl.read_database")
    @patch("clickhouse_syphon.syphon.ThreadPoolExecutor")
    def test_copy_data_to_staging(
        self, mock_executor: MagicMock, mock_read_database: MagicMock, mock_create_engine: MagicMock
    ) -> None:
        """Test copying data to staging table with parallel processing."""
        mock_engine = MagicMock(spec=Engine)
        mock_create_engine.return_value = mock_engine

        # Create mock data
        mock_df1 = MagicMock()
        mock_df2 = MagicMock()
        # Mock the iterator returned by pl.read_database with iter_batches=True
        mock_read_database.return_value = [mock_df1, mock_df2]

        # Mock ThreadPoolExecutor
        mock_executor_instance = MagicMock()
        mock_executor.return_value.__enter__.return_value = mock_executor_instance

        # Mock futures
        mock_future1 = MagicMock()
        mock_future1.result.return_value = None
        mock_future2 = MagicMock()
        mock_future2.result.return_value = None

        mock_executor_instance.submit.side_effect = [mock_future1, mock_future2]

        syphon = Syphon(self.test_config)
        syphon.copy_data_to_staging(mock_engine, "SELECT * FROM test_table", mock_engine, "test_staging")

        # Verify ThreadPoolExecutor was used
        mock_executor.assert_called_once_with(max_workers=2)
        assert mock_executor_instance.submit.call_count == 2

    @patch("clickhouse_syphon.syphon.create_engine")
    @patch("polars.read_database")
    def test_merge_copy(self, mock_read_database: MagicMock, mock_create_engine: MagicMock) -> None:
        """Test merge copy functionality."""
        mock_engine = MagicMock(spec=Engine)
        mock_create_engine.return_value = mock_engine
        mock_connection = MagicMock(spec=Connection)

        # Mock schema reading
        mock_schema_df = MagicMock()
        mock_schema_df.columns = ["id", "name", "created_at"]
        mock_read_database.return_value = mock_schema_df

        syphon = Syphon(self.test_config)
        syphon.merge_copy(mock_connection, "test_staging", ["id"])

        # Verify execute was called (for the merge query)
        mock_connection.execute.assert_called()
        mock_connection.commit.assert_called()

    @patch("clickhouse_syphon.syphon.create_engine")
    def test_run_method_success(self, mock_create_engine: MagicMock) -> None:
        """Test successful run method execution."""
        mock_engine = MagicMock(spec=Engine)
        mock_create_engine.return_value = mock_engine

        syphon = Syphon(self.test_config)

        # Mock the copy method to return success
        with patch.object(syphon, "copy", return_value=0):
            result = syphon.run()

        assert result == 0

    @patch("clickhouse_syphon.syphon.create_engine")
    def test_run_method_failure(self, mock_create_engine: MagicMock) -> None:
        """Test run method handling failures."""
        mock_engine = MagicMock(spec=Engine)
        mock_create_engine.return_value = mock_engine

        syphon = Syphon(self.test_config)

        # Mock the copy method to raise an exception
        with patch.object(syphon, "copy", side_effect=Exception("Test error")) as mock_copy:
            result = syphon.run()

        # Verify copy was called and result is 1 (failure)
        mock_copy.assert_called_once()
        assert result == 1

    @patch("clickhouse_syphon.syphon.create_engine")
    def test_copy_method_full_flow(self, mock_create_engine: MagicMock) -> None:
        """Test the complete copy method flow."""
        mock_engine = MagicMock(spec=Engine)
        mock_create_engine.return_value = mock_engine

        # Mock engine connections
        mock_source_conn = MagicMock(spec=Connection)
        mock_target_conn = MagicMock(spec=Connection)

        mock_engine.connect.side_effect = [mock_target_conn, mock_source_conn]

        syphon = Syphon(self.test_config)

        # Mock all the methods called by copy
        with (
            patch.object(syphon, "build_source_query", return_value="SELECT * FROM test_table") as mock_build_query,
            patch.object(syphon, "truncate_staging") as mock_truncate,
            patch.object(syphon, "copy_data_to_staging") as mock_copy_staging,
            patch.object(syphon, "merge_copy") as mock_merge,
        ):
            result = syphon.copy()

        # Verify all methods were called
        mock_build_query.assert_called_once()
        mock_truncate.assert_called_once()
        mock_copy_staging.assert_called_once()
        mock_merge.assert_called_once()

        # Verify connections were closed
        mock_source_conn.close.assert_called_once()
        mock_target_conn.close.assert_called_once()

        assert result == 0


class TestSyphonErrorHandling:
    """Test class for Syphon error handling scenarios."""

    def setup_method(self) -> None:
        """Set up test environment variables."""
        self.original_source_uri = os.environ.get("SOURCE_DATABASE_URI")
        self.original_target_uri = os.environ.get("TARGET_DATABASE_URI")

        os.environ["SOURCE_DATABASE_URI"] = "clickhouse://admin:admin@localhost:8123/default"
        os.environ["TARGET_DATABASE_URI"] = "postgresql://admin:admin@localhost:5432/postgres"

    def teardown_method(self) -> None:
        """Clean up test environment variables."""
        if self.original_source_uri is not None:
            os.environ["SOURCE_DATABASE_URI"] = self.original_source_uri
        elif "SOURCE_DATABASE_URI" in os.environ:
            del os.environ["SOURCE_DATABASE_URI"]

        if self.original_target_uri is not None:
            os.environ["TARGET_DATABASE_URI"] = self.original_target_uri
        elif "TARGET_DATABASE_URI" in os.environ:
            del os.environ["TARGET_DATABASE_URI"]

    def test_syphon_with_invalid_environment_uris(self) -> None:
        """Test Syphon initialization with invalid environment URIs."""
        os.environ["SOURCE_DATABASE_URI"] = "invalid-uri"

        config = TableConfig(
            source_uri="",  # Will use invalid env var
            source_table="test_table",
            target_uri="postgresql://admin:admin@localhost:5432/postgres",
            target_table="test_table",
            primary_keys=["id"],
            sync_mode="incremental",
            sync_column="created_at",
            batch_size=1000,
            number_of_workers=2,
        )

        with pytest.raises(ValueError, match="must contain a valid protocol"):
            Syphon(config)

    @patch("clickhouse_syphon.syphon.create_engine")
    def test_copy_method_exception_handling(self, mock_create_engine: MagicMock) -> None:
        """Test copy method handles exceptions properly."""
        mock_engine = MagicMock(spec=Engine)
        mock_create_engine.return_value = mock_engine

        # Mock connection that raises an exception
        mock_engine.connect.side_effect = Exception("Connection failed")

        config = TableConfig(
            source_uri="clickhouse://admin:admin@localhost:8123/default",
            source_table="test_table",
            target_uri="postgresql://admin:admin@localhost:5432/postgres",
            target_table="test_table",
            primary_keys=["id"],
            sync_mode="incremental",
            sync_column="created_at",
            batch_size=1000,
            number_of_workers=2,
        )

        syphon = Syphon(config)
        result = syphon.copy()

        # Should return 1 (failure) when exception occurs
        assert result == 1


class TestSyphonIntegration:
    """Integration tests for Syphon with multiple components."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.original_source_uri = os.environ.get("SOURCE_DATABASE_URI")
        self.original_target_uri = os.environ.get("TARGET_DATABASE_URI")

        os.environ["SOURCE_DATABASE_URI"] = "clickhouse://admin:admin@localhost:8123/default"
        os.environ["TARGET_DATABASE_URI"] = "postgresql://admin:admin@localhost:5432/postgres"

    def teardown_method(self) -> None:
        """Clean up test environment."""
        if self.original_source_uri is not None:
            os.environ["SOURCE_DATABASE_URI"] = self.original_source_uri
        elif "SOURCE_DATABASE_URI" in os.environ:
            del os.environ["SOURCE_DATABASE_URI"]

        if self.original_target_uri is not None:
            os.environ["TARGET_DATABASE_URI"] = self.original_target_uri
        elif "TARGET_DATABASE_URI" in os.environ:
            del os.environ["TARGET_DATABASE_URI"]

    @patch("clickhouse_syphon.syphon.create_engine")
    def test_syphon_with_different_sync_modes(self, mock_create_engine: MagicMock) -> None:
        """Test Syphon behavior with different sync modes."""
        mock_engine = MagicMock(spec=Engine)
        mock_create_engine.return_value = mock_engine

        # Test incremental mode
        incremental_config = TableConfig(
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

        syphon_incremental = Syphon(incremental_config)
        assert syphon_incremental.sync_mode == "incremental"

        # Test rewind mode
        rewind_config = TableConfig(
            source_uri="",
            source_table="test_table",
            target_uri="",
            target_table="test_table",
            primary_keys=["id"],
            sync_mode="rewind",
            sync_column="updated_at",
            batch_size=2000,
            number_of_workers=4,
        )

        syphon_rewind = Syphon(rewind_config)
        assert syphon_rewind.sync_mode == "rewind"
        assert syphon_rewind.batch_size == 2000
        assert syphon_rewind.number_of_workers == 4

    @patch("clickhouse_syphon.syphon.create_engine")
    def test_syphon_with_multiple_primary_keys(self, mock_create_engine: MagicMock) -> None:
        """Test Syphon with multiple primary keys."""
        mock_engine = MagicMock(spec=Engine)
        mock_create_engine.return_value = mock_engine

        config = TableConfig(
            source_uri="",
            source_table="test_table",
            target_uri="",
            target_table="test_table",
            primary_keys=["id", "tenant_id", "created_at"],
            sync_mode="incremental",
            sync_column="updated_at",
            batch_size=5000,
            number_of_workers=8,
        )

        syphon = Syphon(config)
        assert syphon.primary_keys == ["id", "tenant_id", "created_at"]
        assert len(syphon.primary_keys) == 3
        assert syphon.primary_keys == ["id", "tenant_id", "created_at"]
        assert len(syphon.primary_keys) == 3
        assert len(syphon.primary_keys) == 3
