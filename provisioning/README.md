# ./provisioning

If the application requires installed dependencies include a ./provisioning directory, the edited `p_manifest.json` file, and ipk packages when building the application.

## IPK Packages

The following Python packages are required and should be included as IPK files:

- python3-xmlrpc
- python3-pip
- python3-misc
- python3-multiprocessing
- python3-mmap

These packages should be placed in this directory and listed in `p_manifest.json`.

