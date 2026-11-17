import random

import pytest

from beating_in_sync_app.brain.user_model import UserModel
from beating_in_sync_app.config import Config


@pytest.fixture
def cfg():
    return Config()


@pytest.fixture
def rng():
    return random.Random(1)


@pytest.fixture
def user():
    return UserModel(name="Ana", name_confirmed=True, language="es", language_confirmed=True)
