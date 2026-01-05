"""Demand scaling utility - normalize demand profiles to target annual total."""

import numpy as np
import pandas as pd
import os
from pre_processors.profile_generator import Profile


def load_scaled_demand(csv_path: str, total_demand: float = 50000.0) -> Profile:
    """Load demand from CSV and scale to target annual total.
    
    Args:
        csv_path: Path to demand CSV file (single column: demand values)
        total_demand: Target annual demand in MWh (default 50,000 MWh)
    
    Returns:
        Profile with scaled demand values
    """
    df = pd.read_csv(csv_path)
    values = df.iloc[:, 0].values
    
    # Normalize: x = x / sum(x) * total_demand
    scaled = values / values.sum() * total_demand
    
    print(f"Loaded demand from: {os.path.basename(csv_path)}")
    print(f"  Original range: {values.min():.1f} - {values.max():.1f}")
    print(f"  Scaled range: {scaled.min():.1f} - {scaled.max():.1f}")
    print(f"  Annual total: {scaled.sum():.0f} MWh")
    
    return Profile(scaled)


# Default: Austria demand scaled to 50,000 MWh/year
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DEMAND_PROFILE = load_scaled_demand(
    os.path.join(DATA_DIR, "demand_profile_AT.csv"),
    total_demand=50000.0
)
