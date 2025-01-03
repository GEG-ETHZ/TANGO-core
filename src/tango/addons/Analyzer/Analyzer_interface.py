from tango.addons.base import *
import subprocess
import os
import csv

class Analyzer_addon(TangoAddon):
    def __init__(self, graph, results):
        super().__init__(graph, results)

    def replace_keywords(self, data, replacements):
        """
        Replace keywords in the given data using the replacements dictionary.

        :param data: Dictionary containing the original keys and values.
        :param replacements: Dictionary with original keywords as keys and replacement keywords as values.
        :return: A new dictionary with replaced keywords.
        """
        updated_data = {}
        for key, value in data.items():
            # Replace the key using the replacements dictionary
            new_key = replacements.get(key, key)
            updated_data[new_key] = value
        return updated_data

    def post_process(self, specs):
        """
        Write the results into the specified results file in CSV format after replacing keywords.
        """
        self.results_file = specs.results_file

        # Define your replacements dictionary
        replacements = {
            "original_key1": "new_key1",
            "original_key2": "new_key2",
            # Add more replacements as needed
        }

        try:
            updated_results = self.replace_keywords(self.results, replacements)

            keys = list(updated_results.keys())
            rows = zip(*updated_results.values())

            with open(self.results_file, 'w', newline='') as cf:
                writer = csv.writer(cf)
                writer.writerow(keys)
                writer.writerows(rows)

            print(f"Results written to CSV file: {self.results_file}")
        except Exception as e:
            print(f"Error writing results to file: {e}")
            raise

    def execute(self):
        """
        Execute the add-on by launching the PyQt module with the generated files.
        """
        results_file = os.path.abspath(self.results_file)

        try:
            subprocess.run(
                ['python', '/Users/morteza/Documents/projects/TANGO/src/tango/addons/Analyzer/results_analysis.py', results_file],
                check=True
            )
        except subprocess.CalledProcessError as e:
            print(f"Error launching PyQt module: {e}")
            raise
