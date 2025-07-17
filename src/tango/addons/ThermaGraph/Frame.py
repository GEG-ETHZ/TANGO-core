import sys
import os
import json
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget, QLineEdit, QLabel, QPushButton,
    QHBoxLayout, QComboBox, QFormLayout, QGroupBox, QFileDialog, QMessageBox, QCheckBox
)
import numpy as np
from Plotter import FluidDiagramPlotter, MplCanvas
from PyQt5.QtCore import Qt, QTimer


class MainWindow(QMainWindow):
    """
    Main application window for the Interactive Fluid Diagram Plotter.
    """
    def __init__(self, default_fluid='CO2'):
        super(MainWindow, self).__init__()
        self.default_fluid = default_fluid
        self.setWindowTitle('Interactive Fluid Diagram Plot')
        self.setGeometry(200, 200, 1200, 1000)
        self.initUI()
        self.connect_signals()
        self.show()
        self.update_default_isoline_values()
        self.previous_units = self.get_unit_system()

    def initUI(self):
        """
        Initialize the User Interface components and layout.
        """
        self.canvas = MplCanvas(self, width=6, height=10, dpi=100)
        self.create_input_fields()
        self.create_layouts()
        self.create_file_input_section()
        self.create_download_section()
        self.setCentralWidget(self.main_widget)

    def show_error_message(self, message):
        """
        Display an error message in a QMessageBox.
        """
        error_dialog = QMessageBox(self)
        error_dialog.setIcon(QMessageBox.Critical)
        error_dialog.setWindowTitle('Error')
        error_dialog.setText(message)
        error_dialog.exec_()

    def create_input_fields(self):
        """
        Create and set up the input fields for fluid, diagram settings, and isoline settings.
        """
        self.fluid_input = self.create_line_edit(self.default_fluid, 'Enter the fluid name (e.g., CO2 for carbon dioxide)')
        self.unit_system_p = self.create_combo_box(['bar', 'hPa', 'mbar', 'psi', 'kPa', 'Pa', 'MPa'], 'Select the pressure unit')
        self.unit_system_T = self.create_combo_box(['°C', 'K', '°F'], 'Select the temperature unit')
        self.unit_system_s = self.create_combo_box(['J/kgK', 'kJ/kgK', 'MJ/kgK'], 'Select the entropy unit')
        self.unit_system_h = self.create_combo_box(['kJ/kg', 'J/kg', 'MJ/kg'], 'Select the enthalpy unit')
        self.unit_system_v = self.create_combo_box(['m^3/kg', 'l/kg'], 'Select the specific volume unit')
        self.unit_system_Q = self.create_combo_box(['-', '%'], 'Select the vapor fraction unit')

        self.diagram_type_input = self.create_combo_box(['logph', 'hs', 'Ts', 'Th', 'plogv'], 'Select the type of diagram to plot')
        self.xmin_input = self.create_line_edit('0.01', 'Enter the minimum value for the x-axis')
        self.xmax_input = self.create_line_edit('700', 'Enter the maximum value for the x-axis')
        self.ymin_input = self.create_line_edit('10', 'Enter the minimum value for the y-axis')
        self.ymax_input = self.create_line_edit('1000', 'Enter the maximum value for the y-axis')

        self.q_start_input, self.q_end_input, self.q_points_input, self.q_color_input, self.q_style_input, self.q_linewidth_input = \
            self.create_isoline_input_fields('0', '1', '2', 'blue', '-', '2.5')
        self.t_start_input, self.t_end_input, self.t_points_input, self.t_color_input, self.t_style_input, self.t_linewidth_input = \
            self.create_isoline_input_fields('25', '375', '0', 'red', '-', '1.0')
        self.p_start_input, self.p_end_input, self.p_points_input, self.p_color_input, self.p_style_input, self.p_linewidth_input = \
            self.create_isoline_input_fields('0.01', '1000', '0', 'green', '-.', '1.0')
        self.v_start_input, self.v_end_input, self.v_points_input, self.v_color_input, self.v_style_input, self.v_linewidth_input = \
            self.create_isoline_input_fields('0.001', '10', '0', 'orange', ':', '1.0')
        self.s_start_input, self.s_end_input, self.s_points_input, self.s_color_input, self.s_style_input, self.s_linewidth_input = \
            self.create_isoline_input_fields('1000', '10000', '0', 'purple', '-', '1.0')
        self.h_start_input, self.h_end_input, self.h_points_input, self.h_color_input, self.h_style_input, self.h_linewidth_input = \
            self.create_isoline_input_fields('0', '3600', '0', 'brown', '--', '1.0')

        self.auto_update_checkbox = QCheckBox('Automatic Update', self)
        self.auto_update_checkbox.setToolTip('Automatically update the plot after changes')

    def create_isoline_input_fields(self, start, end, points, color, style, linewidth='1.0'):
        """
        Helper function to create input fields for isoline settings.

        :param start: Default start value.
        :param end: Default end value.
        :param points: Default number of points.
        :param color: Default color.
        :param style: Default line style.
        :param linewidth: Default line width.
        :return: A tuple of created QLineEdit and QComboBox widgets.
        """
        start_input = self.create_line_edit(start)
        end_input = self.create_line_edit(end)
        points_input = self.create_line_edit(points)
        color_input = self.create_combo_box(['blue', 'red', 'green', 'orange', 'purple', 'brown'])
        style_input = self.create_combo_box(['-', '--', '-.', ':'])
        linewidth_input = self.create_line_edit(linewidth)
        return start_input, end_input, points_input, color_input, style_input, linewidth_input

    def create_layouts(self):
        """
        Set up and arrange the layout for the main window.
        """
        fluid_group = self.create_group_box('Fluid and Units', self.create_fluid_layout())
        diagram_group = self.create_group_box('Diagram Settings', self.create_diagram_layout())
        isoline_group = self.create_group_box('Isoline Settings', self.create_isoline_layout())

        self.main_widget = QWidget()
        main_layout = QVBoxLayout(self.main_widget)
        main_layout.addWidget(self.canvas)

        settings_layout = QHBoxLayout()
        settings_layout.addWidget(fluid_group)
        settings_layout.addWidget(diagram_group)
        settings_layout.addWidget(isoline_group)

        main_layout.addLayout(settings_layout)
        self.main_layout = main_layout
        auto_update_layout = QHBoxLayout()
        auto_update_layout.addWidget(self.auto_update_checkbox)
        main_layout.addLayout(auto_update_layout)

    def create_file_input_section(self):
        """
        Create the input fields and buttons for selecting input files.
        """
        self.fluid_states_input = self.create_line_edit('', 'Select fluid states file', placeholder=True)
        self.fluid_states_button = self.create_button('Browse', self.select_fluid_states_file)
        self.connections_input = self.create_line_edit('', 'Select connections file', placeholder=True)
        self.connections_button = self.create_button('Browse', self.select_connections_file)
        self.update_button = self.create_button('Update Plot', self.update_plot)

        file_layout = QHBoxLayout()
        file_layout.addWidget(QLabel('Fluid States:'))
        file_layout.addWidget(self.fluid_states_input)
        file_layout.addWidget(self.fluid_states_button)
        file_layout.addWidget(QLabel('Connections:'))
        file_layout.addWidget(self.connections_input)
        file_layout.addWidget(self.connections_button)
        file_layout.addWidget(self.update_button)

        self.main_layout.addLayout(file_layout)

    def create_download_section(self):
        """
        Create the input fields and buttons for downloading the plot.
        """
        self.format_input = self.create_combo_box(['png', 'svg'], 'Select the file format for download')
        self.resolution_input = self.create_line_edit('', 'Enter resolution (dpi)', placeholder=True)
        download_button = self.create_button('Download Plot', self.download_plot)

        download_layout = QHBoxLayout()
        download_layout.addWidget(QLabel('File Format:'))
        download_layout.addWidget(self.format_input)
        download_layout.addWidget(QLabel('Resolution (dpi):'))
        download_layout.addWidget(self.resolution_input)
        download_layout.addWidget(download_button)

        self.main_layout.addLayout(download_layout)

    def create_group_box(self, title, layout):
        """
        Create a QGroupBox with the given layout.

        :param title: Title of the group box.
        :param layout: Layout to set in the group box.
        :return: Configured QGroupBox.
        """
        group_box = QGroupBox(title)
        group_box.setLayout(layout)

        return group_box

    def create_fluid_layout(self):
        """
        Create layout for fluid and unit settings.
        """
        layout = QFormLayout()
        layout.addRow('Fluid:', self.fluid_input)
        layout.addRow('Pressure Unit:', self.unit_system_p)
        layout.addRow('Temperature Unit:', self.unit_system_T)
        layout.addRow('Entropy Unit:', self.unit_system_s)
        layout.addRow('Enthalpy Unit:', self.unit_system_h)
        layout.addRow('Volume Unit:', self.unit_system_v)
        layout.addRow('Vapor Fraction Unit:', self.unit_system_Q)

        return layout

    def create_diagram_layout(self):
        """
        Create layout for diagram settings.
        """
        layout = QFormLayout()
        layout.addRow('Diagram Type:', self.diagram_type_input)
        layout.addRow('X Min:', self.xmin_input)
        layout.addRow('X Max:', self.xmax_input)
        layout.addRow('Y Min:', self.ymin_input)
        layout.addRow('Y Max:', self.ymax_input)

        return layout

    def create_isoline_layout(self):
        """
        Create layout for isoline settings.
        """
        layout = QVBoxLayout()

        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel('Isoline'))
        header_layout.addWidget(QLabel('Start'))
        header_layout.addWidget(QLabel('End'))
        header_layout.addWidget(QLabel('Points'))
        header_layout.addWidget(QLabel('Color'))
        header_layout.addWidget(QLabel('Style'))
        header_layout.addWidget(QLabel('Linewidth'))

        for i in range(header_layout.count()):
            widget = header_layout.itemAt(i).widget()
            widget.setAlignment(Qt.AlignCenter)
            widget.setFixedWidth(100)

        layout.addLayout(header_layout)

        layout.addLayout(self.create_isoline_row('Vapor Fraction (Q):', self.q_start_input, self.q_end_input, self.q_points_input, self.q_color_input, self.q_style_input, self.q_linewidth_input))
        layout.addLayout(self.create_isoline_row('Temperature (T):', self.t_start_input, self.t_end_input, self.t_points_input, self.t_color_input, self.t_style_input, self.t_linewidth_input))
        layout.addLayout(self.create_isoline_row('Pressure (P):', self.p_start_input, self.p_end_input, self.p_points_input, self.p_color_input, self.p_style_input, self.p_linewidth_input))
        layout.addLayout(self.create_isoline_row('Specific Volume (V):', self.v_start_input, self.v_end_input, self.v_points_input, self.v_color_input, self.v_style_input, self.v_linewidth_input))
        layout.addLayout(self.create_isoline_row('Entropy (S):', self.s_start_input, self.s_end_input, self.s_points_input, self.s_color_input, self.s_style_input, self.s_linewidth_input))
        layout.addLayout(self.create_isoline_row('Enthalpy (H):', self.h_start_input, self.h_end_input, self.h_points_input, self.h_color_input, self.h_style_input, self.h_linewidth_input))

        return layout

    def create_isoline_row(self, label, start_input, end_input, points_input, color_input, style_input, linewidth_input):
        """
        Helper function to create a row of isoline settings.
        """
        row_layout = QHBoxLayout()
        label_widget = QLabel(label)
        label_widget.setFixedWidth(150)
        row_layout.addWidget(label_widget)
        row_layout.addWidget(start_input)
        row_layout.addWidget(end_input)
        row_layout.addWidget(points_input)
        row_layout.addWidget(color_input)
        row_layout.addWidget(style_input)
        row_layout.addWidget(linewidth_input)

        for i in range(row_layout.count()):
            widget = row_layout.itemAt(i).widget()
            widget.setFixedWidth(100)

        return row_layout

    def create_line_edit(self, default_text='', tooltip='', placeholder=False):
        """
        Create a QLineEdit with the given default text and tooltip.
        """
        line_edit = QLineEdit(self)

        if placeholder:
            line_edit.setPlaceholderText(default_text)
        else:
            line_edit.setText(default_text)
        line_edit.setToolTip(tooltip)

        return line_edit

    def create_combo_box(self, items, tooltip=''):
        """
        Create a QComboBox with the given items and tooltip.
        """
        combo_box = QComboBox(self)
        combo_box.addItems(items)
        combo_box.setToolTip(tooltip)

        return combo_box

    def create_button(self, text, callback):
        """
        Create a QPushButton with the given text and callback.
        """
        button = QPushButton(text, self)
        button.clicked.connect(callback)

        return button

    def connect_signals(self):
        """
        Connect signals to track changes in input fields and update the plot.
        """
        line_edit_widgets = [
            self.fluid_input, self.xmin_input, self.xmax_input, self.ymin_input, self.ymax_input,
            self.q_start_input, self.q_end_input, self.q_points_input,
            self.t_start_input, self.t_end_input, self.t_points_input,
            self.p_start_input, self.p_end_input, self.p_points_input,
            self.v_start_input, self.v_end_input, self.v_points_input,
            self.s_start_input, self.s_end_input, self.s_points_input,
            self.h_start_input, self.h_end_input, self.h_points_input,
            self.fluid_states_input,
            self.connections_input
        ]

        for widget in line_edit_widgets:
            widget.textChanged.connect(self.mark_update_needed)

        combo_box_widgets = [
            self.unit_system_p, self.unit_system_T, self.unit_system_s,
            self.unit_system_h, self.unit_system_v, self.unit_system_Q,
            self.diagram_type_input,
            self.q_color_input, self.q_style_input,
            self.t_color_input, self.t_style_input,
            self.p_color_input, self.p_style_input,
            self.v_color_input, self.v_style_input,
            self.s_color_input, self.s_style_input,
            self.h_color_input, self.h_style_input
        ]

        for widget in combo_box_widgets:
            widget.currentIndexChanged.connect(self.mark_update_needed)

        self.fluid_input.textChanged.connect(self.update_default_isoline_values)
        self.diagram_type_input.currentIndexChanged.connect(self.update_default_isoline_values)
        self.unit_system_p.currentIndexChanged.connect(self.convert_units)
        self.unit_system_T.currentIndexChanged.connect(self.convert_units)
        self.unit_system_s.currentIndexChanged.connect(self.convert_units)
        self.unit_system_h.currentIndexChanged.connect(self.convert_units)
        self.unit_system_v.currentIndexChanged.connect(self.convert_units)

    def convert_units(self):
        """
        Convert units for isoline values and diagram axis limits.
        """
        current_units = self.get_unit_system()
        self.convert_field(self.t_start_input, self.t_end_input, self.previous_units['T'], current_units['T'], 'T')
        self.convert_field(self.p_start_input, self.p_end_input, self.previous_units['p'], current_units['p'], 'p')
        self.convert_field(self.s_start_input, self.s_end_input, self.previous_units['s'], current_units['s'], 's')
        self.convert_field(self.h_start_input, self.h_end_input, self.previous_units['h'], current_units['h'], 'h')
        self.convert_field(self.v_start_input, self.v_end_input, self.previous_units['v'], current_units['v'], 'v')
        self.convert_diagram_axis_limits(self.previous_units, current_units)
        self.previous_units = current_units

    def convert_field(self, start_input, end_input, old_unit, new_unit, field_type):
        """
        Convert start and end values for a specific isoline field based on unit changes.
        """
        if not start_input.text().strip() or not end_input.text().strip():
            return

        start_value = float(start_input.text())
        end_value = float(end_input.text())

        if field_type == 'T':
            start_value = self.convert_temperature(start_value, old_unit, new_unit)
            end_value = self.convert_temperature(end_value, old_unit, new_unit)
        elif field_type == 'p':
            start_value = self.convert_pressure(start_value, old_unit, new_unit)
            end_value = self.convert_pressure(end_value, old_unit, new_unit)
        elif field_type == 's':
            start_value = self.convert_entropy(start_value, old_unit, new_unit)
            end_value = self.convert_entropy(end_value, old_unit, new_unit)
        elif field_type == 'h':
            start_value = self.convert_enthalpy(start_value, old_unit, new_unit)
            end_value = self.convert_enthalpy(end_value, old_unit, new_unit)
        elif field_type == 'v':
            start_value = self.convert_volume(start_value, old_unit, new_unit)
            end_value = self.convert_volume(end_value, old_unit, new_unit)

        start_input.setText(str(start_value))
        end_input.setText(str(end_value))

    def convert_diagram_axis_limits(self, old_units, new_units):
        """
        Convert the axis limits for the diagram based on unit changes.
        """
        if not self.xmin_input.text().strip() or not self.xmax_input.text().strip() or not self.ymin_input.text().strip() or not self.ymax_input.text().strip():
            return

        diagram_type = self.diagram_type_input.currentText()
        x_old_unit, y_old_unit = self.get_axis_units(diagram_type, old_units)
        x_unit, y_unit = self.get_axis_units(diagram_type, new_units)

        x_min = self.convert_value(float(self.xmin_input.text()), x_old_unit, x_unit, diagram_type, axis='x')
        x_max = self.convert_value(float(self.xmax_input.text()), x_old_unit, x_unit, diagram_type, axis='x')
        y_min = self.convert_value(float(self.ymin_input.text()), y_old_unit, y_unit, diagram_type, axis='y')
        y_max = self.convert_value(float(self.ymax_input.text()), y_old_unit, y_unit, diagram_type, axis='y')

        self.xmin_input.setText(str(x_min))
        self.xmax_input.setText(str(x_max))
        self.ymin_input.setText(str(y_min))
        self.ymax_input.setText(str(y_max))

    def get_axis_units(self, diagram_type, units):
        """
        Get the units of the x and y axes based on the diagram type.
        """
        if diagram_type == 'Ts':
            return units['s'], units['T']
        elif diagram_type == 'hs':
            return units['s'], units['h']
        elif diagram_type == 'logph':
            return units['h'], units['p']
        elif diagram_type == 'Th':
            return units['h'], units['T']
        elif diagram_type == 'plogv':
            return units['v'], units['p']

        return None, None

    def convert_value(self, value, old_unit, new_unit, diagram_type, axis):
        """
        Convert the axis value based on the units of the diagram type.
        """
        if old_unit == new_unit:
            return value
        if diagram_type in ['Ts', 'Th']:
            if axis == 'x':
                return self.convert_entropy(value, old_unit, new_unit)
            elif axis == 'y':
                return self.convert_temperature(value, old_unit, new_unit)
        elif diagram_type in ['hs', 'logph']:
            if axis == 'x':
                return self.convert_enthalpy(value, old_unit, new_unit)
            elif axis == 'y':
                return self.convert_pressure(value, old_unit, new_unit)
        elif diagram_type == 'plogv':
            if axis == 'x':
                return self.convert_volume(value, old_unit, new_unit)
            elif axis == 'y':
                return self.convert_pressure(value, old_unit, new_unit)

        return value

    def convert_temperature(self, value, old_unit, new_unit):
        """
        Convert temperature between different units.
        """
        if old_unit == new_unit:
            return value
        if old_unit == 'K':
            if new_unit == '°C':
                return value - 273.15
            elif new_unit == '°F':
                return (value - 273.15) * 9/5 + 32
        elif old_unit == '°C':
            if new_unit == 'K':
                return value + 273.15
            elif new_unit == '°F':
                return value * 9/5 + 32
        elif old_unit == '°F':
            if new_unit == 'K':
                return (value - 32) * 5/9 + 273.15
            elif new_unit == '°C':
                return (value - 32) * 5/9

        return value

    def convert_pressure(self, value, old_unit, new_unit):
        """
        Convert pressure between different units.
        """
        conversion_factors = {
            'Pa': 1, 'hPa': 100, 'kPa': 1000, 'mbar': 100, 'bar': 100000, 'psi': 6894.76, 'MPa': 1e6
        }

        return value * conversion_factors[old_unit] / conversion_factors[new_unit]

    def convert_entropy(self, value, old_unit, new_unit):
        """
        Convert entropy between different units.
        """
        conversion_factors = {
            'J/kgK': 1, 'kJ/kgK': 1000, 'MJ/kgK': 1e6
        }

        return value * conversion_factors[old_unit] / conversion_factors[new_unit]

    def convert_enthalpy(self, value, old_unit, new_unit):
        """
        Convert enthalpy between different units.
        """
        conversion_factors = {
            'J/kg': 1, 'kJ/kg': 1000, 'MJ/kg': 1e6
        }

        return value * conversion_factors[old_unit] / conversion_factors[new_unit]

    def convert_volume(self, value, old_unit, new_unit):
        """
        Convert specific volume between different units.
        """
        conversion_factors = {
            'm^3/kg': 1, 'l/kg': 0.001
        }

        return value * conversion_factors[old_unit] / conversion_factors[new_unit]

    def update_default_isoline_values(self):
        """
        Set default isoline values based on the selected fluid and diagram type.
        """
        fluid = self.fluid_input.text()

        if fluid == 'H2O':
            self.set_isoline_defaults(h_start='0', h_end='3500', p_start='0.01', p_end='10000', s_start='100', s_end='9000', t_start='40', t_end='400', v_start='0.01', v_end='100', q_start='0', q_end='1')
        elif fluid == 'CO2':
            self.set_isoline_defaults(h_start='0', h_end='700', p_start='20', p_end='1020', s_start='700', s_end='2100', t_start='10', t_end='310', v_start='0.001', v_end='0.02', q_start='0', q_end='1')

        diagram_type = self.diagram_type_input.currentText()
        self.update_axis_limits(diagram_type)
        self.mark_update_needed()

    def set_isoline_defaults(self, h_start, h_end, p_start, p_end, s_start, s_end, t_start, t_end, v_start, v_end, q_start, q_end):
        """
        Helper function to set default values for isoline settings.
        """
        self.h_start_input.setText(h_start)
        self.h_end_input.setText(h_end)
        self.p_start_input.setText(p_start)
        self.p_end_input.setText(p_end)
        self.s_start_input.setText(s_start)
        self.s_end_input.setText(s_end)
        self.t_start_input.setText(t_start)
        self.t_end_input.setText(t_end)
        self.v_start_input.setText(v_start)
        self.v_end_input.setText(v_end)
        self.q_start_input.setText(q_start)
        self.q_end_input.setText(q_end)

    def update_axis_limits(self, diagram_type):
        """
        Update the axis limits based on the selected diagram type.
        """
        if diagram_type == 'Ts':
            self.xmin_input.setText(self.s_start_input.text())
            self.xmax_input.setText(self.s_end_input.text())
            self.ymin_input.setText(self.t_start_input.text())
            self.ymax_input.setText(self.t_end_input.text())
        elif diagram_type == 'hs':
            self.xmin_input.setText(self.s_start_input.text())
            self.xmax_input.setText(self.s_end_input.text())
            self.ymin_input.setText(self.h_start_input.text())
            self.ymax_input.setText(self.h_end_input.text())
        elif diagram_type == 'logph':
            self.xmin_input.setText(self.h_start_input.text())
            self.xmax_input.setText(self.h_end_input.text())
            self.ymin_input.setText(self.p_start_input.text())
            self.ymax_input.setText(self.p_end_input.text())
        elif diagram_type == 'Th':
            self.xmin_input.setText(self.h_start_input.text())
            self.xmax_input.setText(self.h_end_input.text())
            self.ymin_input.setText(self.t_start_input.text())
            self.ymax_input.setText(self.t_end_input.text())
        elif diagram_type == 'plogv':
            self.xmin_input.setText(self.v_start_input.text())
            self.xmax_input.setText(self.v_end_input.text())
            self.ymin_input.setText(self.p_start_input.text())
            self.ymax_input.setText(self.p_end_input.text())

    def mark_update_needed(self):
        """
        Mark the update button as needing to be pressed by changing its color.
        """
        self.update_button.setStyleSheet("background-color: red; color: white;")

        if self.auto_update_checkbox.isChecked():
            QTimer.singleShot(2000, self.auto_update_plot)

    def auto_update_plot(self):
        """
        Automatically update the plot if the checkbox is checked.
        """
        self.update_plot()

    def update_plot(self):
        """
        Update the plot based on the user-defined parameters.
        """
        try:
            self.load_json_files()
            fluid = self.fluid_input.text()
            unit_system = self.get_unit_system()
            diagram_type = self.diagram_type_input.currentText()
            xmin, xmax, ymin, ymax = self.get_axis_limits()
            isoline_settings = self.get_isoline_settings()
            isoline_styles = self.get_isoline_styles()
            self.canvas.figure.clear()
            self.canvas.axes = self.canvas.figure.add_subplot(111)
            self.plotter = FluidDiagramPlotter(
                self.canvas.figure, self.canvas.axes, fluid_states=self.fluid_states,
                fluid=fluid, unit_system=unit_system, diagram_type=diagram_type,
                x_min=xmin, x_max=xmax, y_min=ymin, y_max=ymax, isoline_settings=isoline_settings,
                isoline_styles=isoline_styles
            )
            self.plotter.create_plot(self.connections)
            self.canvas.draw()
            self.update_button.setStyleSheet("")
        except ValueError as e:
            self.show_error_message(f"Error: {str(e)}")
        except Exception as e:
            self.show_error_message(f"Unexpected Error: {str(e)}")

    def load_json_files(self):
        """
        Load the JSON files for fluid states and connections based on user input.
        """
        try:
            if self.fluid_states_input.text():
                self.fluid_states = self.load_json_file(self.fluid_states_input.text())
            else:
                raise ValueError("Please select a fluid states JSON file.")

            if self.connections_input.text():
                self.connections = self.load_json_file(self.connections_input.text())
            else:
                raise ValueError("Please select a connections JSON file.")
        except Exception as e:
            self.show_error_message(f"Error loading JSON files: {str(e)}")

    def get_unit_system(self):
        """
        Retrieve the selected unit system from the input fields.
        """
        return {
            'p': self.unit_system_p.currentText(),
            'T': self.unit_system_T.currentText(),
            's': self.unit_system_s.currentText(),
            'h': self.unit_system_h.currentText(),
            'v': self.unit_system_v.currentText(),
            'Q': self.unit_system_Q.currentText()
        }

    def get_axis_limits(self):
        """
        Retrieve the axis limits from the input fields.
        """
        return (float(self.xmin_input.text()), float(self.xmax_input.text()), float(self.ymin_input.text()), float(self.ymax_input.text()))

    def get_isoline_settings(self):
        """
        Retrieve the isoline settings from the input fields.
        """
        return {
            'Q': {'values': np.linspace(float(self.q_start_input.text()), float(self.q_end_input.text()), int(self.q_points_input.text()))},
            'T': {'values': np.linspace(float(self.t_start_input.text()), float(self.t_end_input.text()), int(self.t_points_input.text()))},
            'p': {'values': np.geomspace(float(self.p_start_input.text()), float(self.p_end_input.text()), int(self.p_points_input.text()))},
            'v': {'values': np.geomspace(float(self.v_start_input.text()), float(self.v_end_input.text()), int(self.v_points_input.text()))},
            's': {'values': np.linspace(float(self.s_start_input.text()), float(self.s_end_input.text()), int(self.s_points_input.text()))},
            'h': {'values': np.linspace(float(self.h_start_input.text()), float(self.h_end_input.text()), int(self.h_points_input.text()))}
        }

    def get_isoline_styles(self):
        """
        Retrieve the isoline styles from the input fields.
        """
        return {
            'Q': {'color': self.q_color_input.currentText(), 'linestyle': self.q_style_input.currentText(), 'linewidth': float(self.q_linewidth_input.text())},
            'T': {'color': self.t_color_input.currentText(), 'linestyle': self.t_style_input.currentText(), 'linewidth': float(self.t_linewidth_input.text())},
            'p': {'color': self.p_color_input.currentText(), 'linestyle': self.p_style_input.currentText(), 'linewidth': float(self.p_linewidth_input.text())},
            'v': {'color': self.v_color_input.currentText(), 'linestyle': self.v_style_input.currentText(), 'linewidth': float(self.v_linewidth_input.text())},
            's': {'color': self.s_color_input.currentText(), 'linestyle': self.s_style_input.currentText(), 'linewidth': float(self.s_linewidth_input.text())},
            'h': {'color': self.h_color_input.currentText(), 'linestyle': self.h_style_input.currentText(), 'linewidth': float(self.h_linewidth_input.text())}
        }

    def download_plot(self):
        """
        Save the plot to a file in the selected format and resolution.
        """
        file_format = self.format_input.currentText()
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Plot", "", f"{file_format.upper()} Files (*.{file_format});;All Files (*)", options=options)

        if file_path:
            try:
                dpi = int(self.resolution_input.text())
            except ValueError:
                dpi = 100

            self.canvas.figure.savefig(file_path, format=file_format, dpi=dpi)

    def load_json_file(self, file_path):
        """
        Load a JSON file and return its content.
        """
        with open(file_path, 'r') as file:
            return json.load(file)

    def select_fluid_states_file(self):
        """
        Open a file dialog to select a fluid states JSON file.
        """
        file_name, _ = QFileDialog.getOpenFileName(self, "Open Fluid States File", "", "JSON Files (*.json);;All Files (*)")
        if file_name:
            self.fluid_states_input.setText(file_name)
            self.fluid_states = self.load_json_file(file_name)

    def select_connections_file(self):
        """
        Open a file dialog to select a connections JSON file.
        """
        file_name, _ = QFileDialog.getOpenFileName(self, "Open Connections File", "", "JSON Files (*.json);;All Files (*)")
        if file_name:
            self.connections_input.setText(file_name)
            self.connections = self.load_json_file(file_name)

    def load_files(self, components_file=None, connections_file=None):
        """
        Load the given JSON files into the application.
        """
        if components_file:
            self.fluid_states_input.setText(components_file)
            self.fluid_states = self.load_json_file(components_file)

        if connections_file:
            self.connections_input.setText(connections_file)
            self.connections = self.load_json_file(connections_file)

        self.update_plot()


if __name__ == '__main__':
    import sys
    if len(sys.argv) == 6:
        components_file = sys.argv[1]
        connections_file = sys.argv[2]
        default_fluid = sys.argv[3]
        auto_save_svg = sys.argv[4]
        svg_filename = sys.argv[5]
        app = QApplication(sys.argv)
        window = MainWindow(default_fluid=default_fluid)
        window.load_files(components_file, connections_file)
        if auto_save_svg == 'yes' and svg_filename:
            try:
                window.canvas.figure.savefig(svg_filename, format='svg')
                print(f"SVG successfully saved to: {svg_filename}")
            except Exception as e:
                print(f"Error saving SVG: {e}")
            sys.exit(0)
        else:
            sys.exit(app.exec_())
    elif len(sys.argv) == 4:
        components_file = sys.argv[1]
        connections_file = sys.argv[2]
        default_fluid = sys.argv[3]
        app = QApplication(sys.argv)
        window = MainWindow(default_fluid=default_fluid)
        window.load_files(components_file, connections_file)
        sys.exit(app.exec_())
    elif len(sys.argv) == 3:
        components_file = sys.argv[1]
        connections_file = sys.argv[2]
        app = QApplication(sys.argv)
        window = MainWindow()
        window.load_files(components_file, connections_file)
        sys.exit(app.exec_())
    else:
        app = QApplication(sys.argv)
        window = MainWindow()
        sys.exit(app.exec_())
