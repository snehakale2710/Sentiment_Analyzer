from sklearn.base import BaseEstimator, TransformerMixin
import os
import nltk
from nltk.corpus import stopwords
import re
import string
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
nltk.data.path.insert(0, os.path.join(BASE_DIR, "nltk_data"))


class TextCleaner(BaseEstimator, TransformerMixin):
    def __init__(self):
        self.stop_words = set(stopwords.words('english'))
        self.important = {'no', 'not', 'nor', 'never'}

    def clean_text(self, text):
        text = re.sub(r"[^a-zA-Z0-9']+", " ", text)
        text = text.lower()

        tokens = text.split()
        cleaned = []

        for w in tokens:
            if w.endswith("n't"):
                cleaned.append(w)
                continue

            if w in self.important:
                cleaned.append(w)
                continue

            if w not in self.stop_words:
                cleaned.append(w)

        return " ".join(cleaned)

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        if not isinstance(X, pd.Series):
            X = pd.Series(X)

        X = X.fillna("")
        X = X.apply(self.clean_text)

        return X.values