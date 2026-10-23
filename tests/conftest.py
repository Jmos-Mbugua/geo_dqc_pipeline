"""Shared test fixtures: small fake counties so tests run offline and fast."""

import numpy as np
import pytest
from shapely.geometry import box

from fdq.synthetic.generate import generate_clean_survey
from fdq.synthetic.plant import plant_errors

# Squares (0.3° wide, about 33 km) near each real county. Nakuru's straddles
# 36°E, so the UTM zone switch is exercised.
FAKE_COUNTY_CENTRES = {
    "Nakuru": (36.0, -0.4),
    "Kakamega": (34.8, 0.3),
    "Bungoma": (34.6, 0.7),
    "Meru": (37.7, 0.1),
    "Uasin Gishu": (35.3, 0.5),
}
HALF_WIDTH = 0.15
N_FARMERS = 200


@pytest.fixture(scope="session")
def county_polygons() -> dict:
    return {
        name: box(x - HALF_WIDTH, y - HALF_WIDTH, x + HALF_WIDTH, y + HALF_WIDTH)
        for name, (x, y) in FAKE_COUNTY_CENTRES.items()
    }


@pytest.fixture(scope="session")
def clean_survey(county_polygons):
    return generate_clean_survey(county_polygons, N_FARMERS, np.random.default_rng(1))


@pytest.fixture(scope="session")
def planted(clean_survey, county_polygons):
    """(survey with errors, ground truth) built from the clean survey."""
    return plant_errors(clean_survey, county_polygons, np.random.default_rng(2))
