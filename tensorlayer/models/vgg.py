#! /usr/bin/python
# -*- coding: utf-8 -*-
"""
VGG for ImageNet.

Introduction
----------------
VGG is a convolutional neural network model proposed by K. Simonyan and A. Zisserman
from the University of Oxford in the paper “Very Deep Convolutional Networks for
Large-Scale Image Recognition”  . The model achieves 92.7% top-5 test accuracy in ImageNet,
which is a dataset of over 14 million images belonging to 1000 classes.

Download Pre-trained Model
----------------------------
- Model weights in this example - vgg16_weights.npz : http://www.cs.toronto.edu/~frossard/post/vgg16/
- Model weights in this example - vgg19.npy : https://media.githubusercontent.com/media/tensorlayer/pretrained-models/master/models/
- Caffe VGG 16 model : https://gist.github.com/ksimonyan/211839e770f7b538e2d8#file-readme-md
- Tool to convert the Caffe models to TensorFlow's : https://github.com/ethereon/caffe-tensorflow

Note
------
- For simplified CNN layer see "Convolutional layer (Simplified)"
in read the docs website.
- When feeding other images to the model be sure to properly resize or crop them
beforehand. Distorted images might end up being misclassified. One way of safely
feeding images of multiple sizes is by doing center cropping.
"""

import sys

import os
import numpy as np
import tensorflow as tf
from tensorflow.python.eager import context

from tensorlayer import logging

from tensorlayer.layers import Conv2d
from tensorlayer.layers import Dense
from tensorlayer.layers import Flatten
from tensorlayer.layers import Input
from tensorlayer.layers import MaxPool2d
from tensorlayer.layers import LayerList
from tensorlayer.layers import BatchNorm
from tensorlayer.models import Model

from tensorlayer.files import maybe_download_and_extract
from tensorlayer.files import assign_weights


__all__ = [
    'VGG', 'vgg16', 'vgg19',
#    'vgg11', 'vgg11_bn', 'vgg13', 'vgg13_bn', 'vgg16', 'vgg16_bn',
#    'vgg19_bn', 'vgg19',
]

layer_names = [
    ['conv1_1', 'conv1_2'],
    'pool1',
    ['conv2_1', 'conv2_2'],
    'pool2',
    ['conv3_1', 'conv3_2', 'conv3_3', 'conv3_4'],
    'pool3',
    ['conv4_1', 'conv4_2', 'conv4_3', 'conv4_4'],
    'pool4',
    ['conv5_1', 'conv5_2', 'conv5_3', 'conv5_4'],
    'pool5',
    'flatten', 'fc1_relu', 'fc2_relu', 'outputs'
]

cfg = {
    'A': [[64], 'M', [128], 'M', [256, 256], 'M', [512, 512], 'M', [512, 512], 'M', 'F', 'fc1', 'fc2', 'O'],
    'B': [[64, 64], 'M', [128, 128], 'M', [256, 256], 'M', [512, 512], 'M', [512, 512], 'M', 'F', 'fc1', 'fc2', 'O'],
    'D': [[64, 64], 'M', [128, 128], 'M', [256, 256, 256], 'M', [512, 512, 512], 'M', [512, 512, 512], 'M', 'F', 'fc1', 'fc2', 'O'],
    'E': [[64, 64], 'M', [128, 128], 'M', [256, 256, 256, 256], 'M', [512, 512, 512, 512], 'M', [512, 512, 512, 512], 'M', 'F', 'fc1', 'fc2', 'O'],
}

mapped_cfg = {
    'vgg11': 'A', 'vgg11_bn': 'A',
    'vgg13': 'B', 'vgg13_bn': 'B',
    'vgg16': 'D', 'vgg16_bn': 'D',
    'vgg19': 'E', 'vgg19_bn': 'E'
}

model_urls = {
    'vgg16': 'http://www.cs.toronto.edu/~frossard/vgg16/',
    'vgg19': 'https://media.githubusercontent.com/media/tensorlayer/pretrained-models/master/models/'
}

model_saved_name = {
    'vgg16': 'vgg16_weights.npz',
    'vgg19': 'vgg19.npy'
}

class VGG(Model):
    """Pre-trained VGG model.

    Parameters
    ------------
    end_with : str
        The end point of the model. Default ``fc3_relu`` i.e. the whole model.

    Examples
    ---------
    Classify ImageNet classes with VGG16, see `tutorial_models_vgg.py <https://github.com/tensorlayer/tensorlayer/blob/master/example/tutorial_models_vgg.py>`__


    >>> # get the whole model
    >>> vgg = tl.models.vgg.vgg16()
    >>> # restore pre-trained VGG parameters
    >>> vgg.restore_weights()
    >>> # use for inferencing
    >>> probs = tf.nn.softmax(vgg.outputs)

    Extract features with VGG16 and Train a classifier with 100 classes

    >>> # get VGG without the last layer
    >>> vgg = tl.models.vgg.vgg16(end_with='fc2_relu')
    >>> # add one more layer
    >>> net = tl.layers.DenseLayer(vgg, 100, name='out')
    >>> # restore pre-trained VGG parameters
    >>> vgg.restore_weights()
    >>> # train your own classifier (only update the last layer)
    >>> train_params = tl.layers.get_variables_with_name('out')

    Reuse model

    >>> # get VGG without the last layer
    >>> vgg1 = tl.models.vgg.vgg16(end_with='fc2_relu')
    >>> # reuse the parameters of vgg1 with different input
    >>> vgg2 = tl.models.vgg.vgg16(end_with='fc2_relu', reuse=True)
    >>> # restore pre-trained VGG parameters (as they share parameters, we don’t need to restore vgg2)
    >>> vgg1.restore_weights()

    """

    def __init__(self, layer_type, batch_norm=False, end_with='outputs', name=None):
        super(VGG, self).__init__()
        self.end_with = end_with

        self.innet = Input([None, 224, 224, 3])

        config = cfg[mapped_cfg[layer_type]]
        self.layers = make_layers(config, batch_norm, end_with)

    def forward(self, inputs):
        """
        inputs : tensor
            Shape [None, 224, 224, 3], value range [0, 1].
        """
        outputs = inputs * 255.0
        mean = tf.constant([123.68, 116.779, 103.939], dtype=tf.float32, shape=[1, 1, 1, 3], name='img_mean')
        outputs = outputs - mean

        out = self.innet(outputs)
        out = self.layers(out)
        return out.outputs


def make_layers(config, batch_norm=False, end_with='outputs'):
    layer_list = []
    is_end = False
    for layer_group_idx, layer_group in enumerate(config):
        if isinstance(layer_group, list):
            for idx, layer in enumerate(layer_group):
                layer_name = layer_names[layer_group_idx][idx]
                n_filter = layer
                if idx == 0:
                    if layer_group_idx > 0:
                        in_channels = config[layer_group_idx - 2][-1]
                    else:
                        in_channels = 3
                else:
                    in_channels = layer
                layer_list.append(Conv2d(n_filter=n_filter, filter_size=(3, 3), strides=(1, 1), act=tf.nn.relu,
                                         padding='SAME', in_channels=in_channels, name=layer_name))
                if batch_norm:
                    layer_list.append(BatchNorm())
                if layer_name == end_with:
                    is_end = True
                    break
        else:
            layer_name = layer_names[layer_group_idx]
            if layer_group == 'M':
                layer_list.append(MaxPool2d(filter_size=(2, 2), strides=(2, 2), padding='SAME', name=layer_name))
            elif layer_group == 'O':
                layer_list.append(Dense(n_units=1000, in_channels=4096, name=layer_name))
            elif layer_group == 'F':
                layer_list.append(Flatten(name='flatten'))
            elif layer_group == 'fc1':
                layer_list.append(Dense(n_units=4096, act=tf.nn.relu, in_channels=512 * 7 * 7, name=layer_name))
            elif layer_group == 'fc2':
                layer_list.append(Dense(n_units=4096, act=tf.nn.relu, in_channels=4096, name=layer_name))
            if layer_name == end_with:
                is_end = True
        if is_end:
            break
    return LayerList(layer_list)


def restore_model(model, layer_type, sess=None):
    logging.info("Restore pre-trained weights")
    # download weights
    maybe_download_and_extract(
        model_saved_name[layer_type], 'models', model_urls[layer_type]
    )
    weights = []
    if layer_type == 'vgg16':
        npz = np.load(os.path.join('models', model_saved_name[layer_type]))
        # get weight list
        for val in sorted(npz.items()):
            logging.info("  Loading weights %s in %s" % (str(val[1].shape), val[0]))
            weights.append(val[1])
            if len(model.weights) == len(weights):
                break
    elif layer_type == 'vgg19':
        npz = np.load(os.path.join('models', model_saved_name[layer_type]), encoding='latin1').item()
        # get weight list
        for val in sorted(npz.items()):
            logging.info("  Loading %s in %s" % (str(val[1][0].shape), val[0]))
            logging.info("  Loading %s in %s" % (str(val[1][1].shape), val[0]))
            weights.extend(val[1])
            if len(model.weights) == len(weights):
                break
    # assign weight values
    assign_weights(sess, weights, model)
    del weights


def VGG_static(layer_type, batch_norm=False, end_with='outputs', name=None):
    ni = Input([None, 224, 224, 3])

    config = cfg[mapped_cfg[layer_type]]
    layers = make_layers(config, batch_norm, end_with)

    nn = layers(ni)

    M = Model(inputs=ni, outputs=nn, name=name)
    return M


def vgg16(pretrained=False, end_with='outputs', sess=None):
    if context.default_execution_mode == context.EAGER_MODE:
        model = VGG(layer_type='vgg16', batch_norm=False, end_with=end_with)
    else:
        model = VGG_static(layer_type='vgg16', batch_norm=False, end_with=end_with)
    if pretrained:
        # model.restore_weights()
        restore_model(model, layer_type='vgg16', sess=sess)
    return model


def vgg19(pretrained=False, end_with='outputs', sess=None):
    if context.default_execution_mode == context.EAGER_MODE:
        model = VGG(layer_type='vgg19', batch_norm=False, end_with=end_with)
    else:
        model = VGG_static(layer_type='vgg19', batch_norm=False, end_with=end_with)
    if pretrained:
        # model.restore_weights()
        restore_model(model, layer_type='vgg19', sess=sess)
    return model

# models without pretrained parameters
'''def vgg11(pretrained=False, end_with='outputs'):
    model = VGG(layer_type='vgg11', batch_norm=False, end_with=end_with)
    if pretrained:
        model.restore_weights()
    return model


def vgg11_bn(pretrained=False, end_with='outputs'):
    model = VGG(layer_type='vgg11_bn', batch_norm=True, end_with=end_with)
    if pretrained:
        model.restore_weights()
    return model


def vgg13(pretrained=False, end_with='outputs'):
    model = VGG(layer_type='vgg13', batch_norm=False, end_with=end_with)
    if pretrained:
        model.restore_weights()
    return model


def vgg13_bn(pretrained=False, end_with='outputs'):
    model = VGG(layer_type='vgg13_bn', batch_norm=True, end_with=end_with)
    if pretrained:
        model.restore_weights()
    return model


def vgg16_bn(pretrained=False, end_with='outputs'):
    model = VGG(layer_type='vgg16_bn', batch_norm=True, end_with=end_with)
    if pretrained:
        model.restore_weights()
    return model


def vgg19_bn(pretrained=False, end_with='outputs'):
    model = VGG(layer_type='vgg19_bn', batch_norm=True, end_with=end_with)
    if pretrained:
        model.restore_weights()
    return model
'''

