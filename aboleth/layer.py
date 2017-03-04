"""Neural Net Layer tools."""
import numpy as np
import tensorflow as tf

from aboleth.util import pos


#
# Layers
#

def eye():
    """Indentity Layer."""
    def build_eye(X):
        KL = 0.
        return X, KL

    return build_eye


def activation(h=lambda X: X):
    """Activation function layer."""
    def build_activation(X):
        Phi = [h(x) for x in X]
        KL = 0.
        return Phi, KL
    return build_activation


def fork(replicas=2):
    """Fork an input into multiple, unmodified, outputs."""
    def build_fork(X):
        KL = 0.
        return [X for _ in range(replicas)], KL

    return build_fork


def lmap(*layers):
    """Map multiple layers to multiple inputs (after forking)."""
    def build_lmap(Xs):
        if len(Xs) != len(layers):
            raise ValueError("Number of layers and inputs not the same!")
        Phis, KLs = zip(*map(lambda p, X: p(X), layers, Xs))
        KL = sum(KLs)
        return Phis, KL

    return build_lmap


def cat():
    """Join multiple inputs by concatenation."""
    def build_cat(Xs):
        Phi = [tf.concat(X, axis=1) for X in Xs]
        KL = 0.
        return Phi, KL

    return build_cat


def add():
    """Join multiple inputs by addition."""
    def build_add(Xs):
        Phi = [tf.add_n(X) for X in Xs]
        KL = 0.
        return Phi, KL

    return build_add


def dense_var(output_dim, reg=1., learn_prior=True, mixtures=1):
    """Dense (fully connected) linear layer, with variational inference."""
    def build_dense(X):
        """
        X is now a list
        """
        input_dim = _input_dim(X)
        Wdim = (input_dim, output_dim)
        bdim = (output_dim,)

        # Layer priors
        pW = _NormPrior(dim=Wdim, var=reg, learn_var=learn_prior)
        pb = _NormPrior(dim=bdim, var=reg, learn_var=learn_prior)

        # Layer Posterior samples
        if mixtures > 1:
            qW = _MixPosterior(dim=Wdim, prior_var=reg, K=mixtures)
            qb = _MixPosterior(dim=bdim, prior_var=reg, K=mixtures)
        else:
            qW = _NormPosterior(dim=Wdim, prior_var=reg)
            qb = _NormPosterior(dim=bdim, prior_var=reg)

        # Linear layer
        Phi = [tf.matmul(x, qW.sample()) + qb.sample() for x in X]

        # Regularizers
        KL = tf.reduce_sum(qW.KL(pW)) + tf.reduce_sum(qb.KL(pb))

        return Phi, KL

    return build_dense


def dense_map(output_dim, l1_reg=1., l2_reg=1.):
    """Dense (fully connected) linear layer, with MAP inference."""

    def build_dense_map(X):
        input_dim = _input_dim(X)
        Wdim = (input_dim, output_dim)
        bdim = (output_dim,)

        W = tf.Variable(tf.random_normal(Wdim))
        b = tf.Variable(tf.random_normal(bdim))

        # Linear layer
        Phi = [tf.matmul(x, W) + b for x in X]

        # Regularizers
        l1, l2 = 0, 0
        if l2_reg > 0:
            l2 = l2_reg * (tf.nn.l2_loss(W) + tf.nn.l2_loss(b))
        if l1_reg > 0:
            l1 = l1_reg * (_l1_loss(W) + _l1_loss(b))
        pen = l1 + l2

        return Phi, pen

    return build_dense_map


def randomFourier(n_features, kernel=None):
    """Random fourier feature layer."""
    kernel = kernel if kernel else RBF()

    def build_randomRBF(X):
        input_dim = _input_dim(X)
        P = kernel.weights(input_dim, n_features)

        def phi(x):
            XP = tf.matmul(x, P)
            real = tf.cos(XP)
            imag = tf.sin(XP)
            result = tf.concat([real, imag], axis=1) / np.sqrt(n_features)
            return result

        Phi = [phi(x) for x in X]
        KL = 0.0
        return Phi, KL

    return build_randomRBF


#
# Random Fourier Kernels
#

class RBF:
    """RBF kernel approximation."""

    def __init__(self, lenscale=1.0):
        self.lenscale = lenscale

    def weights(self, input_dim, n_features):
        P = np.random.randn(input_dim, n_features).astype(np.float32)
        return P / self.lenscale


class Matern(RBF):
    """Matern kernel approximation."""

    def __init__(self, p=1, lenscale=1.0):
        super().__init__(lenscale)
        self.p = p

    def weights(self, input_dim, n_features):
        # p is the matern number (v = p + .5) and the two is a transformation
        # of variables between Rasmussen 2006 p84 and the CF of a Multivariate
        # Student t (see wikipedia). Also see "A Note on the Characteristic
        # Function of Multivariate t Distribution":
        #   http://ocean.kisti.re.kr/downfile/volume/kss/GCGHC8/2014/v21n1/
        #   GCGHC8_2014_v21n1_81.pdf
        # To sample from a m.v. t we use the formula
        # from wikipedia, x = y * np.sqrt(df / u) where y ~ norm(0, I),
        # u ~ chi2(df), then x ~ mvt(0, I, df)
        df = 2 * (self.p + 0.5)
        y = np.random.randn(input_dim, n_features)
        u = np.random.chisquare(df, size=(n_features,))
        P = y * np.sqrt(df / u)
        P = P.astype(np.float32)
        return P / self.lenscale


#
# Private module stuff
#

class _Normal:

    def __init__(self, mu=0., var=1.):
        self.mu = mu
        self.var = var
        self.sigma = tf.sqrt(var)

    def sample(self):
        # Reparameterisation trick
        e = tf.random_normal(self.mu.get_shape())
        x = self.mu + e * self.sigma
        return x

    def KL(self, p):
        KL = 0.5 * (tf.log(p.var) - tf.log(self.var) + self.var / p.var - 1. +
                    (self.mu - p.mu)**2 / p.var)
        return KL


class _NormPrior(_Normal):

    def __init__(self, dim, var, learn_var):
        mu = tf.zeros(dim)
        var = pos(tf.Variable(var)) if learn_var else var
        super().__init__(mu, var)


class _NormPosterior(_Normal):

    def __init__(self, dim, prior_var):
        mu = tf.Variable(tf.sqrt(prior_var) * tf.random_normal(dim))
        var = pos(tf.Variable(prior_var * tf.random_normal(dim)))
        super().__init__(mu, var)


class _MixPosterior:

    def __init__(self, dim, prior_var, K):
        self.comps = [_NormPosterior(dim, prior_var) for _ in range(K)]
        self.K = K

    def sample(self):
        # Sample randomly from one mixture component
        # NOT particularly efficient, or even workable....
        k = tf.multinomial([[np.log(1. / self.K)] * self.K], 1)[0][0]
        z = tf.zeros_like(self.comps[0].mu)
        sample = z
        for i, qk in enumerate(self.comps):
            sample += tf.cond(tf.equal(k, i), qk.sample, lambda: z)
        return sample

    def KL(self, p):
        """Lower bound on KL between a mixture and normal."""
        KL = 0.
        for qk in self.comps:
            lp = _log_norm(qk.mu, p.mu, p.var)
            tr = tf.reduce_sum(qk.var / p.var)
            lq = [_log_norm(qk.mu, qj.mu, qk.var + qj.var) - self.K
                  for qj in self.comps]
            h = tf.reduce_logsumexp(lq)
            KL += (tr / 2. - lp + h) / self.K
        return KL


def _l1_loss(X):
    l1 = tf.reduce_sum(tf.abs(X))
    return l1


# TODO: this is repeated in likelihoods (wihtout the sum)
def _log_norm(x, mu, var):
    ll = -0.5 * tf.reduce_sum(tf.log(2 * var * np.pi) + (x - mu)**2 / var)
    return ll


def _input_dim(X):
        input_dim = int(X[0].get_shape()[1])
        return input_dim
