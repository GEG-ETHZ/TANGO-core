"""Unit tests for addon system functionality.

These tests verify that addon initialization and core functionality work correctly
after the refactoring from dynamic to explicit imports.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from tango.addons.utils import resolve_addon_output_path


class TestAnalyzerAddon:
    """Tests for Analyzer addon CSV generation functionality."""

    def test_analyzer_csv_generation(self):
        """Test that Analyzer addon correctly generates CSV from results dict."""
        from tango.addons.Analyzer.Analyzer_interface import Analyzer_addon

        # Create mock graph and results
        mock_graph = {"main_graph": {}, "power_plant_graph": {}}
        mock_results = {
            "temperature": [100.0, 150.0, 200.0],
            "pressure": [1.0, 1.5, 2.0],
            "flow_rate": [50.0, 55.0, 60.0],
        }

        # Create addon instance
        addon = Analyzer_addon(mock_graph, mock_results)

        # Create a temporary file for output
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            temp_csv_path = f.name

        try:
            # Create mock specs with results_file
            mock_specs = MagicMock()
            mock_specs.results_file = temp_csv_path

            # Run post_process
            addon.post_process(mock_specs)

            # Verify file was created and has correct content
            assert os.path.exists(temp_csv_path)

            with open(temp_csv_path) as f:
                content = f.read()

            # Check headers
            assert "temperature" in content
            assert "pressure" in content
            assert "flow_rate" in content

            # Check data rows
            lines = content.strip().split("\n")
            assert len(lines) == 4  # 1 header + 3 data rows

        finally:
            # Cleanup
            if os.path.exists(temp_csv_path):
                os.unlink(temp_csv_path)

    def test_analyzer_keyword_replacement(self):
        """Test that keyword replacement works correctly."""
        from tango.addons.Analyzer.Analyzer_interface import Analyzer_addon

        mock_graph = {}
        mock_results = {}
        addon = Analyzer_addon(mock_graph, mock_results)

        # Test keyword replacement
        data = {"original_key1": [1, 2, 3], "other_key": [4, 5, 6]}
        replacements = {"original_key1": "new_key1"}

        result = addon.replace_keywords(data, replacements)

        assert "new_key1" in result
        assert "original_key1" not in result
        assert "other_key" in result
        assert result["new_key1"] == [1, 2, 3]


class TestThermaGraphAddon:
    """Tests for ThermaGraph addon initialization."""

    def test_thermagraph_initialization(self):
        """Test that ThermaGraph addon can be initialized with mock data."""
        from tango.addons.ThermaGraph.ThermaGraph_interface import ThermaGraph_addon

        mock_graph = {
            "main_graph": {
                "nodes": {"node1": {"type": "well"}},
                "edges": {},
            },
            "power_plant_graph": {},
        }
        mock_results = {}

        # Should not raise
        addon = ThermaGraph_addon(mock_graph, mock_results)
        assert addon is not None
        assert addon.graph == mock_graph


class TestExplicitImports:
    """Tests verifying that explicit imports work correctly."""

    def test_can_import_thermagraph(self):
        """Test that ThermaGraph addon can be explicitly imported."""
        from tango.addons.ThermaGraph.ThermaGraph_interface import ThermaGraph_addon

        assert ThermaGraph_addon is not None

    def test_can_import_analyzer(self):
        """Test that Analyzer addon can be explicitly imported."""
        from tango.addons.Analyzer.Analyzer_interface import Analyzer_addon

        assert Analyzer_addon is not None

    def test_can_import_specs(self):
        """Test that specs dataclasses can be imported from dataclasses.py."""
        from tango.units.dataclasses import CommonSpecs

        assert CommonSpecs is not None


class TestPathResolver:
    """Tests for the addon output path resolver utility."""

    def test_none_returns_default(self):
        """Test that None path returns output/default_filename."""
        result = resolve_addon_output_path(None, "states.json")
        assert result == Path("output/states.json")

    def test_empty_string_returns_default(self):
        """Test that empty string returns output/default_filename."""
        result = resolve_addon_output_path("", "states.json")
        assert result == Path("output/states.json")

    def test_relative_path_gets_output_prefix(self):
        """Test that relative path gets output/ prefix."""
        result = resolve_addon_output_path("my_states.json", "states.json")
        assert result == Path("output/my_states.json")

    def test_explicit_output_path_unchanged(self):
        """Test that output/... paths are returned as-is."""
        result = resolve_addon_output_path("output/custom.json", "states.json")
        assert result == Path("output/custom.json")

    def test_absolute_path_unchanged(self):
        """Test that absolute paths are returned as-is."""
        result = resolve_addon_output_path("/tmp/states.json", "states.json")
        assert result == Path("/tmp/states.json")

    def test_custom_output_dir(self):
        """Test that custom output_dir is used instead of default."""
        result = resolve_addon_output_path(
            "states.json",
            "default.json",
            "/custom/path",
        )
        assert result == Path("/custom/path/states.json")

    def test_path_object_input(self):
        """Test that Path objects work as input."""
        result = resolve_addon_output_path(Path("my_states.json"), "states.json")
        assert result == Path("output/my_states.json")
