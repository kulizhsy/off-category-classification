import dataclasses
from typing import Dict, Iterable

import numpy as np
import pandas as pd
from sklearn.preprocessing import MultiLabelBinarizer
from tensorflow.python.keras.preprocessing.sequence import pad_sequences

from category_classification.models import TextPreprocessingConfig
from utils.constant import UNK_TOKEN
from utils.preprocess import generate_y, tokenize, preprocess_product_name


def generate_data_from_df(df: pd.DataFrame,
                          ingredient_to_id: Dict,
                          category_to_id: Dict,
                          product_name_token_to_int: Dict[str, int],
                          nlp,
                          product_name_max_length: int,
                          product_name_preprocessing_config: TextPreprocessingConfig):
    ingredient_matrix = process_ingredients(df.known_ingredient_tags,
                                            ingredient_to_id).astype(np.float32)
    product_name_matrix = process_product_name(df.product_name,
                                               nlp=nlp,
                                               token_to_int=product_name_token_to_int,
                                               max_length=product_name_max_length,
                                               preprocessing_config=product_name_preprocessing_config)
    y = generate_y(df.categories_tags, category_to_id)
    return [ingredient_matrix, product_name_matrix], y


def generate_data(ingredient_tags: Iterable[str],
                  product_name: str,
                  ingredient_to_id: Dict,
                  product_name_token_to_int: Dict[str, int],
                  nlp,
                  product_name_max_length: int,
                  product_name_preprocessing_config: TextPreprocessingConfig):
    ingredient_matrix = process_ingredients([list(ingredient_tags)],
                                            ingredient_to_id)
    product_name_matrix = process_product_name([product_name],
                                               nlp=nlp,
                                               token_to_int=product_name_token_to_int,
                                               max_length=product_name_max_length,
                                               preprocessing_config=product_name_preprocessing_config)
    return [ingredient_matrix, product_name_matrix]


def process_ingredients(ingredients: Iterable[Iterable[str]],
                        ingredient_to_id: Dict[str, int]) -> np.ndarray:
    ingredient_count = len(ingredient_to_id)
    ingredient_binarizer = MultiLabelBinarizer(classes=list(range(ingredient_count)))
    ingredient_int = [[ingredient_to_id[ing]
                       for ing in product_ingredients
                       if ing in ingredient_to_id]
                      for product_ingredients in ingredients]
    return ingredient_binarizer.fit_transform(ingredient_int)


def process_product_name(product_names: Iterable[str],
                         nlp,
                         token_to_int: Dict,
                         max_length: int,
                         preprocessing_config: TextPreprocessingConfig):
    tokens_all = [tokenize(preprocess_product_name(text, **dataclasses.asdict(preprocessing_config)), nlp)
                  for text in product_names]
    tokens_int = [[token_to_int[t if t in token_to_int else UNK_TOKEN] for t in tokens]
                  for tokens in tokens_all]
    return pad_sequences(tokens_int, max_length)
