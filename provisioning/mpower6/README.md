# ./provisioning/mpower6

This directory contains provisioning files for **mPower 6** gateways.

## Architecture

mPower 6 gateways use **ARMv7** files (`armv7vet2hf-neon` architecture).

## IPK Packages

The following Python packages are required and should be included as IPK files built for ARMv7 (cortexa7t2hf-neon) architecture:

- python3-xmlrpc
- python3-pip
- python3-misc
- python3-multiprocessing
- python3-mmap
- python3-distutils

These packages should be placed in this directory and listed in `p_manifest.json`.

## Usage

When building the application for mPower 6 gateways, ensure:
1. The `p_manifest.json` file references the correct IPK files
2. All IPK files are built for ARMv7 (`armv7vet2hf-neon`) architecture
3. The provisioning directory is included in the application package

## Differences from mPower 7

- **mPower 6**: Uses ARMv7 (`armv7vet2hf-neon`) architecture
- **mPower 7**: Uses ARMv7 (`cortexa7t2hf-neon`) architecture

The IPK package filenames reflect the architecture difference in their naming convention.
