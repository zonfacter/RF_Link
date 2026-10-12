"""Track included Arduino tabs and plugins, which the C++ scanner may skip."""
from pathlib import Path
Import("env")

project = Path(env.subst("$PROJECT_DIR"))
dependencies = [str(path) for folder in ("legacy", "include")
                for path in (project / folder).rglob("*")
                if path.is_file() and path.suffix in (".ino", ".c", ".h")]
env.Depends("$BUILD_DIR/src/main.cpp.o", dependencies)
