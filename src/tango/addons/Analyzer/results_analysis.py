import os
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class SimulationAnalyzerSeaborn:
    def __init__(self, results):
        """Initialize the analyzer with simulation results.

        Args:
            results (dict): Simulation results dictionary.

        """
        self.df = self._convert_to_dataframe(results)

    def _convert_to_dataframe(self, results):
        """Converts the results dictionary into a Pandas DataFrame.

        Args:
            results (dict): Simulation results dictionary.

        Returns:
            pd.DataFrame: Converted DataFrame with 'date' as a column.

        """
        df = pd.DataFrame(results)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])

        return df

    def launch_interactive_ui(self):
        """Launch a PyQt5-based interactive UI for plotting and analysis."""
        app = QApplication(sys.argv)
        window = InteractiveAnalyzerUI(self)
        window.show()
        sys.exit(app.exec_())

    def basic_statistics(self, output_file=None):
        """Compute and print basic statistics for numeric columns.

        Args:
            output_file (str): File path to save the statistics. If None, does not save.

        Returns:
            pd.DataFrame: Summary statistics for numeric data.

        """
        stats = self.df.describe()
        if output_file:
            stats.to_csv(output_file)
            print(f"Statistics saved to {output_file}")

        return stats

    def correlation_heatmap(self, variables=None):
        """Generate a heatmap for correlation between numeric variables.

        Args:
            variables (list): List of variable names to include in the heatmap.

        """
        if variables is None:
            variables = self.df.select_dtypes(include=["float64", "int64"]).columns
        numeric_df = self.df[variables]

        plt.figure(figsize=(12, 8))
        sns.heatmap(numeric_df.corr(), annot=True, cmap="coolwarm", fmt=".2f")
        plt.title("Correlation Heatmap")
        sns.set_theme(style="ticks", palette="pastel")
        plt.show()

    def pairplot(self, variables=None, hue=None):
        """Generate a pairplot for relationships between variables.

        Args:
            variables (list): List of variable names to include.
            hue (str): Column name for color-coding.

        """
        if variables is None:
            variables = self.df.select_dtypes(include=["float64", "int64"]).columns

        if hue and hue not in self.df.columns:
            print(f"Warning: Hue '{hue}' not found in the DataFrame.")
            hue = None

        sns.pairplot(self.df, vars=variables, hue=hue, diag_kind="kde", height=2.5)
        plt.suptitle("Pairplot of Selected Variables", y=1.02)
        plt.show()

    def distribution_plot(self, keys, color="green", linewidth=2):
        """Plot the Kernel Density Estimation (KDE) of selected variables in the same figure.

        Args:
            keys (list): The variables to analyze.
            color (str): Color of the KDE curve.
            linewidth (int): Line thickness of the KDE curve.

        """
        sns.set_theme(style="whitegrid", palette="deep")
        if not isinstance(keys, list):
            keys = [keys]

        plt.figure(figsize=(10, 6))

        for key in keys:
            if key in self.df.columns:
                data = self.df[key].dropna()
                sns.kdeplot(data, label=key, linewidth=linewidth)

        plt.title("KDE of Selected Variables", fontsize=16)
        plt.xlabel("Value", fontsize=14)
        plt.ylabel("Density", fontsize=14)
        plt.grid(True)
        plt.legend(title="Parameters")
        plt.show()

    def boxplot_parameters(self, keys=None):
        """Create a boxplot for one or more numerical parameters.

        Args:
            keys (list): List of parameters to plot as boxplots. If None, defaults to all numeric columns.

        """
        numeric_columns = self.df.select_dtypes(include=["float64", "int64"]).columns

        if keys is None:
            keys = numeric_columns
        else:
            missing_keys = [key for key in keys if key not in numeric_columns]
            if missing_keys:
                print(f"Warning: The following keys are not numeric or don't exist: {missing_keys}")
                keys = [key for key in keys if key in numeric_columns]

        if not keys:
            print("No valid numeric keys to plot.")
            return

        data_to_plot = self.df[keys]
        plt.figure(figsize=(12, 8))
        sns.set_theme(style="whitegrid")
        sns.boxplot(
            data=data_to_plot,
            linewidth=1.5,
            palette="pastel",
            boxprops={"edgecolor": "black", "facecolor": "white"},
            whiskerprops={"color": "black"},
            capprops={"color": "black"},
            medianprops={"color": "red", "linewidth": 2},
        )
        plt.title("Boxplot of Selected Parameters", fontsize=16, weight="bold")
        plt.xlabel("Parameters", fontsize=14)
        plt.ylabel("Values", fontsize=14)
        plt.grid(True, linestyle="--", alpha=0.7)
        plt.xticks(rotation=45, fontsize=12)
        plt.yticks(fontsize=12)
        plt.show()

    def plot_over_time(self, keys, title="Parameter(s) Over Time", save_path=None):
        """Plot selected parameters over time.

        Args:
            keys (list): List of parameters to plot.
            title (str): Title of the plot.
            save_path (str): Path to save the plot as an image. If None, does not save.

        """
        missing_keys = [key for key in keys if key not in self.df.columns]

        if missing_keys:
            print(f"Warning: The following keys are not in the DataFrame: {missing_keys}")
            keys = [key for key in keys if key in self.df.columns]

        if not keys:
            print("No valid keys to plot.")
            return

        sns.set_theme(style="whitegrid", palette="deep")
        plt.figure(figsize=(12, 6))

        for key in keys:
            plt.plot(self.df["date"], self.df[key], marker="o", label=key)

        plt.title(title, fontsize=16)
        plt.xlabel("Time", fontsize=14)
        plt.ylabel("Value", fontsize=14)
        plt.grid(True)
        plt.legend(title="Parameters", fontsize=12)

        if save_path:
            plt.savefig(save_path, dpi=300)
            print(f"Plot saved to {save_path}")

        plt.show()

    def cumulative_distribution_plot(self, keys, color="blue", linewidth=2):
        """Plot the Cumulative Distribution Function (CDF) for selected parameters in the same figure.

        Args:
            keys (list): The variables to analyze.
            color (str): Base color for the CDF lines (colors will vary for each key).
            linewidth (int): Line thickness of the CDF lines.

        """
        if not isinstance(keys, list):
            keys = [keys]

        plt.figure(figsize=(10, 6))
        colors = sns.color_palette("husl", len(keys))
        sns.set_theme(style="whitegrid", palette="deep")

        for i, key in enumerate(keys):
            if key in self.df.columns:
                data = self.df[key].dropna()
                sorted_data = np.sort(data)
                cumulative = np.arange(1, len(sorted_data) + 1) / len(sorted_data)
                plt.plot(sorted_data, cumulative, color=colors[i], linewidth=linewidth, label=key)

        plt.title("Cumulative Distribution Function (CDF) of Selected Variables", fontsize=16)
        plt.xlabel("Value", fontsize=14)
        plt.ylabel("Cumulative Probability", fontsize=14)
        plt.grid(True)
        plt.legend(title="Parameters")
        plt.show()

    def regression_plot(self, x, y, hue=None):
        """Create a regression plot to analyze trends between two variables.

        Args:
            x (str): Independent variable.
            y (str): Dependent variable.
            hue (str): Variable for color grouping.

        """
        sns.set_theme(style="whitegrid", palette="deep")

        if x in self.df.columns and y in self.df.columns:
            sns.lmplot(data=self.df, x=x, y=y, hue=hue, height=6, aspect=1.5)
            plt.title(f"Regression Plot of {y} vs {x}")
            plt.grid(True)
            plt.show()
        else:
            print(f"Columns '{x}' or '{y}' not found in the results.")

    def detect_outliers(self, key):
        """Detect outliers in the specified parameter using the IQR method.

        Args:
            key (str): The parameter to analyze for outliers.

        Returns:
            list: List of outlier values.

        """
        if key in self.df.columns:
            data = self.df[key].dropna()
            Q1 = np.percentile(data, 25)
            Q3 = np.percentile(data, 75)
            IQR = Q3 - Q1
            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR
            outliers = data[(data < lower_bound) | (data > upper_bound)]
            print(f"Outliers detected in '{key}':\n{outliers.tolist()}")
            return outliers.tolist()
        else:
            print(f"Key '{key}' not found in the results.")
            return []

    def histogram_with_kde(self, key, bins=30, color="purple", alpha=0.6):
        """Plot a histogram with a KDE curve overlay for a selected parameter.

        Args:
            key (str): The variable to analyze.
            bins (int): Number of bins for the histogram.
            color (str): Color of the histogram and KDE curve.
            alpha (float): Transparency of the histogram bars.

        """
        if key in self.df.columns:
            plt.figure(figsize=(10, 6))
            sns.histplot(self.df[key].dropna(), bins=bins, kde=True, color=color, alpha=alpha)

            plt.title(f"Histogram with KDE of {key}", fontsize=16)
            plt.xlabel(key, fontsize=14)
            plt.ylabel("Frequency", fontsize=14)
            plt.grid(True)
            plt.show()
        else:
            print(f"Key '{key}' not found in the results.")

    def rolling_mean_plot(self, key, window=3):
        """Plot the rolling mean (moving average) for a selected parameter.

        Args:
            key (str): The parameter to analyze.
            window (int): The size of the moving average window.

        """
        sns.set_theme(style="whitegrid", palette="deep")

        if "date" in self.df.columns and key in self.df.columns:
            data = self.df[["date", key]].dropna()
            data["rolling_mean"] = data[key].rolling(window=window).mean()

            plt.figure(figsize=(12, 6))
            plt.plot(data["date"], data[key], label=key, marker="o", linestyle="--", alpha=0.5)
            plt.plot(
                data["date"],
                data["rolling_mean"],
                label=f"Rolling Mean (window={window})",
                color="red",
                linewidth=2,
            )

            plt.title(f"Rolling Mean of {key} (Window = {window})", fontsize=16)
            plt.xlabel("Time", fontsize=14)
            plt.ylabel("Value", fontsize=14)
            plt.legend()
            plt.grid(True)
            plt.show()
        else:
            print(f"Key '{key}' not found or 'date' column is missing in the results.")

    def violin_plot(self, keys=None):
        """Create violin plots for selected numerical parameters.

        Args:
            keys (list): List of parameters to plot. If None, plots all numeric columns.

        """
        numeric_columns = self.df.select_dtypes(include=["float64", "int64"]).columns

        if keys is None:
            keys = numeric_columns
        else:
            keys = [key for key in keys if key in numeric_columns]

        if not keys:
            print("No valid numeric keys to plot.")
            return

        sns.set_theme(style="whitegrid", palette="deep")
        plt.figure(figsize=(12, 8))
        sns.violinplot(data=self.df[keys])
        plt.title("Violin Plot of Selected Parameters", fontsize=16)
        plt.xlabel("Parameters", fontsize=14)
        plt.ylabel("Values", fontsize=14)
        plt.grid(True)
        plt.xticks(rotation=45)
        plt.show()

    def generate_summary_report(self, output_file=None):
        """Generate a summary report of the DataFrame, including statistics, correlations, and missing values.

        Args:
            output_file (str): File path to save the report. If None, prints the report.

        """
        report = []
        report.append("### Basic Statistics ###")
        report.append(str(self.df.describe()))
        report.append("\n### Correlation Matrix ###")
        report.append(str(self.df.corr()))
        report.append("\n### Missing Values ###")
        report.append(str(self.df.isnull().sum()))

        full_report = "\n".join(report)

        if output_file:
            with open(output_file, "w") as f:
                f.write(full_report)
            print(f"Summary report saved to {output_file}")
        else:
            print(full_report)


class InteractiveAnalyzerUI(QMainWindow):
    """A GUI application for interactively visualizing and analyzing data using various plot types.
    The application is built using PyQt5 and leverages an analyzer object to perform data analysis.

    Attributes:
        analyzer (SimulationAnalyzerSeaborn): The data analysis engine used to generate plots.
        file_path (str): The path of the currently selected data file.
        main_widget (QWidget): The central widget for the application.
        layout (QVBoxLayout): The main layout of the application.
        file_path_label (QLabel): Label displaying the currently selected file.
        file_select_button (QPushButton): Button to open a file selection dialog.
        plot_type_combo (QComboBox): Dropdown for selecting the plot type.
        dynamic_controls (QVBoxLayout): Layout for input fields dynamically updated based on the selected plot type.
        plot_button (QPushButton): Button to trigger plot generation.

    Args:
        analyzer (SimulationAnalyzerSeaborn): An optional analysis engine instance. Defaults to a new SimulationAnalyzerSeaborn object with empty configuration.
        preselected_file (str, optional): Path to a preselected data file. Defaults to None.

    """

    def __init__(self, analyzer, preselected_file=None):
        """Initialize the InteractiveAnalyzerUI.

        Args:
            analyzer (SimulationAnalyzerSeaborn): The data analysis engine.
            preselected_file (str, optional): The path to a preselected data file. Defaults to None.

        """
        super().__init__()
        self.analyzer = analyzer if analyzer else SimulationAnalyzerSeaborn({})
        self.file_path = preselected_file
        self.setWindowTitle("Interactive Analyzer")
        self.main_widget = QWidget()
        self.setCentralWidget(self.main_widget)
        self.layout = QVBoxLayout()
        self.main_widget.setLayout(self.layout)
        self.create_controls()

        if self.file_path:
            self.file_path_label.setText(self.file_path)
            self.load_file(self.file_path)

    def create_controls(self):
        """Create the GUI controls for the application, including file selector, plot type dropdown,
        and dynamic input fields.
        """
        controls_layout = QVBoxLayout()
        file_selector_layout = QHBoxLayout()
        self.file_path_label = QLabel("No file selected")
        self.file_select_button = QPushButton("Select File")
        self.file_select_button.clicked.connect(self.select_file)
        file_selector_layout.addWidget(self.file_path_label)
        file_selector_layout.addWidget(self.file_select_button)
        controls_layout.addLayout(file_selector_layout)
        self.plot_type_combo = QComboBox()
        self.plot_type_combo.addItems(
            [
                "Correlation Heatmap",
                "Pairplot",
                "Boxplot Parameters",
                "Distribution Plot",
                "Plot Over Time",
                "Cumulative Distribution Plot",
                "Regression Plot",
                "Detect Outliers",
                "Histogram with KDE",
                "Rolling Mean Plot",
                "Violin Plot",
            ],
        )
        controls_layout.addWidget(QLabel("Select Plot Type:"))
        controls_layout.addWidget(self.plot_type_combo)
        self.dynamic_controls = QVBoxLayout()
        controls_layout.addLayout(self.dynamic_controls)
        self.plot_button = QPushButton("Generate Plot")
        self.plot_button.clicked.connect(self.generate_plot)
        controls_layout.addWidget(self.plot_button)
        self.layout.addLayout(controls_layout)
        self.plot_type_combo.currentTextChanged.connect(self.update_dynamic_controls)
        self.update_dynamic_controls()

    def select_file(self):
        """Open a file dialog to allow the user to select a CSV file. The selected file is loaded
        and displayed in the application.
        """
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(
            self,
            "Select Data File",
            "",
            "CSV Files (*.csv);;All Files (*)",
        )
        if file_path:
            self.load_file(file_path)

    def load_file(self, file_path):
        """Load data from the specified file and update the analyzer's data.

        Args:
            file_path (str): The path to the data file.

        """
        self.file_path = file_path
        self.file_path_label.setText(self.file_path)
        data = pd.read_csv(self.file_path)
        self.analyzer.df = self.analyzer._convert_to_dataframe(data.to_dict(orient="list"))
        print(f"Loaded data from {self.file_path}")

    def update_dynamic_controls(self):
        """Dynamically update the input fields based on the selected plot type.

        This method clears the current dynamic controls and adds new ones based on the
        requirements of the selected plot type. Supported plot types determine the input
        fields such as variables, keys, hue, and window size.
        """
        while self.dynamic_controls.count():
            child = self.dynamic_controls.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        plot_type = self.plot_type_combo.currentText()

        self.inputs = {}

        if plot_type in ["Correlation Heatmap", "Pairplot", "Boxplot Parameters", "Violin Plot"]:
            self.inputs["variables"] = QLineEdit()
            self.dynamic_controls.addWidget(QLabel("Variables (comma-separated, optional):"))
            self.dynamic_controls.addWidget(self.inputs["variables"])

        if plot_type in [
            "Distribution Plot",
            "Cumulative Distribution Plot",
            "Detect Outliers",
            "Histogram with KDE",
        ]:
            self.inputs["key"] = QLineEdit()
            self.dynamic_controls.addWidget(QLabel("Key (required):"))
            self.dynamic_controls.addWidget(self.inputs["key"])

        if plot_type == "Regression Plot":
            self.inputs["variables"] = QLineEdit()
            self.dynamic_controls.addWidget(QLabel("Variables (independent, dependent):"))
            self.dynamic_controls.addWidget(self.inputs["variables"])
            self.inputs["additional"] = QLineEdit()
            self.dynamic_controls.addWidget(QLabel("Hue (optional):"))
            self.dynamic_controls.addWidget(self.inputs["additional"])

        if plot_type == "Rolling Mean Plot":
            self.inputs["key"] = QLineEdit()
            self.dynamic_controls.addWidget(QLabel("Key (required):"))
            self.dynamic_controls.addWidget(self.inputs["key"])
            self.inputs["window"] = QLineEdit()
            self.dynamic_controls.addWidget(QLabel("Window size (integer):"))
            self.dynamic_controls.addWidget(self.inputs["window"])

        if plot_type == "Plot Over Time":
            self.inputs["variables"] = QLineEdit()
            self.dynamic_controls.addWidget(QLabel("Variables (comma-separated, required):"))
            self.dynamic_controls.addWidget(self.inputs["variables"])

    def generate_plot(self):
        """Generate a plot based on the selected plot type and input parameters.

        This method retrieves the user inputs, validates them, and triggers the corresponding
        plot generation function from the analyzer. Handles errors and ensures appropriate
        user feedback in case of missing or invalid inputs.

        Attributes:
            plot_type (str): The selected plot type from the dropdown.
            variables (list): List of variables specified by the user.
            key (str): Key used for certain plots.
            additional_param (str): Optional additional parameter (e.g., hue).
            window (int): Window size for rolling mean plots.

        Raises:
            Exception: Captures and prints any errors encountered during plot generation.

        """
        if not self.file_path:
            print("Please select a file before generating plots.")
            return

        plot_type = self.plot_type_combo.currentText()
        variables = []
        key = None
        additional_param = None
        window = None

        if "variables" in self.inputs and self.inputs["variables"].text():
            variables = [v.strip() for v in self.inputs["variables"].text().split(",") if v.strip()]
        if "key" in self.inputs and self.inputs["key"].text():
            key = self.inputs["key"].text().strip()
            variables = [v.strip() for v in key.split(",") if v.strip()]
        if "additional" in self.inputs and self.inputs["additional"].text():
            additional_param = self.inputs["additional"].text().strip()
        if "window" in self.inputs and self.inputs["window"].text():
            window = self.inputs["window"].text().strip()

        try:
            if plot_type == "Correlation Heatmap":
                self.analyzer.correlation_heatmap(variables if variables else None)
            elif plot_type == "Pairplot":
                self.analyzer.pairplot(variables if variables else None, hue=additional_param)
            elif plot_type == "Boxplot Parameters":
                self.analyzer.boxplot_parameters(variables if variables else None)
            elif plot_type == "Distribution Plot":
                if variables:
                    self.analyzer.distribution_plot(variables)
                else:
                    print("Please specify at least one key for the distribution plot.")
            elif plot_type == "Plot Over Time":
                if variables:
                    self.analyzer.plot_over_time(variables)
                else:
                    print("Please specify at least one key for the plot over time.")
            elif plot_type == "Cumulative Distribution Plot":
                if variables:
                    self.analyzer.cumulative_distribution_plot(variables)
                else:
                    print("Please specify at least one key for the cumulative distribution plot.")
            elif plot_type == "Regression Plot":
                if len(variables) >= 2:
                    self.analyzer.regression_plot(variables[0], variables[1], hue=additional_param)
                else:
                    print("Please specify at least two variables for the regression plot.")
            elif plot_type == "Detect Outliers":
                if key:
                    self.analyzer.detect_outliers(key)
                else:
                    print("Please specify a key for outlier detection.")
            elif plot_type == "Histogram with KDE":
                if variables:
                    self.analyzer.histogram_with_kde(variables[0])
                else:
                    print("Please specify a key for the histogram with KDE.")
            elif plot_type == "Rolling Mean Plot":
                if key and window and window.isdigit():
                    self.analyzer.rolling_mean_plot(key, window=int(window))
                else:
                    print("Please specify a key and a numeric window for the rolling mean plot.")
            elif plot_type == "Violin Plot":
                self.analyzer.violin_plot(variables if variables else None)
            else:
                print("Invalid plot type selected.")
        except Exception as e:
            print(f"An error occurred while generating the plot: {e}")


if __name__ == "__main__":
    if len(sys.argv) == 2:
        results_file = sys.argv[1]

        if not os.path.exists(results_file):
            print("Error: Specified results file does not exist.")
            sys.exit(1)

        data = pd.read_csv(results_file)
        analyzer = SimulationAnalyzerSeaborn(data.to_dict(orient="list"))
        app = QApplication(sys.argv)
        window = InteractiveAnalyzerUI(analyzer, preselected_file=results_file)
        window.show()
        sys.exit(app.exec_())

    else:
        print("No results file provided. Running standalone.")
        app = QApplication(sys.argv)
        app.setStyle("Macintosh")
        analyzer = SimulationAnalyzerSeaborn({})
        window = InteractiveAnalyzerUI(analyzer)
        window.show()
        sys.exit(app.exec_())
