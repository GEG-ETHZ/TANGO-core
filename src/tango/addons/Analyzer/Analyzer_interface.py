from tango.addons.base import *
import subprocess
import os
import csv

class Analyzer_addon(TangoAddon):
    def __init__(self, graph, results):
        super().__init__(graph, results)

    def post_process(self, specs):
        """
        Write the results into the specified results file in CSV format.
        """
        self.results_file = specs.results_file

        try:
            # Extract keys and values from results
            keys = list(self.results.keys())
            rows = zip(*self.results.values())

            # Write the results to the specified CSV file
            with open(self.results_file, 'w', newline='') as cf:
                writer = csv.writer(cf)
                writer.writerow(keys)  # Write header row
                writer.writerows(rows)  # Write data rows

            print(f"Results written to CSV file: {self.results_file}")
        except Exception as e:
            print(f"Error writing results to file: {e}")
            raise

    def execute(self):
        """
        Execute the add-on by launching the PyQt module with the generated files.
        """
        results_file = os.path.abspath(self.results_file)  # Get the absolute path of the results file

        try:
            subprocess.run(
                ['python', '/Users/morteza/Documents/projects/TANGO/src/tango/addons/Analyzer/results_analysis.py', results_file],
                check=True
            )
        except subprocess.CalledProcessError as e:
            print(f"Error launching PyQt module: {e}")
            raise
