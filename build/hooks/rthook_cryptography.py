# Runtime hook — executed before any application code
# Forces cryptography to use the bundled OpenSSL backend
import os
import sys

# Tell cryptography to avoid loading system OpenSSL in favour of the bundled one
os.environ.setdefault("CRYPTOGRAPHY_OPENSSL_LESS_SAFE_LOADING", "1")

# On macOS, ensure the Frameworks directory is in the dynamic library path
if sys.platform == "darwin":
    frameworks = os.path.join(sys._MEIPASS, "..", "Frameworks")
    if os.path.isdir(frameworks):
        os.environ["DYLD_LIBRARY_PATH"] = (
            frameworks + ":" + os.environ.get("DYLD_LIBRARY_PATH", "")
        )

# On Linux, similar treatment for bundled .so files
if sys.platform.startswith("linux"):
    lib_dir = sys._MEIPASS
    os.environ["LD_LIBRARY_PATH"] = (
        lib_dir + ":" + os.environ.get("LD_LIBRARY_PATH", "")
    )
