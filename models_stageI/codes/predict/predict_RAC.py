import random
import pandas as pd
import numpy as np
from itertools import chain
import math
import keras
import tensorflow as tf
from keras import regularizers,constraints,initializers
from keras import backend as K
from keras.layers import *
from keras.models import Model
from keras.models import load_model
from keras.optimizers import SGD,Adam
from keras.engine import Layer, InputSpec
from keras.metrics import binary_accuracy
from keras.initializers import Ones, Zeros
from sklearn.model_selection import GridSearchCV
from keras.wrappers import scikit_learn
from sklearn import metrics
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import LabelEncoder
from keras.utils import to_categorical
from sklearn.preprocessing import MinMaxScaler
import sys

def Onehotcode(sequence):

    alphabet = np.array(['A', 'G', 'U', 'C','N'])

    line = list(sequence.strip('\n'));

    seq = np.array(line, dtype = '|U1').reshape(-1,1);
    seq_data = []

    for i in range(len(seq)):
        if seq[i] == 'A':
            seq_data.append([1,0,0,0])
        if seq[i] == 'U':
            seq_data.append([0,1,0,0])
        if seq[i] == 'C':
            seq_data.append([0,0,1,0])
        if seq[i] == 'G':
            seq_data.append([0,0,0,1])
        if seq[i] == 'N':
            seq_data.append([0,0,0,0])

    return np.array(seq_data).reshape(-1,4)

def readfa(filename):
    data,supportNum = [],[]
    with open(filename,'r') as f:
        for line in f:
            line = line.strip('\n')
            if line.startswith('>'):
                x = line.split('|')
                supportNum.append(float(x[1]))
            else:
                ohdata = Onehotcode(line)
                data.append(ohdata)
    return data,supportNum

def getseqs(filename):
    seqs = []
    with open(filename,'r') as f:
        tmpseq = ''
        for line in f:
            if line.startswith('>'):
                if len(tmpseq) > 0:
                    seqs.append(tmpseq)
                    tmpseq = ''
            else:
                tmpseq = tmpseq + line.strip()
        if len(tmpseq) > 0:
            seqs.append(tmpseq)
    return seqs

def getSubStrIndex(str1,pattern):
    n = str1.count(pattern)
    indexes=[]
    if n > 0:
        idx = str1.find(pattern)
        while idx != -1:
            indexes.append(idx)
            idx = str1.find(pattern,idx+1)
    return indexes

def getsegs(seq):
    indexes1 = getSubStrIndex(seq,'AAC')
    indexes2 = getSubStrIndex(seq,'GAC')
    indexes = indexes1 + indexes2
    n = len(indexes)
    indexes.sort()
    segs = []
    poss = []
    for index in indexes:
        start = max([0,index+1-300])
        tmpseg = 'N'*(300-index-1) + seq[start:(index+1+301)] + 'N'*(index+1+301-len(seq))
        segs.append(tmpseg)
        poss.append(index+2)
    return segs,poss


class GroupNormalization(Layer):
    def __init__(self,groups=32,axis=-1,epsilon=1e-5,center=True,scale=True,beta_initializer='zeros',gamma_initializer='ones',beta_regularizer=None,
                 gamma_regularizer=None,beta_constraint=None,gamma_constraint=None,**kwargs):
        super(GroupNormalization, self).__init__(**kwargs)
        self.supports_masking = True
        self.groups = groups
        self.axis = axis
        self.epsilon = epsilon
        self.center = center
        self.scale = scale
        self.beta_initializer = initializers.get(beta_initializer)
        self.gamma_initializer = initializers.get(gamma_initializer)
        self.beta_regularizer = regularizers.get(beta_regularizer)
        self.gamma_regularizer = regularizers.get(gamma_regularizer)
        self.beta_constraint = constraints.get(beta_constraint)
        self.gamma_constraint = constraints.get(gamma_constraint)

    def build(self, input_shape):
        dim = input_shape[self.axis]

        if dim is None:
            raise ValueError('Axis '+str(self.axis)+' of input tensor should have a defined dimension but the layer received an input with shape '+str(input_shape)+'.')

        if dim < self.groups:
            raise ValueError('Number of groups ('+str(self.groups)+') cannot be more than the number of channels ('+str(dim)+').')

        if dim % self.groups != 0:
            raise ValueError('Number of groups ('+str(self.groups)+') must be a multiple of the number of channels ('+str(dim)+').')

        self.input_spec = InputSpec(ndim=len(input_shape),axes={self.axis: dim})
        shape = (dim,)

        if self.scale:
            self.gamma = self.add_weight(shape=shape,name='gamma',initializer=self.gamma_initializer,regularizer=self.gamma_regularizer,constraint=self.gamma_constraint)
        else:
            self.gamma = None

        if self.center:
            self.beta = self.add_weight(shape=shape,name='beta',initializer=self.beta_initializer,regularizer=self.beta_regularizer,constraint=self.beta_constraint)
        else:
            self.beta = None

        self.built = True

    def call(self, inputs, **kwargs):
        input_shape = K.int_shape(inputs)
        tensor_input_shape = K.shape(inputs)

        # Prepare broadcasting shape.
        reduction_axes = list(range(len(input_shape)))
        del reduction_axes[self.axis]
        broadcast_shape = [1] * len(input_shape)
        broadcast_shape[self.axis] = input_shape[self.axis] // self.groups
        broadcast_shape.insert(1, self.groups)

        reshape_group_shape = K.shape(inputs)
        group_axes = [reshape_group_shape[i] for i in range(len(input_shape))]
        group_axes[self.axis] = input_shape[self.axis] // self.groups
        group_axes.insert(1, self.groups)

        # reshape inputs to new group shape
        group_shape = [group_axes[0], self.groups] + group_axes[2:]
        group_shape = K.stack(group_shape)
        inputs = K.reshape(inputs, group_shape)

        group_reduction_axes = list(range(len(group_axes)))
        group_reduction_axes = group_reduction_axes[2:]

        mean = K.mean(inputs, axis=group_reduction_axes, keepdims=True)
        variance = K.var(inputs, axis=group_reduction_axes, keepdims=True)
        inputs = (inputs - mean) / (K.sqrt(variance + self.epsilon))

        # prepare broadcast shape
        inputs = K.reshape(inputs, group_shape)
        outputs = inputs

        # In this case we must explicitly broadcast all parameters.
        if self.scale:
            broadcast_gamma = K.reshape(self.gamma, broadcast_shape)
            outputs = outputs * broadcast_gamma

        if self.center:
            broadcast_beta = K.reshape(self.beta, broadcast_shape)
            outputs = outputs + broadcast_beta

        outputs = K.reshape(outputs, tensor_input_shape)

        return outputs

    def get_config(self):
        config = {'groups': self.groups,'axis': self.axis,'epsilon': self.epsilon,'center': self.center,'scale': self.scale,
            'beta_initializer': initializers.serialize(self.beta_initializer),'gamma_initializer': initializers.serialize(self.gamma_initializer),
            'beta_regularizer': regularizers.serialize(self.beta_regularizer),'gamma_regularizer': regularizers.serialize(self.gamma_regularizer),
            'beta_constraint': constraints.serialize(self.beta_constraint),'gamma_constraint': constraints.serialize(self.gamma_constraint)}
        base_config = super(GroupNormalization, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))

    def compute_output_shape(self, input_shape):
        return input_shape

class Position_Embedding(Layer):

    def __init__(self, size=None, mode='sum', **kwargs):
        self.size = size  #
        self.mode = mode
        super(Position_Embedding, self).__init__(**kwargs)

    def call(self, x):
        if (self.size == None) or (self.mode == 'sum'):
            self.size = int(x.shape[-1])
        batch_size, seq_len = K.shape(x)[0], K.shape(x)[1]
        position_j = 1. / K.pow(10000., 2 * K.arange(self.size / 2, dtype='float32') / self.size)
        position_j = K.expand_dims(position_j, 0)
        position_i = K.cumsum(K.ones_like(x[:, :, 0]), 1) - 1  #
        position_i = K.expand_dims(position_i, 2)
        position_ij = K.dot(position_i, position_j)
        position_ij = K.concatenate([K.cos(position_ij), K.sin(position_ij)], 2)
        if self.mode == 'sum':
            return position_ij + x
        elif self.mode == 'concat':
            return K.concatenate([position_ij, x], 2)

    def compute_output_shape(self, input_shape):
        if self.mode == 'sum':
            return input_shape
        elif self.mode == 'concat':
            return (input_shape[0], input_shape[1], input_shape[2] + self.size)

class MulitHeadAttention(Layer):

    def __init__(self, nb_head = 2, size_per_head = 8, **kwargs):
        self.nb_head = nb_head
        self.size_per_head = size_per_head
        self.output_dim = nb_head * size_per_head

        super(MulitHeadAttention, self).__init__(**kwargs)

    def build(self, input_shape):
        print(input_shape)
        self.WQ = self.add_weight(name='WQ', shape=(input_shape[0][-1], self.output_dim), initializer='glorot_uniform', trainable=True)
        self.WK = self.add_weight(name='WK', shape=(input_shape[1][-1], self.output_dim), initializer='glorot_uniform', trainable=True)
        self.WV = self.add_weight(name='WV', shape=(input_shape[2][-1], self.output_dim), initializer='glorot_uniform', trainable=True)

        super(MulitHeadAttention, self).build(input_shape)

    def Mask(self, inputs, seq_len, mode='mul'):

        if seq_len == None:
            return inputs
        else:
            mask = K.one_hot(seq_len[:, 0], K.shape(inputs)[1])
            mask = 1 - K.cumsum(mask, 1)
            for _ in range(len(inputs.shape) - 2):
                mask = K.expand_dims(mask, 2)
            if mode == 'mul':
                return inputs * mask
            if mode == 'add':
                return inputs - (1 - mask) * 1e12

    def call(self, x):

        if len(x) == 3:
            Q_seq, K_seq, V_seq = x
            Q_len, V_len = None, None
        elif len(x) == 5:
            Q_seq, K_seq, V_seq, Q_len, V_len = x

        Q_seq = K.dot(Q_seq, self.WQ)
        Q_seq = K.reshape(Q_seq, (-1, K.shape(Q_seq)[1], self.nb_head, self.size_per_head))
        Q_seq = K.permute_dimensions(Q_seq, (0, 2, 1, 3))
        K_seq = K.dot(K_seq, self.WK)
        K_seq = K.reshape(K_seq, (-1, K.shape(K_seq)[1], self.nb_head, self.size_per_head))
        K_seq = K.permute_dimensions(K_seq, (0, 2, 1, 3))
        V_seq = K.dot(V_seq, self.WV)
        V_seq = K.reshape(V_seq, (-1, K.shape(V_seq)[1], self.nb_head, self.size_per_head))
        V_seq = K.permute_dimensions(V_seq, (0, 2, 1, 3))

        A = K.batch_dot(Q_seq, K_seq, axes=[3, 3]) / self.size_per_head ** 0.5
        A = K.permute_dimensions(A, (0, 3, 2, 1))
        A = self.Mask(A, V_len, 'add')
        A = K.permute_dimensions(A, (0, 3, 2, 1))
        A = K.softmax(A)

        O_seq = K.batch_dot(A, V_seq, axes=[3, 2])
        O_seq = K.permute_dimensions(O_seq, (0, 2, 1, 3))
        O_seq = K.reshape(O_seq, (-1, K.shape(O_seq)[1], self.output_dim))
        O_seq = self.Mask(O_seq, Q_len, 'mul')

        return O_seq

    def compute_output_shape(self, input_shape):
        return (input_shape[0][0], input_shape[0][1], self.output_dim)

    def get_config(self):
        config = {'output_dim': self.output_dim, 'nb_head' : self.nb_head, 'size_per_head' : self.size_per_head}
        base_config = super(MulitHeadAttention, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))

class PositionWiseFeedForward(object):
    # def __init__(self, d_model=512, d_ff=2048, **kwargs):
    def __init__(self, d_model = 16, d_ff = 16, **kwargs):
        self._d_model = d_model
        self._d_ff = d_ff

        self._conv1 = Conv1D(self._d_ff, kernel_size=1, activation="elu")
        self._conv2 = Conv1D(self._d_model, kernel_size=1)
    
    def __call__(self, x):
        intermediate_x = self._conv1(x)
        return self._conv2(intermediate_x)

class LayerNormalization(Layer):

    def __init__(self, epsilon=1e-8, **kwargs):
        self._epsilon = epsilon
        super(LayerNormalization, self).__init__(**kwargs)
    
    def compute_output_shape(self, input_shape):
        return input_shape
    
    def build(self, input_shape):
        self._g = self.add_weight(name='gain', shape=(input_shape[-1],),initializer=Ones(),trainable=True)
        self._b = self.add_weight(name='bias', shape=(input_shape[-1],),initializer=Zeros(),trainable=True)
        
    def call(self, x):
        mean = K.mean(x, axis=-1)
        std = K.std(x, axis=-1)

        if len(x.shape) == 3:
            mean = K.permute_dimensions(K.repeat(mean, x.shape.as_list()[-1]),[0,2,1])
            std = K.permute_dimensions(K.repeat(std, x.shape.as_list()[-1]),[0,2,1])
            
        elif len(x.shape) == 2:
            mean = K.reshape(K.repeat_elements(mean, x.shape.as_list()[-1], 0),(-1, x.shape.as_list()[-1]))
            std = K.reshape(K.repeat_elements(mean, x.shape.as_list()[-1], 0),(-1, x.shape.as_list()[-1]))
        
        return self._g * (x - mean) / (std + self._epsilon) + self._b

def transformerBlock(inputs, head, size_per_head, n_one, n_two):

    x1 = MulitHeadAttention(head, size_per_head)([inputs,inputs,inputs])
    y1 = Add()([x1, inputs])
    y1 = LayerNormalization()(y1)
    x2 = PositionWiseFeedForward(n_one, n_two)(y1)
    y2 = Add()([y1, x2])
    y2 = LayerNormalization()(y2)
    return y2;

def CNN_model():
    input_shape = (601,4)
    inputs = Input(shape = input_shape)
    internel = inputs
    internel = Conv1D(filters= 16, kernel_size= 10, padding = 'valid', kernel_regularizer = regularizers.l2(1e-4), bias_regularizer = regularizers.l2(1e-4))(internel)
    internel = GroupNormalization(groups = 4, axis = -1)(internel)
    internel = Activation('elu')(internel)
    x = internel
    x = AveragePooling1D(pool_size = 15)(x)
    x = Flatten()(x)
    x = Dropout(0.6)(x)
    x = Dense(64, kernel_regularizer = regularizers.l2(1e-4),bias_regularizer = regularizers.l2(1e-4))(x)
    x = Activation('elu')(x)
    outLayer_1 = Dense(2, activation='softmax',name='out1')(x)
    outLayer_2 = Dense(1,activation='elu',name='out2')(x)
    model = Model(input=[inputs], output=[outLayer_1,outLayer_2])
    #model.compile(loss='categorical_crossentropy', optimizer= SGD(momentum = 0.95, lr = 0.01, nesterov=True), metrics=['acc'])
    model.compile(loss={'out1':'categorical_crossentropy','out2':'logcosh'}, optimizer= SGD(momentum = 0.95, lr = 0.01, nesterov=True), metrics={'out1':'acc','out2':'mae'})
    #print(model.summary())
    return model

def LSTM_model():
    input_shape = (601,4)
    inputs = Input(shape = input_shape)
    internel = inputs
    internel = Conv1D(filters= 16, kernel_size= 10, padding = 'valid', kernel_regularizer = regularizers.l2(1e-4), bias_regularizer = regularizers.l2(1e-4))(internel)
    internel = GroupNormalization(groups = 4, axis = -1)(internel)
    internel = Activation('elu')(internel)
    x = internel
    x = Bidirectional(LSTM(units = 8, return_sequences = True))(x)
    x = AveragePooling1D(pool_size = 15)(x)
    x = Flatten()(x)
    x = Dropout(0.6)(x)
    x = Dense(64, kernel_regularizer = regularizers.l2(1e-4),bias_regularizer = regularizers.l2(1e-4))(x)
    x = Activation('elu')(x)
    outLayer_1 = Dense(2, activation='softmax',name='out1')(x)
    outLayer_2 = Dense(1,activation='elu',name='out2')(x)
    model = Model(input=[inputs], output=[outLayer_1,outLayer_2])
    #model.compile(loss='categorical_crossentropy', optimizer= SGD(momentum = 0.95, lr = 0.001, nesterov=True), metrics=['acc'])
    model.compile(loss={'out1':'categorical_crossentropy','out2':'logcosh'}, optimizer= SGD(momentum = 0.95, lr = 0.01, nesterov=True), metrics={'out1':'acc','out2':'mae'})
    return model

def Transformer_model():

    input_shape = (601,4)
    inputs = Input(shape = input_shape)
    internel = inputs
    internel = Conv1D(filters= 16, kernel_size= 10, padding = 'valid', kernel_regularizer = regularizers.l2(1e-4), bias_regularizer = regularizers.l2(1e-4))(internel)
    internel = GroupNormalization(groups = 4, axis = -1)(internel)
    internel = Activation('elu')(internel)
    x = internel
    x= Position_Embedding()(x)
    x = transformerBlock(x, 2, 8, 16, 16);
    x = AveragePooling1D(pool_size =15)(x)
    x = Flatten()(x)
    x = Dropout(0.6)(x)
    x = Dense(64, kernel_regularizer = regularizers.l2(1e-4),bias_regularizer = regularizers.l2(1e-4))(x)
    x = Activation('elu')(x)
    outLayer_1 = Dense(2, activation='softmax',name='out1')(x)
    outLayer_2 = Dense(1,activation='elu',name='out2')(x)
    model = Model(input=[inputs], output=[outLayer_1,outLayer_2])
    #model.compile(loss='categorical_crossentropy', optimizer= SGD(momentum = 0.95, lr = 0.01, nesterov=True), metrics=['acc'])
    model.compile(loss={'out1':'categorical_crossentropy','out2':'logcosh'}, optimizer= SGD(momentum = 0.95, lr = 0.01, nesterov=True), metrics={'out1':'acc','out2':'mae'})
    return model

def my_score(y_pred,y_true):
    y_pred = y_pred[:,1]
    y_true = y_true[:,1]
    y_pred2= np.around(y_pred)
    TN,FP,FN,TP = metrics.confusion_matrix(y_true, y_pred2).ravel()
    acc = metrics.accuracy_score(y_true, y_pred2)
    MCC=metrics.matthews_corrcoef(y_true, y_pred2)
    auroc=metrics.roc_auc_score(y_true, y_pred)
    precision, recall, _thresholds = metrics.precision_recall_curve(y_true, y_pred)
    auprc = metrics.auc(recall, precision)
    Specificity =float(TN) / float(TN + FP)
    Sensitivity = float(TP) / float(TP + FN)

    return TN,FP,FN,TP,Specificity,Sensitivity,acc,MCC,auroc,auprc

if __name__ == "__main__":
    seed = 2020
    np.random.seed(seed)
    fastafile = sys.argv[1]
    modelpath = sys.argv[2]
    seqs = getseqs(fastafile)
    model = LSTM_model()
    model.load_weights(modelpath)
    seqids = []
    allposs = []
    test = []
    for seqid in range(len(seqs)):
        tmpsegs,tmposs = getsegs(seqs[seqid])
        allposs = allposs + tmposs
        for seg in tmpsegs:
            seqids.append(seqid)
            test.append(Onehotcode(seg))
    
    test = np.array(test)
    y_pred_cls,y_pred_reg = model.predict(test)
    outfile = sys.argv[3]
    output = open(outfile,'w')
    output.write("seqid\t    pos\t        probability\t        confidence\n")
    for i in range(len(allposs)):
        output.write('%5d\t  %5d\t%19.3f\t%18.3f\n' % (seqids[i],allposs[i],y_pred_cls[i,1],y_pred_reg[i]))
    output.close()
