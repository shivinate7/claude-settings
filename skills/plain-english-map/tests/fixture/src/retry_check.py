import retry


def test_wait():
    assert retry.RETRY_WAIT_S == 30
