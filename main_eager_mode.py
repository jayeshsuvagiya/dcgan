"""Eager mode, single GPU
"""

import os, time, multiprocessing
import numpy as np
import tensorflow as tf
tf.enable_eager_execution() # for TF 1.13
import tensorlayer as tl
from glob import glob
from utils import get_celebA, flags # get_image
from model import get_generator, get_discriminator

FLAGS = flags.FLAGS
num_tiles = int(np.sqrt(FLAGS.sample_size))

def train():
    images, images_path = get_celebA(FLAGS.output_size, FLAGS.n_epoch, FLAGS.batch_size)
    G = get_generator([None, FLAGS.z_dim])
    D = get_discriminator([None, FLAGS.output_size, FLAGS.output_size, FLAGS.c_dim])

    G.train()
    D.train()

    d_optimizer = tf.train.AdamOptimizer(FLAGS.learning_rate, beta1=FLAGS.beta1)
    g_optimizer = tf.train.AdamOptimizer(FLAGS.learning_rate, beta1=FLAGS.beta1)

    n_step_epoch = int(len(images_path) // FLAGS.batch_size)

    for step, batch_images in enumerate(images):
        step_time = time.time()
        with tf.GradientTape(persistent=True) as tape:
            z = tf.contrib.distributions.Normal(0., 1.).sample([FLAGS.batch_size, FLAGS.z_dim]) #tf.placeholder(tf.float32, [None, z_dim], name='z_noise')
            d_logits = D(G(z))
            d2_logits = D(batch_images)
            # discriminator: real images are labelled as 1
            d_loss_real = tl.cost.sigmoid_cross_entropy(d2_logits, tf.ones_like(d2_logits), name='dreal')
            # discriminator: images from generator (fake) are labelled as 0
            d_loss_fake = tl.cost.sigmoid_cross_entropy(d_logits, tf.zeros_like(d_logits), name='dfake')
            # combined loss for updating discriminator
            d_loss = d_loss_real + d_loss_fake
            # generator: try to fool discriminator to output 1
            g_loss = tl.cost.sigmoid_cross_entropy(d_logits, tf.ones_like(d_logits), name='gfake')

        grad = tape.gradient(g_loss, G.weights)
        g_optimizer.apply_gradients(zip(grad, G.weights))
        grad = tape.gradient(d_loss, D.weights)
        d_optimizer.apply_gradients(zip(grad, D.weights))
        del tape

        print("Epoch: [{}/{}] [{}/{}] took: {:3f}, d_loss: {:5f}, g_loss: {:5f}".format(step//n_step_epoch, FLAGS.n_epoch, step, n_step_epoch, time.time()-step_time, d_loss, g_loss))
        if np.mod(step, FLAGS.save_step) == 0:
            G.save_weights('{}/G.npz'.format(FLAGS.checkpoint_dir), format='npz')
            D.save_weights('{}/D.npz'.format(FLAGS.checkpoint_dir), format='npz')
            result = G(z)
            tl.visualize.save_images(result.numpy(), [num_tiles, num_tiles], '{}/train_{:02d}_{:04d}.png'.format(FLAGS.sample_dir, step//n_step_epoch, step))

if __name__ == '__main__':
    train()
