import pytest


@pytest.mark.parametrize("path", ["/", "/manage/orders", "/manage/inventory", "/manage/reports"])
def test_pages_render(client, path):
    res = client.get(path)
    assert res.status_code == 200
    assert b"Fresh Market" in res.data
