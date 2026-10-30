"""Include the same native source assets in wheels and the source Skill."""
from pathlib import Path
from setuptools import setup
from setuptools.command.build_py import build_py

ROOT = Path(__file__).resolve().parent
NATIVE_ASSETS = {
    'SourceWindow.swift': ROOT / 'desktop/macos/SourceWindow.swift',
    'Reprise.icns': ROOT / 'skills/reprise/assets/Reprise.icns',
    'reprise-icon-1024.png': ROOT / 'skills/reprise/assets/reprise-icon-1024.png',
}


class BuildRuntime(build_py):
    def run(self):
        super().run()
        target = Path(self.build_lib) / 'reprise'
        for name, source in NATIVE_ASSETS.items():
            self.copy_file(str(source), str(target / name))


setup(cmdclass={'build_py': BuildRuntime})
