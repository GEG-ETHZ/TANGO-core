"""Load Duration Curve visualization (Hotmaps compatible)."""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from typing import Dict, Optional


def plot_load_duration_curve(demand: np.ndarray, generation: Dict[str, np.ndarray], 
                             storage_flow: Optional[np.ndarray] = None,
                             save_path: str = None):
    """Plot load duration curve with stacked generation areas (Hotmaps style).
    
    Hotmaps approach:
    - Sort by SUM of all generation (not by demand)
    - Stack generation areas in sorted order
    - Show both generation sum line and demand line (separately sorted)
    
    Args:
        demand: 8760-hour demand array
        generation: Dict of tech_name -> generation array
        storage_flow: Optional storage flow (positive=charge, negative=discharge)
        save_path: Optional path to save the figure
    """
    # Build generation matrix including storage discharge
    gen_names = list(generation.keys())
    gen_arrays = [generation[name] for name in gen_names]
    
    # Add storage discharge as a generation source
    if storage_flow is not None:
        discharge = np.maximum(-storage_flow, 0)  # Negative flow = discharge
        if discharge.sum() > 1e-6:
            gen_names.append("Storage Discharge")
            gen_arrays.append(discharge)
    
    # Stack into matrix (N_tech x N_hours)
    gen_matrix = np.array(gen_arrays)
    
    # Hotmaps: Sort by total generation sum at each hour (descending)
    total_gen = np.sum(gen_matrix, axis=0)
    sort_idx = np.argsort(-total_gen)  # Sort by total generation, descending
    
    # Apply sort to generation matrix
    sorted_gen = gen_matrix[:, sort_idx]
    sorted_total = total_gen[sort_idx]
    
    # Demand: separately sorted (its own load duration curve)
    sorted_demand = np.sort(demand)[::-1]
    
    hours = np.arange(len(demand))
    
    fig, ax = plt.subplots(figsize=(12, 5))
    
    # Dynamic colors using tab10 palette (supports any number of technologies)
    cmap = cm.get_cmap('tab10')
    color_list = [cmap(i % 10) for i in range(len(gen_names))]
    
    # Filter out zero-generation technologies
    nonzero_mask = [np.sum(sorted_gen[i]) > 1e-6 for i in range(len(gen_names))]
    active_names = [gen_names[i] for i in range(len(gen_names)) if nonzero_mask[i]]
    active_gen = [sorted_gen[i] for i in range(len(gen_names)) if nonzero_mask[i]]
    active_colors = [color_list[i] for i in range(len(gen_names)) if nonzero_mask[i]]
    
    # Stacked area plot (sorted by total generation)
    if active_gen:
        ax.stackplot(hours, *active_gen, labels=active_names, colors=active_colors, alpha=0.8)
    
    # Generation sum line
    ax.plot(hours, sorted_total, 'k-', linewidth=0.8, label='Generation Sum', alpha=0.8)
    
    # Demand load duration curve (separately sorted)
    ax.plot(hours, sorted_demand, 'k--', linewidth=1.2, label='Load Duration Curve', alpha=0.9)
    
    ax.set_xlabel("Time in Hours")
    ax.set_ylabel("MWh_th")
    ax.set_title("Load Duration Curve")
    ax.legend(loc='center left', bbox_to_anchor=(1.02, 0.5), frameon=True)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, len(demand))
    ax.set_ylim(0, None)
    
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight', facecolor='white')
        print(f"Saved: {save_path}")
    plt.close()
    return fig

