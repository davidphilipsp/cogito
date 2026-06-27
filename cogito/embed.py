import os

import numpy as np

_PROVIDER = os.getenv('EMBED_PROVIDER', 'fastembed')
_MODEL = os.getenv('EMBED_MODEL', 'sentence-transformers/all-MiniLM-L6-v2')

_model = None


def _get_model():
    global _model
    if _model is None:
        if _PROVIDER == 'fastembed':
            from fastembed import TextEmbedding
            _model = TextEmbedding(_MODEL)
        elif _PROVIDER == 'ollama':
            raise NotImplementedError("EMBED_PROVIDER=ollama — Marco 3")
        else:
            raise ValueError(f"Unknown EMBED_PROVIDER: {_PROVIDER!r}")
    return _model


def embed(texts: list[str]) -> np.ndarray:
    model = _get_model()
    return np.array(list(model.embed(texts)), dtype=np.float32)
