import numpy as np
from timeseers.timeseries_model import TimeSeriesModel
from timeseers.utils import dot, add_subplot
import pymc3 as pm


class LinearTrend(TimeSeriesModel):
    def __init__(
            self, n_changepoints=None, changepoints_prior_scale=0.05, growth_prior_scale=1,
            pool_cols=None, pool_type='complete'
    ):
        self.n_changepoints = n_changepoints
        self.changepoints_prior_scale = changepoints_prior_scale
        self.growth_prior_scale = growth_prior_scale
        self.pool_cols = pool_cols
        self.pool_type = pool_type
        super().__init__()

    def definition(self, model, X, scale_factor):
        t = X["t"].values

        if self.pool_type == 'complete':
            group = np.zeros(len(X), dtype='int')
            self.groups_ = {0: 'all'}
            n_pools = 1
        else:
            group = X[self.pool_cols].cat.codes.values
            self.groups_ = dict(enumerate(X[self.pool_cols].cat.categories))
            n_pools = X[self.pool_cols].nunique()

        self.s = np.linspace(0, np.max(t), self.n_changepoints + 2)[1:-1]

        with model:
            A = (t[:, None] > self.s) * 1.0

            if self.pool_type == 'partial':
                sigma_k = pm.HalfCauchy('sigma_k', beta=self.growth_prior_scale)
                offset_k = pm.Normal('offset_k', mu=0, sd=1, shape=n_pools)
                k = pm.Deterministic("k", 0 + offset_k * sigma_k)

                sigma_delta = pm.HalfCauchy('sigma_delta', beta=self.changepoints_prior_scale)
                offset_delta = pm.Laplace('offset_delta', 0, 1, shape=(n_pools, self.n_changepoints))
                delta = pm.Deterministic("delta", 0 + offset_delta * sigma_delta)

                sigma_m = pm.HalfCauchy('sigma_m', beta=1.5)
                offset_m = pm.Normal('offset_m', mu=0, sd=1, shape=n_pools)
                m = pm.Deterministic("m", 0 + offset_m * sigma_m)

            else:
                k = pm.Normal("k", 0, self.growth_prior_scale, shape=n_pools)
                delta = pm.Laplace(
                    "delta", 0, self.changepoints_prior_scale, shape=(n_pools, self.n_changepoints)
                )
                m = pm.Normal("m", 0, 5, shape=n_pools)

            gamma = -self.s * delta[group, :]

            g = (k[group] + pm.math.sum(A * delta[group], axis=1)) * t + (m[group] + pm.math.sum(A * gamma, axis=1))
        return g

    def _predict(self, trace, t, pool_group=0):
        A = (t[:, None] > self.s) * 1

        k, m = trace["k"][:, pool_group], trace["m"][:, pool_group]
        growth = k + A @ trace["delta"][:, pool_group].T
        gamma = -self.s[:, None] * trace["delta"][:, pool_group].T
        offset = m + A @ gamma
        return growth * t[:, None] + offset

    def plot(self, trace, scaled_t, y_scaler):
        ax = add_subplot()
        ax.set_title(str(self))
        ax.set_xticks([])
        trend_return = np.empty((len(scaled_t), len(self.groups_)))
        for group_code, group_name in self.groups_.items():
            scaled_trend = self._predict(trace, scaled_t, group_code)
            trend = y_scaler.inv_transform(scaled_trend)
            ax.plot(scaled_t, trend.mean(axis=1), label=group_name)
            trend_return[:, group_code] = scaled_trend.mean(axis=1)

        for changepoint in self.s:
            ax.axvline(changepoint, linestyle="--", alpha=0.2, c="k")
        ax.legend()
        return trend_return

    def __repr__(self):
        return f"LinearTrend(n_changepoints={self.n_changepoints}, " \
               f"changepoints_prior_scale={self.changepoints_prior_scale}, " \
               f"growth_prior_scale={self.growth_prior_scale})"
