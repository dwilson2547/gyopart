from src.services.geo import haversine_miles


def test_same_point_is_zero():
    assert haversine_miles(40.7128, -74.0060, 40.7128, -74.0060) == 0.0


def test_new_york_to_los_angeles():
    miles = haversine_miles(40.7128, -74.0060, 34.0522, -118.2437)
    assert 2440 < miles < 2460


def test_short_distance():
    miles = haversine_miles(40.7128, -74.0060, 40.7580, -73.9855)
    assert 3.0 < miles < 4.0
