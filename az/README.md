# az

This image invokes [az](https://docs.microsoft.com/en-us/cli/azure/get-started-with-azure-cli?view=azure-cli-latest). Any arguments provided to this image are passed to az.

## Building

To build this image, run the following in this directory.

```sh
$ az acr run -f acb.yaml -r registryname /dev/null
```

## Usage

Refer to the [acb.yaml](./acb.yaml) file for example usage.