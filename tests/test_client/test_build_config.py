from pathlib import Path
from jsonschema import ValidationError

import pytest

import idom
from idom.client.build_config import (
    BuildConfig,
    find_build_config_item_in_python_file,
    find_python_packages_build_config_items,
    split_package_name_and_version,
    validate_config,
    derive_config_item_info,
    ConfigItemInfo,
)


@pytest.fixture
def make_build_config(tmp_path):
    """A fixture for quickly constructing build configs"""

    def make(*config_items):
        config = BuildConfig(tmp_path)
        config.update(config_items)
        config.save()
        return config

    return make


@pytest.mark.parametrize(
    "value, expectation",
    [
        (
            {
                "version": "1.2.3",
                "items": {"some_module": {"source_name": None}},
            },
            "None is not of type 'string'",
        ),
        (
            {
                "version": "1.2.3",
                "items": {"some_module": {"source_name": "$bad-symbols!"}},
            },
            r"'\$bad-symbols\!' does not match",
        ),
        (
            {
                "version": "1.2.3",
                "items": {"some_module": {"source_name": "some_module"}},
            },
            None,
        ),
        (
            {
                "version": "1.2.3",
                "items": {
                    "some_module": {
                        "source_name": "some_module",
                        "js_dependencies": None,
                    }
                },
            },
            "None is not of type 'array'",
        ),
        (
            {
                "version": "1.2.3",
                "items": {
                    "some_module": {
                        "source_name": "some_module",
                        "js_dependencies": [],
                    }
                },
            },
            None,
        ),
        (
            {
                "version": "1.2.3",
                "items": {
                    "some_module": {
                        "source_name": "some_module",
                        "js_dependencies": [None],
                    }
                },
            },
            "None is not of type 'string'",
        ),
        (
            {
                "version": "1.2.3",
                "items": {
                    "some_module": {
                        "source_name": "some_module",
                        "js_dependencies": ["dep1", "dep2"],
                    }
                },
            },
            None,
        ),
    ],
)
def test_validate_config_schema(value, expectation):
    if expectation is None:
        validate_config(value)
    else:
        with pytest.raises(ValidationError, match=expectation):
            validate_config(value)


def test_derive_config_item_info():
    assert derive_config_item_info(
        {
            "source_name": "some_module",
            "js_dependencies": ["dep1", "dep2"],
        }
    ) == ConfigItemInfo(
        js_dependency_aliases={
            "dep1": "dep1-some_module-261bad9",
            "dep2": "dep2-some_module-261bad9",
        },
        aliased_js_dependencies=[
            "dep1-some_module-261bad9@npm:dep1",
            "dep2-some_module-261bad9@npm:dep2",
        ],
    )


def test_find_build_config_item_in_python_file(tmp_path):
    py_module_path = tmp_path / "a_test.py"
    with py_module_path.open("w") as f:
        f.write("idom_build_config = {'js_dependencies': ['some-js-package']}")
    actual_config = find_build_config_item_in_python_file("a_test", py_module_path)
    assert actual_config == {
        "source_name": "a_test",
        "js_dependencies": ["some-js-package"],
    }


def test_build_config_file_load_absent_config(make_build_config):
    assert make_build_config().data == {
        "version": idom.__version__,
        "items": {},
    }


def test_build_config_file_repr(make_build_config):
    config = make_build_config()
    config.update(
        [{"source_name": "a_test", "js_dependencies": ["a-different-package"]}]
    )
    assert str(config) == f"BuildConfig({config.data})"


def test_build_config_file_add_config_item_and_save(make_build_config):
    config = make_build_config()
    config.update([{"source_name": "a_test", "js_dependencies": ["some-js-package"]}])
    config.save()

    assert make_build_config().data["items"] == {
        "a_test": {"source_name": "a_test", "js_dependencies": ["some-js-package"]}
    }
    assert make_build_config().has_config_item("a_test")


def test_find_python_packages_build_config_items():
    mock_site_pkgs_path = str((Path(__file__).parent / "mock_site_packages").absolute())
    configs, errors = find_python_packages_build_config_items([mock_site_pkgs_path])
    assert configs == [
        {
            "source_name": "has_good_config",
            "js_dependencies": ["some-js-package"],
        }
    ]

    assert len(errors) == 1

    with pytest.raises(
        RuntimeError,
        match="Failed to load build config for module 'has_bad_config'",
    ):
        raise errors[0]

    with pytest.raises(ValidationError, match="1 is not of type 'string'"):
        raise errors[0].__cause__


@pytest.mark.parametrize(
    "package_specifier,expected_name_and_version",
    [
        ("package", ("package", "")),
        ("package@1.2.3", ("package", "1.2.3")),
        ("@scope/pkg", ("@scope/pkg", "")),
        ("@scope/pkg@1.2.3", ("@scope/pkg", "1.2.3")),
        ("alias@npm:package", ("alias", "npm:package")),
        ("alias@npm:package@1.2.3", ("alias", "npm:package@1.2.3")),
        ("alias@npm:@scope/pkg@1.2.3", ("alias", "npm:@scope/pkg@1.2.3")),
        ("@alias/pkg@npm:@scope/pkg@1.2.3", ("@alias/pkg", "npm:@scope/pkg@1.2.3")),
    ],
)
def test_split_package_name_and_version(package_specifier, expected_name_and_version):
    assert (
        split_package_name_and_version(package_specifier) == expected_name_and_version
    )


def test_build_config_get_js_dependency_alias(make_build_config):
    config = make_build_config(
        {"source_name": "module_1", "js_dependencies": ["dep1", "dep2"]},
        {"source_name": "module_2", "js_dependencies": ["dep2", "dep3"]},
    )
    assert config.get_js_dependency_alias("module_1", "dep1") == "dep1-module_1-5001a4b"
    assert config.get_js_dependency_alias("module_1", "dep2") == "dep2-module_1-5001a4b"
    assert config.get_js_dependency_alias("module_2", "dep2") == "dep2-module_2-46d6db8"
    assert config.get_js_dependency_alias("module_2", "dep3") == "dep3-module_2-46d6db8"


def test_build_config_all_aliased_js_dependencies(make_build_config):
    config = make_build_config(
        {"source_name": "module_1", "js_dependencies": ["dep1", "dep2"]},
        {"source_name": "module_2", "js_dependencies": ["dep2", "dep3"]},
    )
    assert config.all_aliased_js_dependencies() == [
        "dep1-module_1-5001a4b@npm:dep1",
        "dep2-module_1-5001a4b@npm:dep2",
        "dep2-module_2-46d6db8@npm:dep2",
        "dep3-module_2-46d6db8@npm:dep3",
    ]


def test_build_config_all_js_dependency_aliases(make_build_config):
    config = make_build_config(
        {"source_name": "module_1", "js_dependencies": ["dep1", "dep2"]},
        {"source_name": "module_2", "js_dependencies": ["dep2", "dep3"]},
    )
    assert config.all_js_dependency_aliases() == [
        "dep1-module_1-5001a4b",
        "dep2-module_1-5001a4b",
        "dep2-module_2-46d6db8",
        "dep3-module_2-46d6db8",
    ]


def test_get_js_dependency_alias(make_build_config):
    config = make_build_config(
        {"source_name": "module_1", "js_dependencies": ["dep1", "dep2"]},
        {"source_name": "module_2", "js_dependencies": ["dep2", "dep3"]},
    )
    assert config.get_js_dependency_alias("module_1", "dep1") == "dep1-module_1-5001a4b"
    assert config.get_js_dependency_alias("module_1", "dep2") == "dep2-module_1-5001a4b"
    assert config.get_js_dependency_alias("module_2", "dep2") == "dep2-module_2-46d6db8"
    assert config.get_js_dependency_alias("module_2", "dep3") == "dep3-module_2-46d6db8"

    assert config.get_js_dependency_alias("missing_module", "missing_dep") is None
    assert config.get_js_dependency_alias("module_1", "missing_dep") is None