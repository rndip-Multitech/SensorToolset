# ./provisioning

If the application requires installed dependencies include a ./provisioning directory, the edited `p_manifest.json` file, and ipk packages when building the application.

## Architecture Support

This provisioning directory supports both mPower 6 and mPower 7 gateways:

- **mPower 7** (default): Uses ARMv7 (`cortexa7t2hf-neon`) architecture
  - Files are in the root `provisioning/` directory
  - Manifest: `p_manifest.json`
  
- **mPower 6**: Uses ARMv7 (`armv7vet2hf-neon`) architecture
  - Files are in the `provisioning/mpower6/` subdirectory
  - Manifest: `provisioning/mpower6/p_manifest.json`

## IPK Packages

The following Python packages are required and should be included as IPK files:

- python3-xmlrpc
- python3-pip
- python3-misc
- python3-multiprocessing
- python3-mmap
- python3-distutils

### For mPower 7 (cortexa7t2hf-neon)
These packages should be placed in the root `provisioning/` directory and listed in `p_manifest.json`.

### For mPower 6 (armv7vet2hf-neon)
These packages should be placed in the `provisioning/mpower6/` directory and listed in `provisioning/mpower6/p_manifest.json`. IPK files must be built for the `armv7vet2hf-neon` architecture.

**Note**: mPower 6 and mPower 7 use different ARMv7 architecture suffixes:
- mPower 6: `*_armv7vet2hf-neon.ipk`
- mPower 7: `*_cortexa7t2hf-neon.ipk`

## Building for Different Platforms

When building the application:
1. **For mPower 7**: Use the files in `provisioning/` root directory
2. **For mPower 6**: Use the files in `provisioning/mpower6/` directory

Ensure the correct manifest file and IPK packages are included based on the target platform.


