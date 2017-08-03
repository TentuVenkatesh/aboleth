"""Package init."""
from .version import __version__
from .losses import elbo
from .layers import (Activation, DropOut, MaxPool2D, DenseVariational,
                     DenseMAP, InputLayer, EmbedVariational, RandomFourier,
                     RandomArcCosine)
from .ops import stack, concat, slicecat, add, mean_impute, gaussian_impute
from .kernels import RBF, Matern
from .likelihoods import (LikeNormal, LikeBernoulli, LikeBinomial,
                          LikeCategorical)
from .distributions import (ParamNormal, ParamGaussian, norm_prior,
                            norm_posterior, gaus_posterior)
from .util import (batch, pos, predict_expected, predict_samples,
                   batch_prediction)
from .random import set_hyperseed

__all__ = (
    '__version__',
    'elbo',
    'Activation',
    'DropOut',
    'MaxPool2D',
    'DenseVariational',
    'DenseMAP',
    'EmbedVariational',
    'RandomFourier',
    'RandomArcCosine',
    'LikeNormal',
    'LikeBernoulli',
    'LikeBinomial',
    'LikeCategorical',
    'ParamNormal',
    'ParamGaussian',
    'norm_prior',
    'norm_posterior',
    'gaus_posterior',
    'batch',
    'pos',
    'predict_expected',
    'predict_samples',
    'batch_prediction',
    'set_hyperseed',
    'InputLayer',
    'stack',
    'concat',
    'add',
    'slicecat',
    'mean_impute',
    'gaussian_impute',
    'RBF',
    'Matern'
)
