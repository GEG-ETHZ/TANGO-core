import numpy as np

class LinearInterpolation:
    def __init__(self, x, y, extrapolate=False):
        """
        Initialize the LinearInterpolation class.

        Parameters:
            x (list): Independent variable (e.g., time points).
            y (list): Dependent variable (e.g., time steps).
            extrapolate (bool): Whether to allow extrapolation beyond x.
        """
        if len(x) != len(y):
            raise ValueError("x and y must be of the same length")
        if any(x[i] >= x[i + 1] for i in range(len(x) - 1)):
            raise ValueError("x values must be strictly increasing")

        self._x = np.array(x)
        self._y = np.array(y)
        self._extrapolate = extrapolate

    def sample(self, x):
        """
        Interpolate or extrapolate the value of y at a given x.

        Parameters:
            x (float): The x value to sample.

        Returns:
            float: The interpolated or extrapolated value of y.
        """
        if x < self._x[0]:
            if self._extrapolate:
                return self._y[0] + (x - self._x[0]) / (self._x[1] - self._x[0]) * (self._y[1] - self._y[0])
            else:
                return self._y[0]
        elif x > self._x[-1]:
            if self._extrapolate:
                return self._y[-1] + (x - self._x[-1]) / (self._x[-2] - self._x[-1]) * (self._y[-2] - self._y[-1])
            else:
                return self._y[-1]
        else:
            idx = np.searchsorted(self._x, x) - 1
            x0, x1 = self._x[idx], self._x[idx + 1]
            y0, y1 = self._y[idx], self._y[idx + 1]
            return y0 + (x - x0) / (x1 - x0) * (y1 - y0)
