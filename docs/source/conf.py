# isort:skip_file
import inspect
import os
import pathlib
import subprocess
import sys
from urllib.parse import quote

from packaging.version import parse
from sphinx_astropy.conf.v2 import *

sys.path.insert(0, pathlib.Path(__file__).parents[0].resolve().as_posix())

import headerCSVGenerator

sys.path.insert(0, pathlib.Path(__file__).parents[2].resolve().as_posix())

import pyscope

project = "pyscope"
copyright = "2025, Walter W. Golay"
author = "Walter W. Golay"
version = pyscope.__version__
release = version

html_theme = "pydata_sphinx_theme"

html_static_path = [os.path.join(os.path.dirname(__file__), "_static")]

graphviz_dot = "/usr/local/bin/dot"

html_theme_options = {
    "logo": {
        "image_light": "_static/pyscope_logo_small_gray.png",
        "image_dark": "_static/pyscope_logo_small.png",
    },
    "icon_links": [
        {
            "name": "GitHub",
            "url": "https://github.com/macro-consortium/pyscope",
            "icon": "fa-brands fa-square-github",
        },
        {
            "name": "PyPI",
            "url": "https://pypi.org/project/pyscope/",
            "icon": "fa-brands fa-python",
        },
        {
            "name": "macro",
            "url": "https://macroconsortium.org",
            "icon": "fa-solid fa-shuttle-space",
        },
    ],
}

intersphinx_mapping["click"] = (
    "https://click.palletsprojects.com/en/8.1.x/",
    None,
)
intersphinx_mapping["astroquery"] = (
    "https://astroquery.readthedocs.io/en/latest/",
    None,
)
intersphinx_mapping["astroplan"] = (
    "https://astroplan.readthedocs.io/en/latest/",
    None,
)
intersphinx_mapping["sqlalchemy"] = (
    "https://docs.sqlalchemy.org/en/20/",
    None,
)

extensions = list(map(lambda x: x.replace("viewcode", "linkcode"), extensions))

# Generate CSV for header info
print("Generating CSV for header info...")
targetPath = os.path.join(
    os.path.dirname(__file__), "user_guide", "observatory_info.csv"
)
headerCSVGenerator.HeaderCSVGenerator().generate_csv(targetPath)


def linkcode_resolve(domain, info):
    """
    Determine the URL corresponding to Python object.

    Inspired by:
    - https://gist.github.com/nlgranger/55ff2e7ff10c280731348a16d569cb73
    - https://github.com/matplotlib/matplotlib/blob/main/doc/conf.py
    """
    if domain != "py":
        return None

    modname = info["module"]
    fullname = info["fullname"]

    submod = sys.modules.get(modname)
    if submod is None:
        return None

    obj = submod
    for part in fullname.split("."):
        try:
            obj = getattr(obj, part)
        except AttributeError:
            return None

    if inspect.isfunction(obj):
        obj = inspect.unwrap(obj)
    try:
        fn = inspect.getsourcefile(obj)
    except TypeError:
        fn = None
    if not fn or fn.endswith("__init__.py"):
        try:
            fn = inspect.getsourcefile(sys.modules[obj.__module__])
        except (TypeError, AttributeError, KeyError):
            fn = None
    if not fn:
        return None

    try:
        source, lineno = inspect.getsourcelines(obj)
    except (OSError, TypeError):
        lineno = None

    linespec = f"#L{lineno:d}-L{lineno + len(source) - 1:d}" if lineno else ""

    startdir = pathlib.Path(pyscope.__file__).parent.parent
    try:
        fn = os.path.relpath(fn, start=startdir).replace(os.path.sep, "/")
    except ValueError:
        return None

    linkcode_revision = "main"
    try:
        # lock to commit number
        cmd = "git log -n1 --pretty=%H"
        head = subprocess.check_output(cmd.split()).strip().decode("utf-8")
        linkcode_revision = head

        # if we are on main's HEAD, use main as reference
        cmd = "git log --first-parent main -n1 --pretty=%H"
        main = subprocess.check_output(cmd.split()).strip().decode("utf-8")
        if head == main:
            linkcode_revision = "main"

        # if we have a tag, use tag as reference
        cmd = "git describe --exact-match --tags " + head
        tag = (
            subprocess.check_output(cmd.split(" "), stderr=subprocess.DEVNULL)
            .strip()
            .decode("utf-8")
        )
        linkcode_revision = tag

    except subprocess.CalledProcessError:
        pass

    return (
        "https://github.com/macro-consortium/pyscope/blob"
        f"/{linkcode_revision}/{fn}{linespec}"
    )


extensions.append("sphinx_favicon")

favicons = [
    "logo16.png",
    "logo32.png",
    "logo48.png",
    "logo128.png",
    "logo256.png",
    "pyscopeIcon.svg",
    {"rel": "apple-touch-icon", "href": "logo180.png"},
]

extensions.append("sphinx.ext.doctest")

# extensions.append("sphinxcontrib.programoutput")
# extensions.append("sphinx_exec_code")
