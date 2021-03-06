# Neural Network Setup

from keras.models import Sequential
from keras.layers import Bidirectional, Dense, Masking
from keras.layers import LSTM, TimeDistributed
import keras.backend as backend
from keras.callbacks import Callback
import numpy as np

from global_vars import *

# Keras Callback to produce a confusion matrix in addition to the accuracy
# We can print the confusion matrix after every epoch
class ConfusionMatrix(Callback):
    def __init__(self, print_confusion=False):
        super(Callback, self).__init__()
        self.print_confusion = print_confusion

    def on_epoch_end(self, epoch, logs={}):
        if self.print_confusion:
            mask = np.sum(self.validation_data[1], axis=2)
            y_true_labels = mask * (np.argmax(self.validation_data[1], axis=2) + 1)
            raw_predictions = self.model.predict(self.validation_data[0])
            y_pred_labels = mask * (np.argmax(raw_predictions, axis=2) + 1)
            confusion = np.zeros((OUTPUT_DIM, OUTPUT_DIM))
            for i in range(y_true_labels.shape[0]):
                for j in range(y_true_labels.shape[1]):
                    if int(y_true_labels[i, j]) == 0:
                        break
                    true_idx = int(y_true_labels[i, j]) - 1
                    pred_idx = int(y_pred_labels[i, j]) - 1
                    confusion[true_idx][pred_idx] += 1
            print '\nConfusion Matrix on Validation Data'
            print confusion.astype(int)

# This accuracy function takes into account the boolean mask and accounts
# for the varying lengths of the protein sequences
def truncated_accuracy(y_true, y_predict):
    mask = backend.sum(y_true, axis=2)
    y_pred_labels = backend.cast(backend.argmax(y_predict, axis=2), 'float32')
    y_true_labels = backend.cast(backend.argmax(y_true, axis=2), 'float32')
    is_same = backend.cast(backend.equal(
        y_true_labels, y_pred_labels), 'float32')
    num_same = backend.sum(is_same * mask, axis=1)
    lengths = backend.sum(mask, axis=1)
    return backend.mean(num_same / lengths, axis=0)

# Base object for predicting the Q8 labels of amino acid sequences
class Predictor(object):
    def __init__(self, batch_size=300, print_confusion=False):
        self.model = Sequential()
        self.batch_size = batch_size
        self.add_layers()
        self.model.compile(optimizer='adagrad',
            loss='categorical_crossentropy',
            sample_weight_mode='temporal',
            metrics=[truncated_accuracy])
        self.model.summary()
        self.print_confusion = print_confusion

    # This function should be implemented in child classes, as it implements
    # the neural network architecture
    def add_layers(self):
        pass

    # Trains the neural network model given training and validation data
    def train(self, x_train, y_train, lengths_train, x_val, y_val, lengths_val,
        num_epochs=20, batch_size=50):
        weight_mask_train = np.zeros((x_train.shape[0], SEQUENCE_LIMIT))
        for i in range(len(lengths_train)):
            weight_mask_train[i, : lengths_train[i]] = 1.0
        weight_mask_val = np.zeros((x_val.shape[0], SEQUENCE_LIMIT))
        for i in range(len(lengths_val)):
            weight_mask_val[i, : lengths_val[i]] = 1.0
        self.model.fit(x_train, y_train,
          batch_size=self.batch_size,
          epochs=num_epochs,
          validation_data=(x_val, y_val, weight_mask_val),
          shuffle=True,
          sample_weight=weight_mask_train,
          callbacks=[ConfusionMatrix(print_confusion=self.print_confusion)])

    # Evaluates the test performance of the model, returning a list
    # [cross entropy loss, truncated_accuracy on test set]
    def evaluate_loss(self, x_test, y_test, test_lengths):
        weight_mask = np.zeros((x_test.shape[0], SEQUENCE_LIMIT))
        for i in range(len(test_lengths)):
            weight_mask[i, : test_lengths[i]] = 1.0
        return self.model.evaluate(x=x_test, y=y_test,
          batch_size=self.batch_size,
          sample_weight=weight_mask)

    # Produces the label predictions of the test set (as a list of strings)
    def predict(self, x_test, test_lengths):
        vectorized_predictions = self.model.predict(x_test,
            batch_size=self.batch_size,
            verbose=1)
        predictions = []
        for i in range(vectorized_predictions.shape[0]):
            predictions.append('')
            labels = np.argmax(vectorized_predictions[i, :, :], axis=1)
            for j in range(test_lengths[i]):
                predictions[-1] += LABEL_SET[labels[j]]
        return predictions


# Predictor that uses a bidirectional LSTM
class BidirectionalLSTMPredictor(Predictor):
    def add_layers(self, activation='tanh'):
        self.model.add(Masking(mask_value=0, 
            input_shape=(SEQUENCE_LIMIT, INPUT_DIM)))
        self.model.add(Bidirectional(LSTM(HIDDEN_DIM, activation=activation, 
            return_sequences=True), merge_mode='concat'))
        self.model.add(TimeDistributed(Dense(HIDDEN_DIM)))
        self.model.add(TimeDistributed(
            Dense(OUTPUT_DIM, activation='softmax')))

