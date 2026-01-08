"""Analyzer addon for TANGO simulation results.

This addon provides two main functions:
1. post_process(): Exports simulation results to CSV format
2. execute(): Launches an interactive PyQt5 data analysis UI

IMPORTANT DESIGN NOTES:
- This addon is for LOCAL/CLI use only - it is NOT used by tango-app frontend
- The tango-app frontend gets its data from ArangoDB, not CSV files
- The execute() method opens an interactive UI - it requires a display
  (no headless/batch mode support, unlike ThermaGraph)
"""

from tango.addons.base import TangoAddon
import os
import csv


class Analyzer_addon(TangoAddon):
    """Addon for analyzing and visualizing simulation results.

    This addon exports results to CSV and provides an interactive PyQt5
    visualization tool for exploring the data.

    NOT used by tango-app frontend - purely a CLI/local tool.

    Attributes:
        graph: The merged graph structure from the simulation
        results: Dictionary of simulation results (keyed by variable name)
        results_file: Path to output CSV file (set during post_process)
    """

    def __init__(self, graph, results):
        super().__init__(graph, results)

    def replace_keywords(self, data, replacements):
        """Replace keywords in the results dictionary.

        Args:
            data: Dictionary containing the original keys and values.
            replacements: Dictionary mapping original keys to new keys.

        Returns:
            A new dictionary with replaced keywords.
        """
        updated_data = {}
        for key, value in data.items():
            new_key = replacements.get(key, key)
            updated_data[new_key] = value
        return updated_data

    def post_process(self, specs):
        """Export simulation results to CSV file.

        This is called after each simulation timestep when the addon is active.
        The CSV file can be used for offline analysis or as input to the
        interactive viewer launched by execute().

        Args:
            specs: AnalyzerSpecs dataclass with configuration including results_file path
        """
        self.results_file = specs.results_file

        # Define replacements for renaming columns (customize as needed)
        replacements = {
            "original_key1": "new_key1",
            "original_key2": "new_key2",
        }

        try:
            updated_results = self.replace_keywords(self.results, replacements)
            keys = list(updated_results.keys())
            rows = zip(*updated_results.values())

            with open(self.results_file, "w", newline="") as cf:
                writer = csv.writer(cf)
                writer.writerow(keys)
                writer.writerows(rows)

            print(f"Results written to CSV file: {self.results_file}")
        except Exception as e:
            print(f"Error writing results to file: {e}")
            raise

    def execute(self):
        """Launch the interactive PyQt5 data analysis UI.

        This opens a visual interface for exploring simulation results with
        various plot types (correlation heatmaps, regression plots, etc.).

        NOTES:
        - Requires a display (will not work on headless servers)
        - Imports PyQt5 dependencies at runtime to avoid loading them
          when only CSV export is needed
        - Uses direct module import rather than subprocess for cleaner
          code and better error handling
        - This is for LOCAL use only - tango-app gets data from ArangoDB
        """
        import pandas as pd
        from tango.addons.Analyzer.results_analysis import (
            SimulationAnalyzerSeaborn,
            InteractiveAnalyzerUI,
        )
        from PyQt5.QtWidgets import QApplication
        import sys

        results_file = os.path.abspath(self.results_file)

        if not os.path.exists(results_file):
            print(f"Error: Results file does not exist: {results_file}")
            return

        # Load CSV and create analyzer instance
        data = pd.read_csv(results_file)
        analyzer = SimulationAnalyzerSeaborn(data.to_dict(orient="list"))

        # Launch interactive UI
        app = QApplication(sys.argv)
        window = InteractiveAnalyzerUI(analyzer, preselected_file=results_file)
        window.show()
        app.exec_()
