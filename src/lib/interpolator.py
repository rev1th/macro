
from pydantic.dataclasses import dataclass
from dataclasses import InitVar
from typing import ClassVar
import numpy as np
from scipy import interpolate
import bisect


@dataclass
class Interpolator():
    _xy_init: InitVar[list[tuple[float, float]]]
    _xs: ClassVar[list[float]]
    _ys: ClassVar[list[float]]

    def __post_init__(self, xy_init):
        self._xs, self._ys = zip(*xy_init)

    @property
    def size(self):
        return len(self._xs)
    
    @classmethod
    def default(cls):
        return LogCubicSplineNatural

    @classmethod
    def fromString(cls, type: str):
        if type in ('Default', 'LogCubicSplineNatural'):
            return LogCubicSplineNatural
        elif type == 'Step':
            return Step
        elif type == 'LogLinear':
            return LogLinear
        elif type == 'LogCubicSpline':
            return LogCubicSpline
        elif type == 'MonotoneConvex':
            return MonotoneConvex
        else:
            raise Exception(f"{type} not supported yet")

    def _get_value(self, x: float):
        assert x >= self._xs[0], f"Cannot interpolate {x} before start {self._xs[0]}"

    def get_value(self, _: float):
        raise Exception("Abstract function")


@dataclass
class Step(Interpolator):

    def __post_init__(self, xy_init):
        super().__post_init__(xy_init)
    
    def get_value(self, x: float) -> float:
        super()._get_value(x)

        if x in self._xs:
            return self._ys[self._xs.index(x)]
        ih = bisect.bisect_left(self._xs, x)
        return self._ys[ih-1]


@dataclass
class LogLinear(Interpolator):
    log_ys: ClassVar[list[float]] = None

    def __post_init__(self, xy_init):
        super().__post_init__(xy_init)
        self.log_ys = [np.log(y) for y in self._ys]
    
    def get_value(self, x: float) -> float:
        super()._get_value(x)

        if x in self._xs:
            return self._ys[self._xs.index(x)]
        elif x > self._xs[-1]:
            slope = (self.log_ys[-1] - self.log_ys[-2]) / (self._xs[-1] - self._xs[-2])
            return self._ys[-1] * np.exp((x-self._xs[-1]) * slope)
        ih = bisect.bisect_left(self._xs, x)
        slope = (self.log_ys[ih] - self.log_ys[ih-1]) / (self._xs[ih] - self._xs[ih-1])
        return self._ys[ih-1] * np.exp((x - self._xs[ih-1]) * slope)


# Cubic spline with free ends
@dataclass
class LogCubicSpline(Interpolator):
    log_ys: ClassVar[list[float]] = None

    def __post_init__(self, xy_init):
        super().__post_init__(xy_init)
        self.log_ys = [np.log(y) for y in self._ys]
        self.spline_tck = interpolate.splrep(self._xs, self.log_ys)

    def get_value(self, x: float) -> float:
        super()._get_value(x)
        return np.exp(interpolate.splev(x, self.spline_tck))


# Cubic spline with f''(x) = 0 at both ends. Standard for curve construction
@dataclass
class LogCubicSplineNatural(Interpolator):
    log_ys: ClassVar[list[float]] = None

    def __post_init__(self, xy_init):
        super().__post_init__(xy_init)
        self.log_ys = [np.log(y) for y in self._ys]
        self.spline_tck = interpolate.make_interp_spline(
                            self._xs, self.log_ys,
                            bc_type=([(2, 0.0)], [(2, 0.0)]))

    def get_value(self, x: float) -> float:
        super()._get_value(x)
        return np.exp(interpolate.splev(x, self.spline_tck))


@dataclass
class MonotoneConvex(Interpolator):
    log_ys: ClassVar[list[float]] = None

    def __post_init__(self, xy_init):
        super().__post_init__(xy_init)
        n = len(self._ys)
        self.fds = [0] + [-np.log(self._ys[i] / self._ys[i-1]) / (self._xs[i] - self._xs[i-1]) for i in range(1, n)]
        self.fs = [0] * n
        for i in range(1, n-1):
            self.fs[i] = (self._xs[i] - self._xs[i-1]) / (self._xs[i+1] - self._xs[i-1]) * self.fds[i+1] + \
                (self._xs[i+1] - self._xs[i]) / (self._xs[i+1] - self._xs[i-1]) * self.fds[i]
        self.fs[0] = self.fds[1] - (self.fs[1] - self.fds[1]) / 2
        self.fs[n-1] = self.fds[n-1] - (self.fs[n-2] - self.fds[n-1]) / 2

    def get_value(self, x: float):
        super()._get_value(x)
        
        if x in self._xs:
            return self._ys[self._xs.index(x)]
        elif x > self._xs[-1]:
            f_x = -np.log(self._ys[-1] / self.get_value(self._xs[-1]-1))
            return self._ys[-1] * np.exp(-f_x * (x-self._xs[-1]))
        ih = bisect.bisect_left(self._xs, x)
        dx = (x-self._xs[ih-1]) / (self._xs[ih]-self._xs[ih-1])
        gi = self.fs[ih] - self.fds[ih]
        gi_1 = self.fs[ih-1] - self.fds[ih]
        if ((gi_1 > 0 and -gi_1/2 >= gi >= -2*gi_1) or (gi_1 < 0 and -gi_1/2 <= gi <= -2*gi_1)):
            gx_s = (gi_1 * (1 - 2*dx + dx*dx) + gi * (-dx + dx*dx)) * dx
        elif ((gi_1 < 0 and gi > -2*gi_1) or (gi_1 > 0 and gi < -2*gi_1)):
            nu = (gi + 2*gi_1) / (gi - gi_1)
            gx_s = gi_1 * dx
            if dx > nu:
                dxr = (dx-nu) / (1-nu)
                gx_s += (gi-gi_1) * dxr * dxr * (dx-nu) / 3
        elif ((gi_1 > 0 and 0 > gi > -gi_1/2) or (gi_1 < 0 and 0 < gi < -gi_1/2)):
            nu = 3*gi / (gi - gi_1)
            gx_s = gi * dx
            if dx < nu:
                dxr = dx / nu
                gx_s += (gi_1-gi) * (1 - dxr + dxr * dxr / 3) * dx
            else:
                gx_s += (gi_1-gi) * nu / 3
        else:
            nu = gi / (gi + gi_1)
            anu = -gi_1*gi / (gi_1 + gi)
            gx_s = anu * dx
            if dx < nu:
                dxr = dx / nu
                gx_s += (gi_1-anu) * (1 - dxr + dxr * dxr / 3) * dx
            else:
                gx_s += (gi_1-anu) * nu / 3
                dxr = (dx-nu) / (1-nu)
                gx_s += (gi-anu) * dxr * dxr * (dx-nu) / 3
        return self._ys[ih-1] * np.exp(-(self.fds[ih] * (x-self._xs[ih-1]) + gx_s * (self._xs[ih]-self._xs[ih-1])))

