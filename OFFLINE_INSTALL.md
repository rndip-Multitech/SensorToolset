# Offline install (LoRaWAN Linux gateway)

This app can run on a Linux gateway **without internet**: either as a **self-contained binary** (no Python/pip on the device) or from source using **offline pip**.

## Option 1: Self-contained binary (no pip on gateway)

Build on a Linux machine that has Python and network access (once). Then deploy the resulting folder to the gateway (USB, SCP, etc.); the gateway does not need Python or pip.

### Build (once, on a Linux build machine)

1. Install build dependencies (requires internet on the build machine):

```bash
pip3 install -r requirements.txt -r requirements-build.txt
```

2. Run the Linux build script:

```bash
chmod +x build_linux.sh
./build_linux.sh
```

Output: `dist/RadioBridgeTools/` containing the `RadioBridgeTools` binary and bundled assets.

### Deploy to the gateway (offline)

1. Copy the entire folder `dist/RadioBridgeTools/` to the gateway (e.g. `/opt/RadioBridgeTools` or your app-manager app directory).
2. Make the binary executable: `chmod +x RadioBridgeTools`
3. Run:

```bash
./RadioBridgeTools --host 0.0.0.0 --port 5000
```

Or use the mPower **Start** script: set `APP_DIR` to the folder that contains the binary and run `./Start start`. If a `RadioBridgeTools` executable is present in `APP_DIR`, Start can be configured to run it instead of `python3 server.py` (see README_LINUX_APP.md or Start script).

### Where data is stored (Linux)

The binary needs a writable directory for config and custom decoders. It uses (in order):

- **Portable**: directory of the executable (if writable)
- **Override**: `RBT_DATA_DIR` environment variable
- **Fallback**: `$XDG_DATA_HOME/RadioBridgeTools` or `~/.local/share/RadioBridgeTools`

Example override:

```bash
export RBT_DATA_DIR=/var/config/radio-bridge-tools
./RadioBridgeTools --host 0.0.0.0 --port 5000
```

---

## Option 2: Run from source with offline pip (gateway has Python, no internet)

If you prefer to run from source on the gateway (e.g. `python3 server.py`) but the gateway has no internet:

1. On a connected machine, download wheels:

```bash
pip3 download -r requirements.txt -d wheels
```

2. Copy the project and the `wheels/` folder to the gateway.
3. On the gateway, in post_install (or manually):

```bash
pip3 install --user --no-index --find-links=wheels -r requirements.txt
```

Then run the app as usual (e.g. via Start script with `python3 server.py`).

---

## Summary

| Target (gateway)        | Build step              | Deploy                        |
|------------------------|-------------------------|-------------------------------|
| No Python/pip on device| Run `build_linux.sh`    | Copy `dist/RadioBridgeTools/` |
| Python, no internet    | `pip download` → wheels | Copy app + wheels, pip install --no-index |
