from src.defects.centroid import update_centroid


def test_update_centroid_from_empty():
    assert update_centroid(None, 0, [1.0, 3.0]) == [1.0, 3.0]


def test_update_centroid_running_mean():
    # centroide [2,2] con count=2, nuevo [8,8] -> (2*2+8)/3 = 4 en cada dim
    assert update_centroid([2.0, 2.0], 2, [8.0, 8.0]) == [4.0, 4.0]


def test_update_centroid_length_mismatch_raises():
    import pytest
    with pytest.raises(ValueError):
        update_centroid([1.0, 2.0], 1, [1.0])
