"""Utility functions for addon system.

This module provides shared utilities used by addon implementations.
"""

from pathlib import Path


def resolve_addon_output_path(
    path: str | Path | None,
    default_filename: str,
    output_dir: str | Path = "output",
) -> Path:
    """Resolve addon output file path with smart defaults.

    Path resolution rules:
    - None/empty/null: returns output_dir/default_filename
    - Relative path (no leading /): returns output_dir/path
    - Starts with output_dir: returns as-is
    - Absolute path (starts with /): returns as-is

    Args:
        path: User-specified path from YAML config (may be None/empty)
        default_filename: Default filename if path is not specified
        output_dir: Output directory (default: "output")

    Returns:
        Resolved file path as Path object

    Examples:
        >>> resolve_addon_output_path(None, "states.json")
        PosixPath('output/states.json')
        >>> resolve_addon_output_path("", "states.json")
        PosixPath('output/states.json')
        >>> resolve_addon_output_path("my_states.json", "states.json")
        PosixPath('output/my_states.json')
        >>> resolve_addon_output_path("output/custom.json", "states.json")
        PosixPath('output/custom.json')
        >>> resolve_addon_output_path("/tmp/states.json", "states.json")
        PosixPath('/tmp/states.json')

    """
    output_dir = Path(output_dir)

    # Handle None or empty string
    if not path:
        return output_dir / default_filename

    path = Path(path)

    # Handle absolute paths - return as-is
    if path.is_absolute():
        return path

    # Handle paths that already include output_dir - return as-is
    try:
        path.relative_to(output_dir)
        return path
    except ValueError:
        pass

    # Relative path - prepend output_dir
    return output_dir / path
