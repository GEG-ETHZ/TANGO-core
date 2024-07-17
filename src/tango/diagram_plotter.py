import matplotlib.pyplot as plt
import numpy as np
from CoolProp.CoolProp import PropsSI
from fluprodia import FluidPropertyDiagram
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable

class FluidDiagramPlotter:
    def __init__(self, fluid_states, fluid='CO2', unit_system={'T': '°C', 'h': 'kJ/kg', 'p': 'bar'},
                 diagram_type='logph', x_min=100, x_max=500, y_min=1, y_max=1000,
                 isoline_config=None):
        self.fluid = fluid
        self.states = self.convert_states(fluid_states, diagram_type)
        self.unit_system = unit_system
        self.diagram_type = diagram_type
        self.x_min = x_min
        self.x_max = x_max
        self.y_min = y_min
        self.y_max = y_max
        self.isoline_config = isoline_config or {
            'Q': {'start': 0, 'end': 1, 'num': 2},
            'T': {'start': -40, 'end': 160, 'num': 10},
            'p': {'start': 0.01, 'end': 1000, 'num': 6},
            'v': {'start': 0.001, 'end': 10, 'num': 0},
            's': {'start': 1000, 'end': 10000, 'num': 0},
            'h': {'start': 0, 'end': 3600, 'num': 19}
        }
        self.isoline_settings = self._generate_isoline_settings()
        self.diagram = FluidPropertyDiagram(fluid=self.fluid)
        self.diagram.set_unit_system(**self.unit_system)
        self.diagram.set_isolines(**self.isoline_settings)
        self.diagram.calc_isolines()

    @staticmethod
    def bar_to_Pa(p_bar):
        return p_bar * 1e5


    def _generate_isoline_settings(self):
        return {
            'Q': np.linspace(self.isoline_config['Q']['start'], self.isoline_config['Q']['end'], self.isoline_config['Q']['num']),
            'T': np.linspace(self.isoline_config['T']['start'], self.isoline_config['T']['end'], self.isoline_config['T']['num']),
            'p': np.geomspace(self.isoline_config['p']['start'], self.isoline_config['p']['end'], self.isoline_config['p']['num']) * 1e5,
            'v': np.geomspace(self.isoline_config['v']['start'], self.isoline_config['v']['end'], self.isoline_config['v']['num']) if self.isoline_config['v']['num'] > 0 else np.array([]),
            's': np.linspace(self.isoline_config['s']['start'], self.isoline_config['s']['end'], self.isoline_config['s']['num']) if self.isoline_config['s']['num'] > 0 else np.array([]),
            'h': np.linspace(self.isoline_config['h']['start'], self.isoline_config['h']['end'], self.isoline_config['h']['num'])
        }

    def plot_fluid_states(self, ax, states, connections=None, markersize=6, fontsize=8, cmap='Greys'):
        labeled_points = set()
        for point_name, point_states in states.items():
            norm = Normalize(vmin=0, vmax=len(point_states) - 1)
            scalar_map = ScalarMappable(norm=norm, cmap=cmap +'_r')
            colors = [scalar_map.to_rgba(i) for i in range(len(point_states))]

            for i, (p, h) in enumerate(point_states):
                # print(i,p,h)
                color = colors[i]
                ax.plot(h, p, marker='o', color=color, markersize=markersize)

                # Annotate the first occurrence of each point_name
                if point_name not in labeled_points:
                    ax.annotate(
                        point_name, (h, p), xytext=(10, 5), ha='left', va='center',
                        textcoords='offset points', fontsize=fontsize, color='black'
                    )
                    labeled_points.add(point_name)

        if connections:
            line_styles = {
                'non-isentropic': {'color': 'blue', 'linestyle': '-', 'linewidth': 1},
                'isentropic': {'color': 'green', 'linestyle': '--', 'linewidth': 1},
                'default': {'color': 'gray', 'linestyle': ':', 'linewidth': 1}
            }

            # print(connections)

            for start, end, line_type in connections:
                start_state = next(state for point, states in states.items() for state in states if start in point)
                end_state = next(state for point, states in states.items() for state in states if end in point)
                style = line_styles.get(line_type, line_styles['default'])
                ax.plot([start_state[1], end_state[1]], [start_state[0], end_state[0]], **style)

        # Set axis labels based on diagram type
        if self.diagram_type == 'Ts':
            ax.set_ylabel('Temperature (°C)', fontsize=10)
            ax.set_xlabel('Specific Entropy (kJ/kg·K)', fontsize=10)
        elif self.diagram_type == 'hs':
            ax.set_ylabel('Specific Enthalpy (kJ/kg)', fontsize=10)
            ax.set_xlabel('Specific Entropy (kJ/kg·K)', fontsize=10)
        elif self.diagram_type == 'logph':
            ax.set_xlabel('Specific Enthalpy (kJ/kg)', fontsize=10)
            ax.set_ylabel('Pressure (bar)', fontsize=10)
        elif self.diagram_type == 'Th':
            ax.set_ylabel('Temperature (°C)', fontsize=10)
            ax.set_xlabel('Specific Enthalpy (kJ/kg)', fontsize=10)
        elif self.diagram_type == 'plogv':
            ax.set_ylabel('Specific Volume (m³/kg)', fontsize=10)
            ax.set_xlabel('Pressure (bar)', fontsize=10)

    def create_plot(self, connections):
        # print('now called')
        plt.style.use('fivethirtyeight')  # Changed style to 'ggplot'
        fig, ax = plt.subplots(1, figsize=(10, 6))
        self.diagram.draw_isolines(diagram_type=self.diagram_type, fig=fig, ax=ax, x_min=self.x_min, x_max=self.x_max, y_min=self.y_min, y_max=self.y_max)

        self.plot_fluid_states(ax, self.states, connections=connections)

        if self.states.values():
            num_states = len(next(iter(self.states.values())))
        else:
            num_states = 0

        cbar = fig.colorbar(ScalarMappable(norm=Normalize(vmin=0, vmax=num_states - 1), cmap='gray'), ax=ax, pad=0.1)
        cbar.set_label('Time Progression')
        cbar.set_ticks(range(num_states))
        cbar.set_ticklabels([str(i + 1) for i in range(num_states)])

        plt.tight_layout()
        fig.savefig('diagram.svg', bbox_inches='tight')
        fig.savefig('diagram.png', dpi=300, bbox_inches='tight')
        # plt.show()

    def convert_states(self, fluid_states, target_diagram):
        converted_states = {}
        # print('fluid_states', fluid_states)
        for point_name, point_states in fluid_states.items():
            converted_states[point_name] = []
            for p_bar, h_kjkg in point_states:
                p_pa = self.bar_to_Pa(p_bar)
                h_jkg = h_kjkg * 1e3  # Convert kJ/kg to J/kg

                # Calculate all properties
                T = PropsSI('T', 'P', p_pa, 'H', h_jkg, self.fluid) - 273.15  # Temperature in C
                S = PropsSI('S', 'P', p_pa, 'H', h_jkg, self.fluid)/1000  # Entropy in J/kg.K
                v = 1 / PropsSI('D', 'P', p_pa, 'H', h_jkg, self.fluid)  # Specific volume in m³/kg

                # Convert to the target diagram units
                if target_diagram == 'Ts':
                    converted_states[point_name].append((T, S))  # S in kJ/kg.K
                elif target_diagram == 'hs':
                    converted_states[point_name].append((h_kjkg, S))  # H in kJ/kg, S in kJ/kg.K
                elif target_diagram == 'logph':
                    converted_states[point_name].append((p_bar, h_kjkg))  # H in kJ/kg, P in bar
                elif target_diagram == 'Th':
                    converted_states[point_name].append((T, h_kjkg))  # T in C, H in kJ/kg
                elif target_diagram == 'plogv':
                    converted_states[point_name].append((v, p_bar))  # v in m³/kg, P in bar
                else:
                    raise ValueError(f"Unsupported diagram type: {target_diagram}")
        # print('converted_states', converted_states)

        return converted_states
