"""Visualization module for energy system optimization results.

Creates Hotmaps-style stacked area charts for thermal power energy mix.
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from typing import Dict, Optional


def plot_thermal_power_energymix(
    demand: np.ndarray,
    generation: Dict[str, np.ndarray],
    storage_flow: Optional[np.ndarray] = None,
    output_file: str = "thermal_power_energymix.png",
    figsize: tuple = (14, 6)
):
    """Create Hotmaps-style stacked area chart for thermal power energy mix.
    
    Args:
        demand: Heat demand profile (8760 hours)
        generation: Dict of technology name -> generation profile
        storage_flow: Storage flow (positive = charging, negative = discharging)
        output_file: Output filename for the plot
        figsize: Figure size tuple
    """
    hours = np.arange(len(demand))
    
    fig, ax = plt.subplots(figsize=figsize)
    
    # Dynamic colors using tab10 palette
    cmap = cm.get_cmap('tab10')
    storage_charge_color = '#F44336'  # Red for charging
    
    # Prepare data for stacking
    stack_data = []
    stack_labels = []
    stack_colors = []
    color_idx = 0
    
    # 1. Storage discharge (positive contribution to meeting demand)
    if storage_flow is not None:
        discharge = np.maximum(-storage_flow, 0)  # Negative flow = discharge
        if discharge.sum() > 0:
            stack_data.append(discharge)
            stack_labels.append('Storage Discharge')
            stack_colors.append(cmap(color_idx % 10))
            color_idx += 1
    
    # 2. Generation technologies
    for name, gen in generation.items():
        if gen.sum() > 0:
            stack_data.append(gen)
            stack_labels.append(name)
            stack_colors.append(cmap(color_idx % 10))
            color_idx += 1
    
    # Create stacked area plot for positive values
    if stack_data:
        ax.stackplot(hours, *stack_data, labels=stack_labels, colors=stack_colors, alpha=0.8)
    
    # 3. Storage charging (shown as negative, below zero)
    if storage_flow is not None:
        charge = np.maximum(storage_flow, 0)  # Positive flow = charging
        if charge.sum() > 0:
            ax.fill_between(hours, 0, -charge, 
                           label='Storage Charging', 
                           color=storage_charge_color, 
                           alpha=0.5)
    
    # 4. Heat demand as a line on top
    ax.plot(hours, demand, 'k-', linewidth=0.8, label='Heat Demand', alpha=0.7)
    
    # Styling
    ax.set_xlabel('Time in Hours', fontsize=11)
    ax.set_ylabel('MWh_th', fontsize=11)
    ax.set_title('Thermal Power Energymix: over year', fontsize=12, fontweight='bold')
    
    # Set axis limits
    ax.set_xlim(0, len(demand))
    y_max = max(demand.max(), max(s.max() for s in stack_data) if stack_data else 0) * 1.1
    y_min = -np.maximum(storage_flow, 0).max() * 1.2 if storage_flow is not None else 0
    ax.set_ylim(y_min, y_max)
    
    # Legend outside the plot
    ax.legend(loc='center left', bbox_to_anchor=(1.02, 0.5), frameon=True)
    
    # Grid
    ax.grid(True, alpha=0.3, linestyle='-', linewidth=0.5)
    ax.set_axisbelow(True)
    
    # Tight layout to fit legend
    plt.tight_layout()
    
    # Save
    plt.savefig(output_file, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"Saved: {output_file}")


def plot_weekly_detail(
    demand: np.ndarray,
    generation: Dict[str, np.ndarray],
    storage_flow: Optional[np.ndarray] = None,
    week: int = 1,
    output_file: str = "weekly_detail.png",
    figsize: tuple = (14, 6)
):
    """Create detailed view for a specific week.
    
    Args:
        demand: Heat demand profile (8760 hours)
        generation: Dict of technology name -> generation profile
        storage_flow: Storage flow
        week: Week number (1-52)
        output_file: Output filename
        figsize: Figure size
    """
    start_hour = (week - 1) * 168
    end_hour = min(start_hour + 168, len(demand))
    
    hours = np.arange(start_hour, end_hour)
    
    fig, ax = plt.subplots(figsize=figsize)
    
    # Dynamic colors using tab10 palette
    cmap = cm.get_cmap('tab10')
    storage_charge_color = '#F44336'  # Red for charging
    
    stack_data = []
    stack_labels = []
    stack_colors = []
    color_idx = 0
    
    # Storage discharge
    if storage_flow is not None:
        discharge = np.maximum(-storage_flow[start_hour:end_hour], 0)
        if discharge.sum() > 0:
            stack_data.append(discharge)
            stack_labels.append('Storage Discharge')
            stack_colors.append(cmap(color_idx % 10))
            color_idx += 1
    
    # Generation
    for name, gen in generation.items():
        gen_week = gen[start_hour:end_hour]
        if gen_week.sum() > 0:
            stack_data.append(gen_week)
            stack_labels.append(name)
            stack_colors.append(cmap(color_idx % 10))
            color_idx += 1
    
    if stack_data:
        ax.stackplot(hours, *stack_data, labels=stack_labels, colors=stack_colors, alpha=0.8)
    
    # Storage charging
    if storage_flow is not None:
        charge = np.maximum(storage_flow[start_hour:end_hour], 0)
        if charge.sum() > 0:
            ax.fill_between(hours, 0, -charge, 
                           label='Storage Charging', 
                           color=storage_charge_color, 
                           alpha=0.5)
    
    # Demand line
    ax.plot(hours, demand[start_hour:end_hour], 'k-', linewidth=1.2, label='Heat Demand')
    
    ax.set_xlabel('Hour of Year', fontsize=11)
    ax.set_ylabel('MWh_th', fontsize=11)
    ax.set_title(f'Thermal Power Energymix: Week {week}', fontsize=12, fontweight='bold')
    ax.legend(loc='center left', bbox_to_anchor=(1.02, 0.5))
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_file, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"Saved: {output_file}")
