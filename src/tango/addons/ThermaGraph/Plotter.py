from CoolProp.CoolProp import PropsSI
from fluprodia import FluidPropertyDiagram
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable
import numpy as np
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt


plt.style.use('seaborn-v0_8-whitegrid')

class FluidDiagramPlotter:
    """
    Class responsible for plotting fluid diagrams based on given states, fluid, and diagram type.

    Attributes:
        fig (matplotlib.figure.Figure): The figure object where the plot will be drawn.
        ax (matplotlib.axes.Axes): The axes object where the plot will be drawn.
        fluid (str): The fluid name (e.g., 'H2O', 'CO2').
        unit_system (dict): The unit system for various properties like pressure, temperature, etc.
        diagram_type (str): The type of diagram to plot (e.g., 'Ts', 'hs', 'logph').
        x_min (float): The minimum value for the x-axis.
        x_max (float): The maximum value for the x-axis.
        y_min (float): The minimum value for the y-axis.
        y_max (float): The maximum value for the y-axis.
        isoline_settings (dict): Settings for the isolines (e.g., values for Q, T, p, etc.).
        isoline_styles (dict): Styles for the isolines (e.g., color, linestyle).
        diagram (FluidPropertyDiagram): An instance of FluidPropertyDiagram for plotting the diagram.
        label_fontsize (int): Font size for the labels on the isolines.
    """
    def __init__(self, fig, ax, fluid_states, fluid='H2O', unit_system=None,
                 diagram_type='Ts', x_min=0.01, x_max=10000, y_min=0.01, y_max=1000,
                 isoline_settings=None, isoline_styles=None, label_fontsize=8):
        self.fig = fig
        self.ax = ax
        self.fluid = fluid
        self.unit_system = unit_system or self.default_unit_system()
        self.diagram_type = diagram_type
        self.x_min = x_min
        self.x_max = x_max
        self.y_min = y_min
        self.y_max = y_max
        self.isoline_settings = isoline_settings or self.default_isoline_settings()
        self.isoline_styles = isoline_styles or self.default_isoline_styles()
        self.states = self.convert_states(fluid_states, diagram_type)
        self.diagram = FluidPropertyDiagram(fluid=self.fluid)
        self.diagram.set_unit_system(**self.unit_system)
        self.diagram.set_isolines(**{k: v['values'] for k, v in self.isoline_settings.items()})
        self.diagram.calc_isolines()
        self.cbar = None
        self.label_fontsize = label_fontsize

    @staticmethod
    def default_unit_system():
        """
        Return the default unit system for the fluid properties.
        """
        return {
            'p': 'Pa',
            'T': '°C',
            's': 'J/kgK',
            'h': 'J/kg',
            'v': 'm^3/kg',
            'Q': '-'
        }

    @staticmethod
    def default_isoline_settings():
        """
        Return the default isoline settings.
        """
        return {
            'Q': {'values': np.linspace(0, 1, 2)},
            'T': {'values': np.arange(25, 376, 25)},
            'p': {'values': np.geomspace(0.01, 1000, 6)},
            'v': {'values': np.geomspace(0.001, 10, 5)},
            's': {'values': np.linspace(1000, 10000, 5)},
            'h': {'values': np.linspace(0, 3600, 19)}
        }

    @staticmethod
    def default_isoline_styles():
        """
        Return the default styles for the isolines.
        """
        return {
            'Q': {'color': 'blue', 'linestyle': '--', 'linewidth': 2.5},
            'T': {'color': 'red', 'linestyle': '-', 'linewidth': 2.5},
            'p': {'color': 'green', 'linestyle': '-.', 'linewidth': 2.5},
            'v': {'color': 'orange', 'linestyle': ':', 'linewidth': 2.5},
            's': {'color': 'purple', 'linestyle': '-', 'linewidth': 2.5},
            'h': {'color': 'brown', 'linestyle': '--', 'linewidth': 2.5}
        }

    @staticmethod
    def bar_to_Pa(p_bar):
        """
        Convert pressure from bar to Pascal.

        :param p_bar: Pressure in bar.
        :return: Pressure in Pascal.
        """
        return p_bar * 1e5

    def plot_fluid_states(self, states, connections=None, markersize=6, fontsize=10, cmap='Greys'):
        """
        Plot the fluid states on the diagram with numeric labels for the last point of each state,
        excluding the point labeled 'inlet'. Numbers for overlapping points will be stacked vertically.
        """
        label_mapping = {}  # To store numeric labels and their corresponding state names
        coordinate_labels = {}  # To store labels for each coordinate
        counter = 1  # Numeric label counter

        for point_name, point_states in states.items():
            if point_name == "inlet":
                continue

            norm = Normalize(vmin=0, vmax=len(point_states) - 1)
            scalar_map = ScalarMappable(norm=norm, cmap=cmap)
            colors = [scalar_map.to_rgba(i) for i in range(len(point_states))]

            for i, (p, h) in enumerate(point_states):
                color = colors[i]
                coord = (round(h, 2), round(p, 2))
                self.ax.plot(h, p, marker='o', color=color, markersize=markersize)

                if coord not in coordinate_labels:
                    coordinate_labels[coord] = []

                if i == len(point_states) - 1:
                    coordinate_labels[coord].append(str(counter))
                    label_mapping[counter] = point_name
                    counter += 1

        for (h, p), labels in coordinate_labels.items():
            label_text = "\n".join(labels)  # Stack labels vertically
            self.ax.text(h - 30, p, label_text, fontsize=fontsize, color='red', ha='right', va='center')

        if connections:
            self.plot_connections(states, connections)

        # Generate label list on the right side
        self.add_label_list(label_mapping)

    def add_label_list(self, label_mapping):
        """
        Create a label list on the right side of the plot showing numeric labels and corresponding state names,
        excluding the point labeled 'inlet'.
        """
        self.ax.set_position([0.1, 0.1, 0.7, 0.8])
        x_pos = 1.25
        y_pos = 0.95
        y_step = 0.05

        for num, point_name in label_mapping.items():
            if point_name == "inlet":
                continue
            self.ax.text(x_pos, y_pos, f"{num}: {point_name}", transform=self.ax.transAxes, fontsize=10, ha='left')
            y_pos -= y_step


    def plot_connections(self, states, connections):
        """
        Plot the connections between fluid states.

        :param states: Dictionary of fluid states.
        :param connections: List of connections between states.
        """
        line_styles = self.connection_line_styles()

        for start, end, line_type in connections:
            # Prefer exact key match; fallback to substring match for backward compatibility
            def get_last_state(point_name: str):
                if point_name in states:
                    lst = states[point_name]
                    return lst[-1] if lst else None
                # fallback: substring match
                for key, seq in states.items():
                    if point_name in key and seq:
                        return seq[-1]
                return None

            start_state = get_last_state(start)
            end_state = get_last_state(end)
            if start_state is None or end_state is None:
                continue
            style = line_styles.get(line_type, line_styles['default'])
            self.ax.plot([start_state[1], end_state[1]], [start_state[0], end_state[0]], **style)

    @staticmethod
    def connection_line_styles():
        """
        Return the line styles for different connection types.
        """
        return {
            'non-isentropic': {'color': 'gray', 'linestyle': '-', 'linewidth': 2},
            'isentropic': {'color': 'green', 'linestyle': '--', 'linewidth': 2},
            'default': {'color': 'gray', 'linestyle': ':', 'linewidth': 2}
        }

    def create_plot(self, connections):
        """
        Create and display the fluid diagram plot with isolines and fluid states.

        :param connections: List of connections between fluid states.
        """
        isoline_data = self.get_isoline_data()
        self.diagram.draw_isolines(fig=self.fig, ax=self.ax, diagram_type=self.diagram_type,
                                   x_min=self.x_min, x_max=self.x_max, y_min=self.y_min, y_max=self.y_max,
                                   isoline_data=isoline_data)

        # Customize axis labels after fluprodia draws the diagram
        if self.diagram_type == 'logph':
            self.ax.set_ylabel('Pressure, P [bar]')
            self.ax.set_xlabel('Enthalpy, h [kJ/kg]')
        elif self.diagram_type == 'Ts':
            self.ax.set_ylabel('Temperature, T [°C]')
            self.ax.set_xlabel('Entropy, s [kJ/kg·K]')
        elif self.diagram_type == 'hs':
            self.ax.set_ylabel('Entropy, s [kJ/kg·K]')
            self.ax.set_xlabel('Enthalpy, h [kJ/kg]')
        elif self.diagram_type == 'Th':
            self.ax.set_ylabel('Temperature, T [°C]')
            self.ax.set_xlabel('Enthalpy, h [kJ/kg]')
        
        # Set dynamic title based on fluid
        fluid_display_name = self.fluid if self.fluid in ['H2O', 'CO2'] else self.fluid
        self.ax.set_title(f'Phase Diagram for {fluid_display_name}', fontsize=14, fontweight='bold')

        for text in self.ax.texts:
            text.set_fontsize(self.label_fontsize)

        self.plot_fluid_states(self.states, connections=connections)
        self.add_color_bar()

    def get_isoline_data(self):
        """
        Retrieve the isoline data with styles.

        :return: Dictionary containing isoline data and styles.
        """
        return {
            k: {
                'values': v['values'],
                'style': {
                    'color': self.isoline_styles[k]['color'],
                    'linestyle': self.isoline_styles[k]['linestyle'],
                    'linewidth': self.isoline_styles[k].get('linewidth', 1)
                }
            } for k, v in self.isoline_settings.items()
        }

    def add_color_bar(self):
        """
        Add a color bar to the plot to indicate time progression of states.
        """
        num_states = len(next(iter(self.states.values())))

        if self.cbar:
            self.cbar.remove()
        self.cbar = self.fig.colorbar(ScalarMappable(norm=Normalize(vmin=0, vmax=num_states - 1), cmap='Greys'), ax=self.ax, pad=0.1)

        self.cbar.set_label('Time Progression [years]')
        self.cbar.set_ticks(range(num_states))
        self.cbar.set_ticklabels([str(i + 1) for i in range(num_states)])

    def convert_states(self, fluid_states, target_diagram):
        """
        Convert fluid states based on the target diagram type.

        :param fluid_states: Dictionary of fluid states.
        :param target_diagram: The type of diagram (e.g., 'Ts', 'hs', 'logph').
        :return: Converted fluid states.
        """
        converted_states = {}

        for point_name, point_states in fluid_states.items():
            converted_states[point_name] = []
            for p_bar, h_kjkg in point_states:
                p_pa = self.bar_to_Pa(p_bar)
                h_jkg = h_kjkg * 1e3
                T, S, v = self.calculate_properties(p_pa, h_jkg)
                Ta, Sa, va, pa, ha = self.convert_units(T, S, v, p_pa, h_jkg)
                converted_states[point_name].append(self.format_converted_state(target_diagram, Ta, Sa, va, pa, ha))

        return converted_states

    def calculate_properties(self, p_pa, h_jkg):
        """
        Calculate temperature, entropy, and specific volume for given pressure and enthalpy.

        :param p_pa: Pressure in Pascal.
        :param h_jkg: Enthalpy in J/kg.
        :return: Tuple containing temperature, entropy, and specific volume.
        """
        T = PropsSI('T', 'P', p_pa, 'H', h_jkg, self.fluid)
        S = PropsSI('S', 'P', p_pa, 'H', h_jkg, self.fluid)
        v = 1 / PropsSI('D', 'P', p_pa, 'H', h_jkg, self.fluid)

        return T, S, v

    def convert_units(self, T, S, v, p_pa, h_jkg):
        """
        Convert the calculated properties to the selected unit system.

        :param T: Temperature in Kelvin.
        :param S: Entropy in J/kg·K.
        :param v: Specific volume in m^3/kg.
        :param p_pa: Pressure in Pascal.
        :param h_jkg: Enthalpy in J/kg.
        :return: Tuple containing converted temperature, entropy, specific volume, pressure, and enthalpy.
        """
        Ta = self.convert_temperature(T)
        Sa = self.convert_entropy(S)
        va = self.convert_volume(v)
        pa = self.convert_pressure(p_pa)
        ha = self.convert_enthalpy(h_jkg)

        return Ta, Sa, va, pa, ha

    def convert_temperature(self, T):
        """
        Convert temperature to the selected unit system.

        :param T: Temperature in Kelvin.
        :return: Converted temperature.
        """
        if self.unit_system['T'] == '°C':
            return T - 273.15
        elif self.unit_system['T'] == '°F':
            return (T - 273.15) * 9/5 + 32

        return T

    def convert_entropy(self, S):
        """
        Convert entropy to the selected unit system.

        :param S: Entropy in J/kg·K.
        :return: Converted entropy.
        """
        if self.unit_system['s'] == 'kJ/kgK':
            return S / 1e3
        elif self.unit_system['s'] == 'MJ/kgK':
            return S / 1e6

        return S

    def convert_volume(self, v):
        """
        Convert specific volume to the selected unit system.

        :param v: Specific volume in m^3/kg.
        :return: Converted specific volume.
        """
        if self.unit_system['v'] == 'l/kg':
            return v * 1e3

        return v

    def convert_pressure(self, p_pa):
        """
        Convert pressure to the selected unit system.

        :param p_pa: Pressure in Pascal.
        :return: Converted pressure.
        """
        if self.unit_system['p'] == 'hPa':
            return p_pa / 1e2
        elif self.unit_system['p'] == 'mbar':
            return p_pa / 1e2
        elif self.unit_system['p'] == 'psi':
            return p_pa * 0.0001450377
        elif self.unit_system['p'] == 'kPa':
            return p_pa / 1e3
        elif self.unit_system['p'] == 'bar':
            return p_pa / 1e5
        elif self.unit_system['p'] == 'MPa':
            return p_pa / 1e6

        return p_pa

    def convert_enthalpy(self, h_jkg):
        """
        Convert enthalpy to the selected unit system.

        :param h_jkg: Enthalpy in J/kg.
        :return: Converted enthalpy.
        """
        if self.unit_system['h'] == 'kJ/kg':
            return h_jkg / 1e3
        elif self.unit_system['h'] == 'MJ/kg':
            return h_jkg / 1e6

        return h_jkg

    @staticmethod
    def format_converted_state(diagram_type, Ta, Sa, va, pa, ha):
        """
        Format the converted state based on the diagram type.

        :param diagram_type: The type of diagram.
        :param Ta: Converted temperature.
        :param Sa: Converted entropy.
        :param va: Converted specific volume.
        :param pa: Converted pressure.
        :param ha: Converted enthalpy.
        :return: Tuple containing the formatted state for plotting.
        """
        if diagram_type == 'Ts':
            return Ta, Sa
        elif diagram_type == 'hs':
            return ha, Sa
        elif diagram_type == 'logph':
            return pa, ha
        elif diagram_type == 'Th':
            return Ta, ha
        elif diagram_type == 'plogv':
            return va, pa
        raise ValueError(f"Unsupported diagram type: {diagram_type}")


class MplCanvas(FigureCanvas):
    """
    Class representing a Matplotlib canvas for embedding plots in a PyQt5 application.
    """

    def __init__(self, parent=None, width=5, height=10, dpi=100):
        self.figure = Figure(figsize=(width, height), dpi=dpi)
        self.axes = self.figure.add_subplot(111)
        super(MplCanvas, self).__init__(self.figure)
