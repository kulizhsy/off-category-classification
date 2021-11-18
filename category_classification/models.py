import contextlib
import dataclasses
import datetime
from typing import List, Optional, Union

import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers
import pandas as pd

from .constants import NUTRIMENTS


@dataclasses.dataclass
class TrainConfig:
    batch_size: int
    epochs: int
    lr: float
    label_smoothing: float = 0
    start_datetime: Union[datetime.datetime, None, str] = None
    end_datetime: Union[datetime.datetime, None, str] = None


@dataclasses.dataclass
class ModelConfig:
    product_name_lstm_recurrent_dropout: float
    product_name_lstm_dropout: float
    product_name_embedding_size: int
    product_name_lstm_units: int
    product_name_max_length: int
    hidden_dim: int
    hidden_dropout: float
    product_name_voc_size: Optional[int] = None
    ingredient_voc_size: Optional[int] = None
    nutriment_input: bool = False


@dataclasses.dataclass
class Config:
    train_config: TrainConfig
    model_config: ModelConfig
    product_name_min_count: int
    category_min_count: int = 0
    ingredient_min_count: int = 0

@tf.keras.utils.register_keras_serializable()
class OutputMapperLayer(layers.Layer):
    '''
        The OutputMapperLayer converts the label indices produced by the model to
        the taxonomy category ids and limits them to top N labels.
    '''
    def __init__(self, labels: List[str], top_n: int, **kwargs):
        self.labels = labels
        self.top_n = top_n

        super(OutputMapperLayer, self).__init__(**kwargs)

    def call(self, x):
        batch_size = tf.shape(x)[0]

        tf_labels = tf.constant([self.labels], dtype="string")
        tf_labels = tf.tile(tf_labels, [batch_size, 1])

        top_n = tf.nn.top_k(x, k=self.top_n, sorted=True, name="top_k").indices

        top_conf = tf.gather(x, top_n, batch_dims=1)
        top_labels = tf.gather(tf_labels, top_n, batch_dims=1)

        return [top_conf, top_labels]

    def compute_output_shape(self, input_shape):
        batch_size = input_shape[0]
        top_shape = (batch_size, self.top_n)
        return [top_shape, top_shape]

    def get_config(self):
        config={'labels': self.labels, 'top_n': self.top_n}
        base_config = super(OutputMapperLayer, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))


@dataclasses.dataclass
class KerasPreprocessing:
    ingredient_preprocessing: keras.layers.Layer
    product_name_preprocessing: keras.layers.Layer
    category_vocab: List[str]


def construct_preprocessing(max_categories: int, max_product_name_tokens: int, max_length: int, max_ingredients: int, train_df: pd.DataFrame) -> KerasPreprocessing:
    category_lookup = tf.keras.layers.StringLookup(max_tokens=max_categories, output_mode="multi_hot", num_oov_indices=0)
    category_lookup.adapt(tf.ragged.constant(train_df.categories_tags))

    product_name_preprocessing = tf.keras.layers.TextVectorization(split='whitespace', max_tokens=max_product_name_tokens, output_sequence_length=max_length)
    product_name_preprocessing.adapt(train_df.product_name)

    ingredient_preprocessing = tf.keras.layers.StringLookup(max_tokens=max_ingredients, output_mode="multi_hot")
    ingredient_preprocessing.adapt(tf.ragged.constant(train_df.known_ingredient_tags))

    return KerasPreprocessing(ingredient_preprocessing, product_name_preprocessing, category_lookup.get_vocabulary())



def build_model(config: ModelConfig, preprocessing: KerasPreprocessing) -> keras.Model:
    ingredient_input = keras.Input(shape=(None,), dtype=tf.string, name="ingredient")
    product_name_input = keras.Input(shape=(1,), dtype=tf.string, name="product_name")

    product_name_layer = preprocessing.product_name_preprocessing(product_name_input)

    product_name_embedding = layers.Embedding(
        input_dim=93000,
        output_dim=config.product_name_embedding_size,
        mask_zero=False,
    )(product_name_layer)

    product_name_lstm = layers.Bidirectional(
        layers.LSTM(
            units=config.product_name_lstm_units,
            recurrent_dropout=config.product_name_lstm_recurrent_dropout,
            dropout=config.product_name_lstm_dropout,
        )
    )(product_name_embedding)

    ingredient_layer = preprocessing.ingredient_preprocessing(ingredient_input)

    inputs = [ingredient_input, product_name_input]
    concat_input = [ingredient_layer, product_name_lstm]

    concat = layers.Concatenate()(concat_input)
    concat = layers.Dropout(config.hidden_dropout)(concat)
    hidden = layers.Dense(config.hidden_dim)(concat)
    hidden = layers.Dropout(config.hidden_dropout)(hidden)
    hidden = layers.Activation("relu")(hidden)
    output = layers.Dense(len(preprocessing.category_vocab), activation="sigmoid")(hidden)
    return keras.Model(inputs=inputs, outputs=[output])


def to_serving_model(base_model: keras.Model, categories: List[str]) -> keras.Model:
    mapper_layer = OutputMapperLayer(categories, 50)(base_model.output)
    return keras.Model(base_model.input, mapper_layer)
