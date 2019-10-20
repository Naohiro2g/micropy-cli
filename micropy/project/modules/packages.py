# -*- coding: utf-8 -*-

"""Project Packages Module"""

import shutil
import tempfile
from pathlib import Path

import requirements

from micropy import utils
from micropy.project.modules import ProjectModule


class PackagesModule(ProjectModule):

    def __init__(self, path, packages=None, **kwargs):
        self._path = Path(path)
        self._loaded = False
        packages = packages or {}
        self.name = "packages"
        self.packages = {**packages}

    @property
    def path(self):
        path = self.parent.path / self._path
        return path

    @property
    def pkg_path(self):
        return self.parent.data_path / self.parent.name

    @property
    def config(self):
        return {
            self.name: self.packages
        }

    @property
    def context(self):
        _paths = self.parent._context.get('paths', set())
        _paths.add(self.pkg_path)
        return {
            'paths': _paths
        }

    def _fetch_package(self, url):
        """Fetch and stub package at url

        Args:
            url (str): URL to fetch

        Returns:
            Path: path to package
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            file_name = utils.get_url_filename(url)
            self.log.debug(f"Fetching package: {file_name}")
            _file_name = "".join(self.log.iter_formatted(f"$B[{file_name}]"))
            content = utils.stream_download(
                url, desc=f"{self.log.get_service()} {_file_name}")
            pkg_path = utils.extract_tarbytes(content, tmp_path)
            ignore = ['setup.py', '__version__', 'test_']
            pkg_init = next(pkg_path.rglob("__init__.py"), None)
            py_files = [f for f in pkg_path.rglob(
                "*.py") if not any(i in f.name for i in ignore)]
            stubs = [utils.generate_stub(f) for f in py_files]
            if pkg_init:
                data_path = self.pkg_path / pkg_init.parent.name
                shutil.rmtree(data_path, ignore_errors=True)
                shutil.copytree(pkg_init.parent, data_path)
                return data_path
            # Iterates over flattened list of stubs tuple
            file_paths = [(f, (self.pkg_path / f.name)) for f in list(sum(stubs, ()))]
            for paths in file_paths:
                shutil.move(*paths)  # overwrite if existing

    @ProjectModule.hook(dev=False)
    def add_from_file(self, path=None, dev=False, **kwargs):
        """Loads all requirements from file

        Args:
            path (str): Path to file. Defaults to self.path.
        """
        reqs = utils.iter_requirements(self.path)
        for req in reqs:
            self.add_package(req, fetch=True)
        return reqs

    @ProjectModule.hook()
    def add_package(self, package, dev=False, **kwargs):
        """Add requirement to project

        Args:
            package (str): package name/spec

        Returns:
            dict: Dictionary of packages
        """
        pkg = package
        if isinstance(package, str):
            pkg = next(requirements.parse(package))
        self.log.info(f"Adding $[{pkg.name}] to requirements...")
        if self.packages.get(pkg.name, None):
            self.log.error(f"$[{pkg.name}] is already installed!")
            return None
        specs = "".join(next(iter(pkg.specs))) if pkg.specs else "*"
        self.packages[pkg.name] = specs
        self.parent.to_json()
        self.load()
        self.log.success("Package installed!")
        return self.packages

    def load(self, fetch=True, **kwargs):
        """Retrieves and stubs project requirements"""
        self.pkg_path.mkdir(exist_ok=True)
        if self.path.exists():
            packages = utils.iter_requirements(self.path)
            for p in packages:
                spec = "".join(next(iter(p.specs))) if p.specs else "*"
                self.packages.update({p.name: spec})
        pkg_keys = set(self.packages.keys())
        pkg_cache = self.parent._get_cache(self.name)
        new_pkgs = pkg_keys.copy()
        if pkg_cache:
            new_pkgs = new_pkgs - set(pkg_cache)
        pkgs = [(name, s)
                for name, s in self.packages.items() if name in new_pkgs]
        if fetch:
            if pkgs:
                self.log.title("Fetching Requirements")
            for name, spec in pkgs:
                meta = utils.get_package_meta(name, spec=spec)
                tar_url = meta['url']
                self._fetch_package(tar_url)
        self.update()
        self.parent._set_cache(self.name, list(pkg_keys))

    def create(self):
        return self.update()

    def update(self):
        """Dumps packages to file at path"""
        if not self.path.exists():
            self.path.touch()
        pkgs = [(f"{name}{spec}" if spec and spec != "*" else name)
                for name, spec in self.packages.items()]
        with self.path.open('r+') as f:
            content = [c.strip() for c in f.readlines() if c.strip() != '']
            _lines = sorted(set(pkgs) | set(content))
            lines = [l + "\n" for l in _lines]
            f.seek(0)
            f.writelines(lines)


class DevPackagesModule(PackagesModule):

    def __init__(self, path, **kwargs):
        super().__init__(path, **kwargs)
        self.packages.update({'micropy-cli': '*'})
        self.name = "dev-packages"

    def load(self, *args, **kwargs):
        return super().load(*args, **kwargs, fetch=False)

    @ProjectModule.hook(dev=True)
    def add_package(self, package, **kwargs):
        return super().add_package(package, **kwargs)

    @ProjectModule.hook(dev=True)
    def add_from_file(self, path=None, **kwargs):
        return super().add_from_file(path=path, **kwargs)
