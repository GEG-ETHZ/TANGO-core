import numpy as np


class LinearInterpolation:
    """A class for performing linear interpolation and optional extrapolation.

    Attributes:
        _x (numpy.ndarray): Independent variable values (must be strictly increasing).
        _y (numpy.ndarray): Dependent variable values.
        _extrapolate (bool): Whether to allow extrapolation beyond the range of `_x`.

    """

    def __init__(self, x, y, extrapolate=False):
        """Initializes the LinearInterpolation class.

        Args:
            x (list): Independent variable values (e.g., time points). Must be strictly increasing.
            y (list): Dependent variable values (e.g., data corresponding to `x`).
            extrapolate (bool, optional): Whether to allow extrapolation beyond the range of `x` (default: False).

        Raises:
            ValueError: If `x` and `y` have different lengths.
            ValueError: If `x` values are not strictly increasing.

        Example:
            >>> interpolator = LinearInterpolation([1, 2, 3], [2, 4, 6])

        """
        if len(x) != len(y):
            raise ValueError("x and y must be of the same length")
        if any(x[i] >= x[i + 1] for i in range(len(x) - 1)):
            raise ValueError("x values must be strictly increasing")

        self._x = np.array(x)
        self._y = np.array(y)
        self._extrapolate = extrapolate

    def sample(self, x):
        """Interpolates or extrapolates the value of `_y` at a given `_x`.

        Args:
            x (float): The x value at which to sample the interpolated or extrapolated value.

        Returns:
            float: The interpolated or extrapolated value of `_y`.

        Behavior:
        - If `x` is within the range of `_x`, performs linear interpolation.
        - If `x` is outside the range of `_x` and `extrapolate` is True, performs linear extrapolation.
        - If `x` is outside the range of `_x` and `extrapolate` is False, returns the nearest boundary value.

        Raises:
            IndexError: If `_x` contains fewer than two points (ensured by the constructor).

        Example:
            >>> interpolator = LinearInterpolation([1, 2, 3], [2, 4, 6])
            >>> interpolator.sample(2.5)
            5.0

        """
        if x < self._x[0]:
            if self._extrapolate:
                return self._y[0] + (x - self._x[0]) / (self._x[1] - self._x[0]) * (self._y[1] - self._y[0])
            else:
                return self._y[0]
        elif x > self._x[-1]:
            if self._extrapolate:
                return self._y[-1] + (x - self._x[-1]) / (self._x[-2] - self._x[-1]) * (
                    self._y[-2] - self._y[-1]
                )
            else:
                return self._y[-1]
        else:
            idx = np.searchsorted(self._x, x) - 1
            x0, x1 = self._x[idx], self._x[idx + 1]
            y0, y1 = self._y[idx], self._y[idx + 1]
            return y0 + (x - x0) / (x1 - x0) * (y1 - y0)
