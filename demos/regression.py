#! /usr/bin/env python3
"""This demo uses Aboleth for approximate Gaussian process regression."""
import logging

import numpy as np
import bokeh.plotting as bk
import bokeh.palettes as bp
import tensorflow as tf
# from sklearn.gaussian_process.kernels import Matern as kern
from sklearn.gaussian_process.kernels import RBF as kern

import aboleth as ab
from aboleth.likelihoods import Normal
from aboleth.datasets import gp_draws

# Set up a python logger so we can see the output of MonitoredTrainingSession
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Set up a consistent random seed in Aboleth so we get repeatable, but random
# results
RSEED = 666
ab.set_hyperseed(RSEED)

# Data settings
N = 1000  # Number of training points to generate
Ns = 400  # Number of testing points to generate
kernel = kern(length_scale=0.5)  # Kernel to use for making a random GP draw
true_noise = 0.1  # Add noise to the GP draws, to make things a little harder

# Model settings
n_samples = 5  # Number of random samples to get from an Aboleth net
n_pred_samples = 10  # This will give n_samples by n_pred_samples predictions
n_epochs = 200  # how many times to see the data for training
batch_size = 10  # mini batch size for stochastric gradients
config = tf.ConfigProto(device_count={'GPU': 0})  # Use GPU? 0 is no

# Model initialisation
variance = tf.Variable(1.)  # Likelihood variance initialisation, and learning
reg = 1.  # Initial weight prior variance, this is optimised later

# Random Fourier Features
# lenscale = tf.Variable(1.)  # learn the length scale
# kern = ab.RBF(lenscale=ab.pos(lenscale))  # keep the length scale positive

# Variational Fourier Features -- length-scale setting here is the "prior", we
# can choose to optimise this or not
lenscale = 1.
kern = ab.RBFVariational(lenscale=lenscale)  # This is VAR-FIXED kernel from
# Cutjar et. al. 2017

# This is how we make the "latent function" of a Gaussian process, here
# n_features controls how many random basis functions we use in the
# approximation. The more of these, the more accurate, but more costly
# computationally. "full" indicates we want a full-covariance matrix Gaussian
# posterior of the model weights. This is optional, but it does greatly improve
# the model uncertainty away from the data.
net = (
    ab.InputLayer(name="X", n_samples=n_samples) >>
    ab.RandomFourier(n_features=100, kernel=kern) >>
    ab.DenseVariational(output_dim=1, var=reg, full=True)
)


def main():
    """Run the demo."""
    n_iters = int(round(n_epochs * N / batch_size))
    print("Iterations = {}".format(n_iters))

    # Get training and testing data
    Xr, Yr, Xs, Ys = gp_draws(N, Ns, kern=kernel, noise=true_noise)

    # Prediction points
    Xq = np.linspace(-20, 20, Ns).astype(np.float32)[:, np.newaxis]
    Yq = np.linspace(-4, 4, Ns).astype(np.float32)[:, np.newaxis]

    # Set up the probability image query points
    Xi, Yi = np.meshgrid(Xq, Yq)
    Xi = Xi.astype(np.float32).reshape(-1, 1)
    Yi = Yi.astype(np.float32).reshape(-1, 1)

    _, D = Xr.shape

    # Name the "data" parts of the graph
    with tf.name_scope("Input"):
        # This function will make a TensorFlow queue for shuffling and batching
        # the data, and will run through n_epochs of the data.
        Xb, Yb = batch_training(Xr, Yr, n_epochs=n_epochs,
                                batch_size=batch_size)
        X_ = tf.placeholder_with_default(Xb, shape=(None, D))
        Y_ = tf.placeholder_with_default(Yb, shape=(None, 1))

    with tf.name_scope("Likelihood"):
        lkhood = Normal(variance=ab.pos(variance))  # Keep the var positive

    # This is where we build the actual GP model
    with tf.name_scope("Deepnet"):
        Phi, kl = net(X=X_)
        loss = ab.elbo(Phi, Y_, N, kl, lkhood)

    # Set up the trainig graph
    with tf.name_scope("Train"):
        optimizer = tf.train.AdamOptimizer()
        global_step = tf.train.create_global_step()
        train = optimizer.minimize(loss, global_step=global_step)

    # This is used for building the predictive density image
    with tf.name_scope("Predict"):
        logprob = lkhood(Y_, Phi)

    # Logging learning progress
    log = tf.train.LoggingTensorHook(
        {'step': global_step, 'loss': loss},
        every_n_iter=1000
    )

    # This is the main training "loop"
    with tf.train.MonitoredTrainingSession(
            config=config,
            save_summaries_steps=None,
            save_checkpoint_secs=None,
            hooks=[log]
    ) as sess:
        try:
            while not sess.should_stop():
                sess.run(train)
        except tf.errors.OutOfRangeError:
            print('Input queues have been exhausted!')
            pass

        # Prediction, the [[None]] is to stop the default placeholder queue
        Ey = ab.predict_samples(Phi, feed_dict={X_: Xq, Y_: [[None]]},
                                n_groups=n_pred_samples, session=sess)
        logPY = ab.predict_expected(logprob, feed_dict={Y_: Yi, X_: Xi},
                                    n_groups=n_pred_samples, session=sess)

    Eymean = Ey.mean(axis=0)  # Average samples to get mean predicted funtion
    Py = np.exp(logPY.reshape(Ns, Ns))  # Turn log-prob into prob

    # Plot
    im_min = np.amin(Py)
    im_size = np.amax(Py) - im_min
    img = (Py - im_min) / im_size
    f = bk.figure(tools='pan,box_zoom,reset', sizing_mode='stretch_both')
    f.image(image=[img], x=-20., y=-4., dw=40., dh=8,
            palette=bp.Plasma256)
    f.circle(Xr.flatten(), Yr.flatten(), fill_color='blue', legend='Training')
    f.line(Xs.flatten(), Ys.flatten(), line_color='blue', legend='Truth')
    for y in Ey:
        f.line(Xq.flatten(), y.flatten(), line_color='red', legend='Samples',
               alpha=0.2)
    f.line(Xq.flatten(), Eymean.flatten(), line_color='green', legend='Mean')
    bk.show(f)


def batch_training(X, Y, batch_size, n_epochs):
    """Batch training queue convenience function."""
    X = tf.train.limit_epochs(X, n_epochs, name="X_lim")
    Y = tf.train.limit_epochs(Y, n_epochs, name="Y_lim")
    X_batch, Y_batch = tf.train.shuffle_batch([X, Y], batch_size, 100, 1,
                                              enqueue_many=True, seed=RSEED)
    return X_batch, Y_batch


if __name__ == "__main__":
    main()
