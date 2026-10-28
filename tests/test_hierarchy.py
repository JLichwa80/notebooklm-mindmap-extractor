from copy import deepcopy

import pytest

from notebooklm_mindmap_extractor import build_hierarchy


def raw(name, x, y, level=None):
    return {"id": name, "title": name, "x": x, "y": y, "level": level}


def test_explicit_levels_preserve_preorder_and_normalize_root():
    nodes = [raw("root", 0, 100, 2), raw("A", 100, 0, 3),
             raw("A1", 200, 0, 4), raw("B", 100, 200, 3), raw("B1", 200, 200, 4)]
    before = deepcopy(nodes)
    root, = build_hierarchy(nodes)
    assert root.level == 1
    assert [n.title for n in root.children] == ["A", "B"]
    assert root.children[0].children[0].title == "A1"
    assert root.children[1].children[0].title == "B1"
    assert nodes == before


def test_coordinate_children_belong_to_nearest_parent():
    root, = build_hierarchy([raw("root", 0, 100), raw("A", 100, 0),
                            raw("B", 101, 200), raw("A1", 200, 0), raw("B1", 200, 200)])
    assert [n.title for n in root.children] == ["A", "B"]
    assert root.children[0].children[0].title == "A1"
    assert root.children[1].children[0].title == "B1"


@pytest.mark.parametrize("levels", [[1, None], [1, 0], [1, 3], [1, -1]])
def test_invalid_levels_fail_clearly(levels):
    with pytest.raises(ValueError, match="level"):
        build_hierarchy([raw(str(i), i * 100, 0, level) for i, level in enumerate(levels)])


def test_empty_mindmap():
    assert build_hierarchy([]) == []
