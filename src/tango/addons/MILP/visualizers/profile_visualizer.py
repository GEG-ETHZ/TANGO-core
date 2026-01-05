"""General purpose profile visualizer for any 8760-hour time series."""

import numpy as np
import matplotlib.pyplot as plt
from typing import List, Tuple


class ProfileVisualizer:
    """Visualize one or more 8760-hour profiles."""
    
    def __init__(self, ylabel: str = "Power (kW)"):
        self.profiles: List[Tuple[str, np.ndarray]] = []
        self.ylabel = ylabel
    
    def add(self, name: str, values: np.ndarray):
        """Add a profile."""
        self.profiles.append((name, values))
        return self
    
    def plot_timeseries(self, title: str = "Profiles", save_path: str = None):
        """Plot full year and first week."""
        fig, axes = plt.subplots(2, 1, figsize=(12, 6))
        
        for name, values in self.profiles:
            axes[0].plot(values, label=name, alpha=0.8, linewidth=0.5)
        axes[0].set_xlabel("Hour of Year")
        axes[0].set_ylabel(self.ylabel)
        axes[0].set_title(f"{title} - Full Year")
        axes[0].legend()
        axes[0].grid(True, alpha=0.3)
        
        for name, values in self.profiles:
            axes[1].plot(values[:168], label=name, alpha=0.8)
        axes[1].set_xlabel("Hour")
        axes[1].set_ylabel(self.ylabel)
        axes[1].set_title(f"{title} - First Week")
        axes[1].set_xticks(range(0, 169, 24))
        axes[1].legend()
        axes[1].grid(True, alpha=0.3)
        
        plt.tight_layout()
        if save_path:
            plt.savefig(save_path, dpi=150)
            print(f"Saved: {save_path}")
        plt.close()
        return fig
    
    def plot_comparison(self, title: str = "Comparison", save_path: str = None):
        """Compare peak/avg statistics."""
        names = [p[0] for p in self.profiles]
        peaks = [p[1].max() for p in self.profiles]
        avgs = [p[1].mean() for p in self.profiles]
        
        x = np.arange(len(self.profiles))
        width = 0.35
        
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.bar(x - width/2, peaks, width, label='Peak', color='#FF5722')
        ax.bar(x + width/2, avgs, width, label='Average', color='#4CAF50')
        ax.set_xticks(x)
        ax.set_xticklabels(names)
        ax.set_ylabel(self.ylabel)
        ax.set_title(title)
        ax.legend()
        ax.grid(True, alpha=0.3, axis='y')
        
        plt.tight_layout()
        if save_path:
            plt.savefig(save_path, dpi=150)
            print(f"Saved: {save_path}")
        plt.close()
        return fig
