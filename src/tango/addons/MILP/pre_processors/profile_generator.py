"""
Input parameters for energy system optimization.
Supports loading profiles from CSV, pattern list, or function.
"""

import numpy as np
from pathlib import Path
from typing import Callable, List, Union, Optional

HOURS_PER_YEAR = 8760


class Profile:
    """Generic 8760-hour profile (demand, solar, price, etc.)"""
    
    def __init__(self, values: np.ndarray, name: str = "demand"):
        if len(values) != HOURS_PER_YEAR:
            raise ValueError(f"Profile must have {HOURS_PER_YEAR} values, got {len(values)}")
        self.values = np.array(values, dtype=np.float64)
        self.name = name
    
    @classmethod
    def from_csv(cls, filepath: str, column: int = 0, skip_header: bool = True) -> "Profile":
        """Load from CSV file."""
        values = np.loadtxt(filepath, delimiter=',', skiprows=1 if skip_header else 0, usecols=column)
        return cls(values)
    
    @classmethod
    def from_pattern(cls, daily_pattern: List[float], noise_std: float = 0.0, 
                     min_value: float = 0.0, seed: int = None) -> "Profile":
        """Create from 24-hour pattern, repeated for the year."""
        if len(daily_pattern) != 24:
            raise ValueError(f"Daily pattern must have 24 values, got {len(daily_pattern)}")
        if seed is not None:
            np.random.seed(seed)
        values = np.tile(daily_pattern, HOURS_PER_YEAR // 24 + 1)[:HOURS_PER_YEAR]
        if noise_std > 0:
            values = values + np.random.normal(0, noise_std, HOURS_PER_YEAR)
        return cls(np.maximum(values, min_value))
    
    @classmethod
    def from_function(cls, func: Callable[[int], float]) -> "Profile":
        """Create from function: f(hour) -> value."""
        return cls(np.array([func(h) for h in range(HOURS_PER_YEAR)]))
    
    @property
    def peak(self) -> float: return float(self.values.max())
    
    @property
    def average(self) -> float: return float(self.values.mean())
    
    @property
    def total_energy(self) -> float: return float(self.values.sum())
    
    def __getitem__(self, idx): return self.values[idx]
    def __len__(self): return HOURS_PER_YEAR
